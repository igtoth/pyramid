// Pyramid web. Two ways in, one page:
//  - hosted (GitHub Pages): sign in with your Genesys Cloud account through an
//    OAuth client with the PKCE grant; the page calls the API from your browser.
//  - local ("pyramid web"): the clients saved in the desktop app; the local
//    server adds the token, so secrets never reach the browser.
import {
  API_HOSTS, Api, ApiError, Cancelled, cell, fetchReport, flattenObject, loginHost, normalizeCatalog,
  pkceChallenge, pkceVerifier, queueMembers, resolve, rowsOf, tableColumns, toCSV,
} from "./core.js";

const VERSION = "3.0.0";
const MAX_TABS = 12;
const ROW_CHUNK = 2000;

const store = {
  get(area, k) { try { return window[area].getItem("pyramid." + k); } catch { return null; } },
  set(area, k, v) { try { v === null ? window[area].removeItem("pyramid." + k) : window[area].setItem("pyramid." + k, v); } catch { /* blocked */ } },
};

const S = {
  catalog: null, mode: "hosted", api: null, orgName: "", clientName: "", region: "",
  tabs: [], current: null, cache: new Map(), busy: false, abort: null, localClients: [],
};

// ── tiny DOM helper (text only: API values never become HTML) ────────────
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "style") {  // CSSOM, which the page's CSP allows (style attributes are blocked)
      for (const decl of String(v).split(";")) {
        const i = decl.indexOf(":");
        if (i > 0) el.style.setProperty(decl.slice(0, i).trim(), decl.slice(i + 1).trim());
      }
    }
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}
const $ = (id) => document.getElementById(id);

function status(text, kind = "") {
  const el = $("status");
  el.textContent = text;
  el.className = kind;
}

// ── theme ─────────────────────────────────────────────────────────────────
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  const b = document.getElementById("btn-theme");
  if (b) b.textContent = isDark() ? "Light" : "Dark";
}
function toggleTheme() {
  const next = isDark() ? "light" : "dark";
  applyTheme(next);
  store.set("localStorage", "theme", next);
}

// ── start ─────────────────────────────────────────────────────────────────
async function init() {
  applyTheme(store.get("localStorage", "theme"));
  $("version").textContent = "v" + VERSION;
  $("btn-theme").onclick = toggleTheme;
  $("btn-help").onclick = showHelp;
  $("btn-cancel").onclick = () => S.abort?.abort();
  $("btn-signout").onclick = signOut;
  document.addEventListener("keydown", onKey);
  S.catalog = normalizeCatalog(await (await fetch("catalog.json")).json());

  // "pyramid web" marks the page it serves; the hosted page never asks
  const local = document.documentElement.dataset.mode === "local"
    ? await fetch("local/info", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
    : null;
  if (local?.mode === "local") {
    S.mode = "local";
    S.localClients = local.clients || [];
    return showConnectLocal(local);
  }
  const q = new URLSearchParams(location.search);
  if (q.get("api") && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(q.get("api"))) {
    store.set("sessionStorage", "devBase", q.get("api"));  // tests and demos against tests/fake_genesys.py
  }
  if (q.has("code") || q.has("error")) return finishPkce(q);
  const tok = token();
  if (tok) return connectHosted(tok.region);
  showConnectHosted();
}

function devBase() { return store.get("sessionStorage", "devBase"); }
function apiHost(region) { return devBase() || API_HOSTS[region]; }
function loginBase(region) { return devBase() || loginHost(API_HOSTS[region]); }
function redirectUri() { return location.origin + location.pathname; }

function token() {
  try {
    const t = JSON.parse(store.get("sessionStorage", "token") || "null");
    return t && t.expiresAt > Date.now() + 60_000 ? t : null;
  } catch { return null; }
}

// ── hosted sign-in (PKCE) ─────────────────────────────────────────────────
function showConnectHosted(error) {
  const region = store.get("localStorage", "region") || "us_east_1";
  const clientId = store.get("localStorage", "clientId") || "";
  const sel = h("select", { id: "f-region" }, Object.keys(API_HOSTS).map((r) => h("option", { value: r, selected: r === region }, r)));
  const cid = h("input", { id: "f-client", value: clientId, placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", autocomplete: "off", spellcheck: "false" });
  const redirect = h("input", { value: redirectUri(), readonly: true });
  const copy = h("button", { type: "button", class: "small", onclick: () => navigator.clipboard?.writeText(redirect.value).then(() => status("Redirect URI copied", "ok")) }, "Copy");
  const go = h("button", { class: "accent", type: "button", onclick: () => startPkce(sel.value, cid.value.trim()) }, "Sign in with Genesys Cloud");
  cid.addEventListener("keydown", (e) => { if (e.key === "Enter") go.click(); });
  const box = $("connect");
  box.replaceChildren(h("div", { class: "card" },
    h("h1", {}, "Your Genesys Cloud org, as tables you can export"),
    h("p", {}, `${S.catalog.endpoints.length} read-only reports: users with their queues and roles, routing, telephony, Architect, outbound, quality, WFM and more, as CSV or JSON. The page talks to the Genesys Cloud API straight from your browser; nothing goes anywhere else.`),
    h("div", { class: "form-row" }, h("label", { for: "f-region" }, "Region"), sel),
    h("div", { class: "form-row" }, h("label", { for: "f-client" }, "OAuth client ID"), cid),
    h("div", { class: "form-actions" }, go),
    error ? h("div", { class: "error" }, error) : null,
    h("h3", {}, "First time? An admin creates the OAuth client once"),
    h("ol", { class: "steps" },
      h("li", {}, "Admin › Integrations › OAuth › Add client."),
      h("li", {}, "Grant type: Code Authorization with PKCE (no secret)."),
      h("li", {}, "Authorized redirect URI:", h("div", { class: "copy-field" }, redirect, copy)),
      h("li", {}, "Save, and give everyone who should run reports the client ID. Each person signs in with their own account and sees only what their roles allow.")),
    h("p", { class: "note" }, "Prefer client credentials, or no browser at all? The desktop app and ", h("code", {}, "pyramid web"),
      " use saved Client Credentials clients: ", h("a", { href: "https://github.com/igtoth/pyramid/releases/latest" }, "download Pyramid"), "."),
  ));
  box.hidden = false;
  $("workspace").hidden = true;
  cid.focus();
}

async function startPkce(region, clientId) {
  if (!/^[0-9a-f-]{36}$/i.test(clientId)) return showConnectHosted("The client ID should look like xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.");
  store.set("localStorage", "region", region);
  store.set("localStorage", "clientId", clientId);
  const verifier = pkceVerifier(64);
  const state = pkceVerifier(16);
  store.set("sessionStorage", "pkce", JSON.stringify({ verifier, state, region, clientId }));
  const q = new URLSearchParams({
    client_id: clientId, redirect_uri: redirectUri(), response_type: "code",
    code_challenge: await pkceChallenge(verifier), code_challenge_method: "S256", state,
  });
  location.assign(`${loginBase(region)}/oauth/authorize?${q}`);
}

async function finishPkce(q) {
  history.replaceState(null, "", location.pathname);
  let pk = null;
  try { pk = JSON.parse(store.get("sessionStorage", "pkce") || "null"); } catch { /* ignore */ }
  store.set("sessionStorage", "pkce", null);
  if (q.get("error")) return showConnectHosted(`Sign-in failed: ${q.get("error_description") || q.get("error")}`);
  if (!pk || pk.state !== q.get("state")) return showConnectHosted("Sign-in could not be verified (state mismatch). Try again.");
  status("Signing in...", "busy");
  try {
    const resp = await fetch(`${loginBase(pk.region)}/oauth/token`, {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "authorization_code", code: q.get("code"), code_verifier: pk.verifier,
        client_id: pk.clientId, redirect_uri: redirectUri() }),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok || !body.access_token) throw new Error(body.error_description || body.error || `HTTP ${resp.status}`);
    store.set("sessionStorage", "token", JSON.stringify({ accessToken: body.access_token, region: pk.region,
      expiresAt: Date.now() + (body.expires_in || 3600) * 1000 }));
    connectHosted(pk.region);
  } catch (e) {
    showConnectHosted(`Sign-in failed: ${e.message}. Check that the OAuth client uses the PKCE grant and that the redirect URI matches exactly.`);
  }
}

function connectHosted(region) {
  S.region = region;
  S.api = new Api({
    base: apiHost(region),
    headers: () => ({ Authorization: "Bearer " + (token()?.accessToken || "") }),
    onProgress: (t) => status(t, "busy"),
    onUnauthorized: () => store.set("sessionStorage", "token", null),
  });
  openWorkspace();
}

function signOut() {
  if (S.mode === "local") return showConnectLocal({ clients: S.localClients });
  store.set("sessionStorage", "token", null);
  S.cache.clear();
  closeAllTabs(false);
  $("org").hidden = true;
  $("btn-signout").hidden = true;
  showConnectHosted();
}

// ── local mode (pyramid web) ──────────────────────────────────────────────
function showConnectLocal(info) {
  const clients = info.clients || [];
  const box = $("connect");
  $("workspace").hidden = true;
  $("org").hidden = true;
  $("btn-signout").hidden = true;
  const sel = h("select", { id: "f-local" }, clients.map((c) => h("option", { value: c.name }, `${c.name}  ·  ${c.region}`)));
  if (info.last) sel.value = info.last;
  box.replaceChildren(h("div", { class: "card" },
    h("h1", {}, "Pyramid on this computer"),
    h("p", {}, "The OAuth clients saved in the desktop app. The secret stays in the Pyramid process on this computer; the browser never sees it."),
    clients.length
      ? [h("div", { class: "form-row" }, h("label", { for: "f-local" }, "Client"), sel),
         h("div", { class: "form-actions" }, h("button", { class: "accent", type: "button", onclick: () => connectLocal(sel.value) }, "Connect"))]
      : h("p", { class: "error" }, "No saved clients yet: add one in the desktop app (OAuth tab), then reload this page."),
  ));
  box.hidden = false;
}

function connectLocal(name) {
  const c = S.localClients.find((x) => x.name === name);
  S.clientName = name;
  S.region = c?.region || "";
  S.api = new Api({ base: `local/api/${encodeURIComponent(name)}`, onProgress: (t) => status(t, "busy") });
  S.cache.clear();
  closeAllTabs(false);
  openWorkspace();
}

// ── workspace: Reports + one sub-tab per report ───────────────────────────
async function openWorkspace() {
  $("connect").hidden = true;
  $("workspace").hidden = false;
  $("btn-signout").hidden = false;
  $("btn-signout").textContent = S.mode === "local" ? "Switch client" : "Sign out";
  status("Connecting...", "busy");
  try {
    const org = await S.api.get("/api/v2/organizations/me");
    S.orgName = org.name || "";
    status(`Connected to ${S.orgName}`, "ok");
  } catch (e) {
    if (S.mode === "hosted" && e.status === 401) return showConnectHosted("Your session expired. Sign in again.");
    status(`Error: ${e.message}`, "err");
    S.orgName = S.clientName || "";
  }
  const org = $("org");
  org.textContent = `● ${S.orgName}${S.mode === "local" ? `  ·  ${S.clientName}` : ""}  ·  ${S.region}`;
  org.hidden = false;
  select(null);
}

function renderTabs() {
  const bar = $("subtabs");
  const tab = (label, t) => {
    const active = S.current === t;
    const el = h("div", { class: `tab${t ? "" : " home"}${active ? " active" : ""}`, role: "tab", tabindex: "0", "aria-selected": String(active),
      title: t ? `${t.res.endpoint.label} · fetched ${t.res.fetchedAt.replace("T", " ")}` : "All reports",
      onclick: () => select(t), onkeydown: (e) => { if (e.key === "Enter") select(t); },
      onauxclick: (e) => { if (t && e.button === 1) closeTab(t); } },
    h("span", { class: "label" }, label));
    if (t) el.append(h("button", { class: "close", type: "button", "aria-label": `Close ${label}`, onclick: (e) => { e.stopPropagation(); closeTab(t); } }, "✕"));
    return el;
  };
  const kids = [tab("▦  Reports", null), ...S.tabs.map((t) => tab(t.res.endpoint.label, t))];
  if (S.tabs.length) kids.push(h("button", { class: "ghost small closeall", type: "button", onclick: () => closeAllTabs(true) }, "Close all"));
  bar.replaceChildren(...kids);
}

function select(t) {
  S.current = t;
  const stack = $("stack");
  for (const el of stack.children) el.hidden = true;
  if (!t) {
    stack.querySelector(".home")?.remove();
    stack.append(renderHome());
  } else {
    if (!t.el) { t.el = renderReport(t); stack.append(t.el); }
    t.el.hidden = false;
  }
  renderTabs();
}

function openTab(res) {
  let t = S.tabs.find((x) => x.res.endpoint.key === res.endpoint.key);
  if (t) { t.res = res; t.el?.remove(); t.el = null; }
  else {
    t = { res, el: null };
    S.tabs.push(t);
    while (S.tabs.length > MAX_TABS) closeTab(S.tabs.find((x) => x !== t), false);
  }
  select(t);
}

function closeTab(t, reselect = true) {
  const i = S.tabs.indexOf(t);
  if (i < 0) return;
  S.tabs.splice(i, 1);
  t.el?.remove();
  if (!reselect) return;
  if (S.current === t) select(S.tabs[Math.min(i, S.tabs.length - 1)] || null); else renderTabs();
}

function closeAllTabs(reselect) {
  for (const t of S.tabs) t.el?.remove();
  S.tabs = [];
  if (reselect) select(null);
}

function renderHome() {
  const view = h("div", { class: "view home" });
  view.append(h("div", { class: "banner" }, h("b", {}, `● ${S.orgName}`),
    `${S.catalog.endpoints.length} reports · each opens in its own tab · ⚡ already fetched (Refresh fetches again)`));
  const grid = h("div", { class: "grid" });
  for (const s of S.catalog.sections) {
    grid.append(h("div", { class: "section", style: `--c: var(--s${s.color % 6})` },
      h("h3", {}, `${s.icon}  ${s.name}`),
      S.catalog.endpoints.filter((e) => e.section === s.id).map((ep) =>
        h("button", { type: "button", title: ep.help, disabled: S.busy, onclick: () => openReport(ep) },
          S.cache.has(ep.key) ? h("span", { class: "cached" }, "⚡") : null, ep.label))));
  }
  view.append(grid);
  return view;
}

async function openReport(ep, force = false) {
  if (!force && S.cache.has(ep.key)) {
    status("⚡ From memory (Refresh to fetch again)", "ok");
    return openTab(S.cache.get(ep.key));
  }
  if (S.busy) return status("Another request is running; cancel it first", "warn");
  if (ep.slow && !force && !confirm(`${ep.help}\n\nThis can take several minutes in a large org. Continue?`)) return;
  setBusy(true);
  S.abort = new AbortController();
  status(`${ep.label}...`, "busy");
  try {
    const res = await fetchReport(S.api, ep, S.abort.signal);
    S.cache.set(ep.key, res);
    status(`✓ ${ep.label}: ${ep.kind === "object" ? "fetched" : res.count + " records"}, ${res.calls} API calls`, "ok");
    openTab(res);
  } catch (e) {
    if (e instanceof Cancelled) status("Cancelled", "warn");
    else {
      status(`Error: ${e.message}`, "err");
      if (S.mode === "hosted" && e.status === 401) showConnectHosted("Your session expired. Sign in again.");
      else if (e.status === 403) status(`Error: ${e.message} (the roles of your account lack a permission for this report)`, "err");
    }
  } finally {
    setBusy(false);
    if (!S.current) select(null);
  }
}

function setBusy(b) {
  S.busy = b;
  $("progress").hidden = !b;
  $("btn-cancel").hidden = !b;
  document.querySelectorAll(".home .section button").forEach((x) => { x.disabled = b; });
}

function renderReport(t) {
  const res = t.res, ep = res.endpoint;
  let cols, rows, records = null;
  if (ep.kind === "object") {
    cols = [{ header: "Key", path: "k" }, { header: "Value", path: "v" }];
    rows = flattenObject(res.obj);
  } else {
    cols = tableColumns(ep.columns, res.records);
    rows = rowsOf(res.records, cols);
    records = res.records;
  }
  const st = { order: rows.map((_, i) => i), visible: [], sortCol: null, rev: false, limit: ROW_CHUNK };
  const count = h("span", { class: "count" });
  const search = h("input", { type: "search", placeholder: "Search every column", "aria-label": "Search" });
  const thead = h("thead");
  const tbody = h("tbody");
  const more = h("button", { class: "more", type: "button", hidden: true, onclick: () => { st.limit += ROW_CHUNK; draw(); } }, "Show more rows");
  const unit = records ? "records" : "fields";

  function apply() {
    const q = search.value.trim().toLowerCase();
    st.visible = st.order.filter((i) => !q || rows[i].some((v) => v.toLowerCase().includes(q)));
    st.limit = ROW_CHUNK;
    draw();
  }
  function draw() {
    const shown = st.visible.slice(0, st.limit);
    tbody.replaceChildren(...shown.map((i) => h("tr", { "data-i": i },
      h("td", { class: "num" }, i + 1), rows[i].map((v) => h("td", { title: v.length > 60 ? v : null }, v)))));
    more.hidden = st.visible.length <= st.limit;
    more.textContent = `Show more rows (${st.limit} of ${st.visible.length} shown)`;
    count.textContent = st.visible.length === rows.length ? `${rows.length} ${unit}` : `${st.visible.length} of ${rows.length} ${unit}`;
  }
  function sortBy(c) {
    st.rev = st.sortCol === c ? !st.rev : false;
    st.sortCol = c;
    const key = (i) => { const v = rows[i][c]; const n = Number(v); return v !== "" && !Number.isNaN(n) ? [0, n, ""] : [1, 0, v.toLowerCase()]; };
    st.order = rows.map((_, i) => i).sort((a, b) => {
      const ka = key(a), kb = key(b);
      const r = ka[0] - kb[0] || ka[1] - kb[1] || (ka[2] < kb[2] ? -1 : ka[2] > kb[2] ? 1 : 0);
      return st.rev ? -r : r;
    });
    header();
    apply();
  }
  function header() {
    thead.replaceChildren(h("tr", {}, h("th", { class: "num" }, "#"),
      cols.map((c, j) => h("th", { onclick: () => sortBy(j), scope: "col", "aria-sort": st.sortCol === j ? (st.rev ? "descending" : "ascending") : null },
        c.header + (st.sortCol === j ? (st.rev ? " ▼" : " ▲") : "")))));
  }
  tbody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (tr) showRecord(ep, records ? records[+tr.dataset.i] : null, rows[+tr.dataset.i]);
  });
  search.addEventListener("input", apply);
  header();
  apply();

  const stamp = res.fetchedAt.replace("T", " ");
  const visibleRows = () => st.visible.map((i) => rows[i]);
  return h("div", { class: "view report" },
    h("div", { class: "rhead" },
      h("h2", {}, ep.label), count, h("span", { class: "meta" }, `${S.orgName} · fetched ${stamp} · ${res.calls} API calls`),
      h("div", { class: "actions" },
        h("button", { class: "ghost", type: "button", title: "Fetch again (Alt+R)", onclick: () => openReport(ep, true) }, "🔄 Refresh"),
        h("button", { class: "ghost", type: "button", title: "The API's own JSON, page by page", onclick: () => download(fileName(ep, "json"), JSON.stringify(res.raw, null, 2), "application/json") }, "⬇ Raw JSON"),
        h("button", { class: "accent", type: "button", title: "What you see: filter and order included", onclick: () => {
          const vr = visibleRows();
          download(fileName(ep, "csv"), toCSV(cols.map((c) => c.header), vr), "text/csv;charset=utf-8");
          status(`✓ ${vr.length} rows exported${vr.length !== rows.length ? " (filtered)" : ""}`, "ok");
        } }, "⬇ Export CSV"))),
    h("div", { class: "searchbar" }, "🔍", search,
      h("span", { class: "hint" }, `click a row for every field${ep.actions.includes("members") ? " and the queue members" : ""} · Alt+W closes the tab · Esc back to Reports`)),
    h("div", { class: "tablewrap" }, h("table", {}, thead, tbody)),
    more);
}

function fileName(ep, ext) {
  const org = (S.orgName || "org").replace(/[^A-Za-z0-9_-]+/g, "_");
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${org}_${ep.key}_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}.${ext}`;
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function dialog(title, ...body) {
  $("dialog-title").textContent = title;
  $("dialog-body").replaceChildren(...body);
  const d = $("dialog");
  if (!d.open) d.showModal();
}

function showRecord(ep, record, row) {
  const title = `${ep.label}: ${row[0] || ""}`;
  if (!record) return dialog(title, h("pre", {}, `${row[0]}\n\n${row[1]}`));
  const parts = [h("pre", {}, JSON.stringify(record, null, 2))];
  if (ep.actions.includes("members")) {
    const btn = h("button", { class: "accent", type: "button", style: "margin-bottom:10px" }, "Show queue members");
    btn.onclick = async () => {
      btn.disabled = true;
      status(`Members of ${record.name}...`, "busy");
      try {
        const members = await queueMembers(S.api, record.id);
        const hdr = ["Name", "Routing Status", "Joined", "Member By", "User ID"];
        const mrows = members.map((m) => [cell(m.name), cell(resolve(m, "routingStatus.status")), cell(m.joined), cell(m.memberBy), cell(m.id)]);
        dialog(`Members of ${record.name} (${members.length})`,
          h("button", { type: "button", onclick: () => download(`members_${(record.name || "queue").replace(/\W+/g, "_")}.csv`, toCSV(hdr, mrows), "text/csv") }, "⬇ Export CSV"),
          h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, hdr.map((x) => h("th", {}, x)))),
            h("tbody", {}, mrows.map((r) => h("tr", {}, r.map((v) => h("td", {}, v))))))));
        status(`✓ ${members.length} members in ${record.name}`, "ok");
      } catch (e) {
        status(`Error: ${e.message}`, "err");
        btn.disabled = false;
      }
    };
    parts.unshift(btn);
  }
  dialog(title, ...parts);
}

function showHelp() {
  const items = [
    ["Reports", "Every button on the Reports tab reads one kind of object from your org and opens it in its own tab. Reopening a report shows the copy already fetched (⚡); Refresh asks the API again."],
    ["Search, sort, export", "The search box filters every column; click a header to sort (numbers sort as numbers). Export CSV saves what you see, filter and order included; Raw JSON saves the API's own answer."],
    ["Privacy", "Hosted page: your browser talks to Genesys Cloud directly, with the token of your own sign-in, kept only in this tab's session storage. Local page (pyramid web): the Pyramid process on your computer adds the token."],
    ["Rate limits", "When Genesys Cloud answers 429 (too many requests) or a temporary 5xx, Pyramid waits as asked and retries; Cancel stops it."],
    ["Keyboard", "Esc: back to Reports · Alt+W: close the tab · Alt+R: refresh · / : search"],
    ["Desktop and command line", "The same reports run in the desktop app for Windows, macOS and Linux, and from the command line (pyramid export ...). github.com/igtoth/pyramid"],
  ];
  dialog("Pyramid help", h("div", { class: "help" }, items.map(([t, d]) => [h("h4", {}, t), h("p", {}, d)])));
}

function onKey(e) {
  if ($("dialog").open) return;
  if (e.key === "Escape" && S.current) { select(null); e.preventDefault(); }
  else if (e.altKey && (e.key === "w" || e.key === "W") && S.current) { closeTab(S.current); e.preventDefault(); }
  else if (e.altKey && (e.key === "r" || e.key === "R") && S.current) { openReport(S.current.res.endpoint, true); e.preventDefault(); }
  else if (e.key === "/" && S.current && document.activeElement?.tagName !== "INPUT") {
    S.current.el?.querySelector("input[type=search]")?.focus();
    e.preventDefault();
  }
}

init().catch((e) => { status(`Error: ${e.message}`, "err"); console.error(e); });

export { S as state, ApiError };
