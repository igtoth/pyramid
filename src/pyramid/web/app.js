// Pyramid web: the desktop app's layout (Main, OAuth, Config, Log, Help,
// About, status bar) in the browser. Two ways in, one page:
//  - hosted (GitHub Pages): orgs saved in this browser only; sign in with your
//    Genesys Cloud account (OAuth PKCE); the page calls the API itself.
//  - local ("pyramid web"): Client Credentials clients in pyramid.cfg, edited
//    here as in the desktop app; the local server gets and adds the token,
//    and never sends a saved secret back to the page.
//  - demo (the published site, data-mode="demo"): a made-up org answered
//    inside the page (demo.js); nothing is sent anywhere.
import {
  API_HOSTS, Api, ApiError, Cancelled, cell, fetchReport, flattenObject, loginHost, normalizeCatalog,
  pkceChallenge, pkceVerifier, queueMembers, resolve, rowsOf, tableColumns, toCSV,
} from "./core.js";
import { DEMO_CLIENT, DEMO_TOKEN, demoApi, demoSignIn } from "./demo.js";

const VERSION = "3.0.0";
const REPO = "https://github.com/igtoth/pyramid";
const MAX_TABS = 12;
const ROW_CHUNK = 2000;
const LEVELS = ["DEBUG", "INFO", "OK", "WARN", "ERROR"];

const store = {
  get(area, k) { try { return window[area].getItem("pyramid." + k); } catch { return null; } },
  set(area, k, v) { try { v === null ? window[area].removeItem("pyramid." + k) : window[area].setItem("pyramid." + k, v); } catch { /* blocked */ } },
};

const S = {
  catalog: null, mode: "hosted", api: null, connected: false, orgName: "", clientName: "", region: "",
  tabs: [], current: null, cache: new Map(), busy: false, abort: null, localClients: [],
  log: [], logLevel: "INFO", top: "main", editing: null,
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
    } else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}
const $ = (id) => document.getElementById(id);

// ── status bar and Log tab ────────────────────────────────────────────────
function log(level, msg) {
  const ts = new Date().toTimeString().slice(0, 8);
  S.log.push([ts, level, msg]);
  if (S.log.length > 5000) S.log.splice(0, S.log.length - 5000);
  const box = $("log-lines");
  if (box && LEVELS.indexOf(level) >= LEVELS.indexOf(S.logLevel)) {
    box.append(h("div", { class: `ll ${level}` }, `${ts}  ${level.padEnd(5)}  ${msg}`));
    box.scrollTop = box.scrollHeight;
  }
}

function status(text, kind = "") {
  const el = $("status");
  el.textContent = text;
  el.className = kind;
  const level = { ok: "OK", err: "ERROR", warn: "WARN", busy: "DEBUG" }[kind] || "INFO";
  log(level, text);
}

function clientLabel() {
  const el = $("client-label");
  if (S.connected) {
    const extra = S.clientName && S.clientName !== S.orgName ? `  ·  ${S.clientName}` : "";
    el.textContent = `●  ${S.orgName}${extra}  ·  ${S.region}`;
    el.className = "ok";
  } else {
    el.textContent = "No client selected";
    el.className = "warn";
  }
}

// ── theme ─────────────────────────────────────────────────────────────────
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  $("btn-theme").textContent = isDark() ? "☀ Light" : "☾ Dark";
}
function setTheme(t) {
  applyTheme(t);
  store.set("localStorage", "theme", t);
  if (S.top === "config") renderConfig();
}

// ── top tabs ──────────────────────────────────────────────────────────────
const RENDER = { main: () => (S.current ? null : select(null)), oauth: () => renderOAuth(), config: () => renderConfig(),
  log: () => renderLog(), help: () => renderHelp(), about: () => renderAbout() };

function showTab(name) {
  S.top = name;
  for (const b of document.querySelectorAll("#maintabs [data-tab]")) {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  }
  for (const p of document.querySelectorAll(".tabpanel")) p.hidden = p.id !== `tab-${name}`;
  if (name !== "about") stopSieve();
  RENDER[name]?.();
}

// ── start ─────────────────────────────────────────────────────────────────
async function init() {
  if (window.top !== window.self) {  // no framing (GitHub Pages cannot send X-Frame-Options)
    document.body.textContent = "Pyramid cannot be shown inside another page.";
    return;
  }
  applyTheme(store.get("localStorage", "theme"));
  $("btn-theme").onclick = () => setTheme(isDark() ? "light" : "dark");
  $("btn-cancel").onclick = () => S.abort?.abort();
  for (const b of document.querySelectorAll("#maintabs [data-tab]")) b.onclick = () => showTab(b.dataset.tab);
  document.addEventListener("keydown", onKey);
  S.catalog = normalizeCatalog(await (await fetch("catalog.json")).json());
  log("INFO", `Pyramid web ${VERSION} started`);
  // an earlier version kept the last region and client ID silently: drop them
  store.set("localStorage", "region", null);
  store.set("localStorage", "clientId", null);

  if (document.documentElement.dataset.mode === "demo") return startDemo();
  // "pyramid web" marks the page it serves; the hosted page never asks
  const local = document.documentElement.dataset.mode === "local"
    ? await fetch("local/info", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
    : null;
  if (local?.mode === "local") {
    S.mode = "local";
    S.localClients = local.clients || [];
    S.editing = local.last || S.localClients[0]?.name || null;
    showTab(S.localClients.length ? "main" : "oauth");
    return;
  }
  const q = new URLSearchParams(location.search);
  // Tests and demos against tests/fake_genesys.py: only for a page itself served from this computer,
  // never with a token around (it would be sent to that address), and it drops any token.
  const pageIsLocal = ["127.0.0.1", "localhost"].includes(location.hostname);
  if (pageIsLocal && q.get("api") && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(q.get("api"))) {
    store.set("sessionStorage", "token", null);
    store.set("sessionStorage", "devBase", q.get("api"));
    history.replaceState(null, "", location.pathname);
  }
  if (!pageIsLocal) store.set("sessionStorage", "devBase", null);
  if (q.has("code") || q.has("error")) return finishPkce(q);
  const tok = token();
  showTab("main");
  if (tok) connectHosted(tok.region, tok.name);
}

function devBase() { return ["127.0.0.1", "localhost"].includes(location.hostname) ? store.get("sessionStorage", "devBase") : null; }
function apiHost(region) { return devBase() || API_HOSTS[region]; }
function loginBase(region) { return devBase() || loginHost(API_HOSTS[region]); }
function redirectUri() { return location.origin + location.pathname; }

function token() {
  try {
    const t = JSON.parse(store.get("sessionStorage", "token") || "null");
    return t && t.expiresAt > Date.now() + 60_000 ? t : null;
  } catch { return null; }
}

// ── saved orgs (hosted): this browser only ────────────────────────────────
// sessionStorage by default; localStorage when "Remember on this browser".
const ORGS = "orgs";

function readOrgs(area) {
  try { return JSON.parse(store.get(area, ORGS) || "[]").filter((o) => o && o.name && o.region && o.clientId); }
  catch { return []; }
}
function loadOrgs() {
  const byName = new Map();
  for (const { name, region, clientId } of readOrgs("localStorage")) byName.set(name, { name, region, clientId, remember: true });
  for (const { name, region, clientId } of readOrgs("sessionStorage")) byName.set(name, { name, region, clientId, remember: false });
  return [...byName.values()].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
}
function saveOrgs(orgs) {
  const pick = (list) => list.map(({ name, region, clientId }) => ({ name, region, clientId }));
  const local = pick(orgs.filter((o) => o.remember)), session = pick(orgs.filter((o) => !o.remember));
  store.set("localStorage", ORGS, local.length ? JSON.stringify(local) : null);
  store.set("sessionStorage", ORGS, session.length ? JSON.stringify(session) : null);
}
function forgetEverything() {
  for (const area of ["localStorage", "sessionStorage"]) {
    try {
      const keys = [];
      for (let i = 0; i < window[area].length; i++) if (window[area].key(i).startsWith("pyramid.")) keys.push(window[area].key(i));
      keys.forEach((k) => window[area].removeItem(k));
    } catch { /* storage blocked: nothing to forget */ }
  }
}

const PRIVACY = () => S.mode === "demo"
  ? h("div", { class: "privacy demo" }, h("b", {}, "Demo: nothing leaves this page. "),
    "Any Name, Client ID and secret \"connect\" to a made-up org (Lumen Harbor Telecom) answered inside the page. Nothing is sent to Genesys Cloud or anywhere else, and nothing is saved.")
  : h("div", { class: "privacy" }, h("b", {}, "Nothing is stored on any server. "),
  S.mode === "local"
    ? "Clients are saved in pyramid.cfg on this computer, the same file the desktop app uses. A secret you type goes to the Pyramid process once and is never sent back to the page; the process gets the token and adds it to each request."
    : "Pyramid has no server: this page runs in your browser and talks only to Genesys Cloud. The clients you add stay in this browser (this tab only, unless you tick Remember) and the token stays in this tab. Sign out or Forget everything (Config tab) clears it all.");

const HOSTED_SECRET = "Not on this web page: Genesys Cloud blocks the Client secret in browsers";

// "pyramid web": the Pyramid process keeps the clients (pyramid.cfg)
async function localPost(path, body) {
  const resp = await fetch(path, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Pyramid": "1" }, body: JSON.stringify(body) });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.message || `HTTP ${resp.status}`);
  return data;
}
// demo: the same calls, answered in memory
async function demoPost(path, body) {
  if (path === "local/test") {
    await demoSignIn();
    return { org: "Lumen Harbor Telecom", region: body.region, expiresIn: 86399 };
  }
  if (path === "local/clients") {
    const rest = S.localClients.filter((c) => c.name !== body.oldName && c.name !== body.name);
    S.localClients = [...rest, { name: body.name, region: body.region, clientId: body.clientId, hasSecret: true }]
      .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  } else if (path === "local/clients/delete") {
    S.localClients = S.localClients.filter((c) => c.name !== body.name);
  }
  return { clients: S.localClients };
}
const backendPost = (path, body) => (S.mode === "demo" ? demoPost(path, body) : localPost(path, body));

function localOrgs() {
  return S.localClients.map((c) => ({ name: c.name, region: c.region, clientId: c.clientId || "", hasSecret: !!c.hasSecret }));
}

// ── OAuth tab (both modes, as in the desktop app) ─────────────────────────
function renderOAuth(error) {
  const panel = $("tab-oauth");
  const local = S.mode === "local" || S.mode === "demo";  // the desktop's form, secret included
  const demo = S.mode === "demo";
  const orgs = () => (local ? localOrgs() : loadOrgs());
  let current = orgs().find((o) => o.name === S.editing) || (S.editing === "" ? null : orgs()[0]) || null;

  const name = h("input", { id: "f-name", placeholder: "e.g. Prod, Lab, Customer X", autocomplete: "off", maxlength: "60" });
  const sel = h("select", { id: "f-region" }, Object.keys(API_HOSTS).map((r) => h("option", { value: r }, r)));
  const cid = h("input", { id: "f-client", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", autocomplete: "off", spellcheck: "false" });
  const secret = h("input", { id: "f-secret", type: "password", autocomplete: "new-password", spellcheck: "false",
    disabled: !local, placeholder: local ? "" : HOSTED_SECRET });
  const show = h("input", { id: "f-show", type: "checkbox", disabled: !local, onchange: () => { secret.type = show.checked ? "text" : "password"; } });
  const remember = h("input", { id: "f-remember", type: "checkbox" });
  const formError = h("div", { class: "error", hidden: !error, role: "alert" }, error || "");
  const list = h("div", { class: "clientlist", role: "listbox", "aria-label": "Saved clients" });
  const del = h("button", { class: "danger", type: "button" }, "Delete");
  const fail = (msg) => { formError.textContent = msg; formError.hidden = !msg; if (msg) status(msg, "err"); };

  function fill(o) {
    current = o;
    S.editing = o ? o.name : "";
    name.value = o?.name || "";
    sel.value = o?.region || "us_east_1";
    cid.value = o?.clientId || "";
    secret.value = "";
    if (local) secret.placeholder = o?.hasSecret ? "saved (leave empty to keep it)" : "the client's secret";
    remember.checked = !!o?.remember;
    del.disabled = !o;
    for (const b of list.querySelectorAll("[data-name]")) b.classList.toggle("active", b.dataset.name === o?.name);
  }
  function renderList() {
    const items = orgs().map((o) => h("div", { class: "item", "data-name": o.name, role: "option", tabindex: "0",
      onclick: () => fill(o), onkeydown: (e) => { if (e.key === "Enter") fill(o); } },
    o.name, h("small", {}, demo ? `${o.region} · demo` : local ? `${o.region} · pyramid.cfg` : `${o.region} · ${o.remember ? "remembered" : "this tab only"}`)));
    list.replaceChildren(...(items.length ? items : [h("p", { class: "note" }, "No saved clients yet.")]));
  }
  function formOrg() {
    const o = { name: name.value.trim(), region: sel.value, clientId: cid.value.trim(), remember: remember.checked };
    if (local) Object.assign(o, { secret: secret.value.trim(), oldName: current?.name || "" });
    const problem = !o.name ? "Give the client a name (any label you like)."
      : !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(o.clientId)
        ? "The Client ID should look like xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx."
        : local && !o.secret && !(current?.hasSecret && current.clientId === o.clientId) ? "Type the Client secret." : "";
    fail(problem);
    return problem ? null : o;
  }
  async function save(o) {
    if (local) {
      const info = await backendPost("local/clients", o);
      S.localClients = info.clients || [];
    } else {
      const all = loadOrgs().filter((x) => x.name !== o.name && x.name !== current?.name);
      all.push({ name: o.name, region: o.region, clientId: o.clientId, remember: o.remember });
      saveOrgs(all);
    }
    S.editing = o.name;
    renderList();
    fill(orgs().find((x) => x.name === o.name) || null);
  }
  const guarded = (fn) => async () => { const o = formOrg(); if (!o) return; try { await fn(o); } catch (e) { fail(e.message); } };
  const signin = h("button", { class: "accent", type: "button", onclick: guarded(async (o) => {
    await save(o);
    if (demo) connectDemo(o.name);
    else if (local) { localPost("local/last", { name: o.name }).catch(() => {}); connectLocal(o.name); } else await startPkce(o);
  }) }, "Save and use");
  const test = h("button", { type: "button", onclick: guarded(async (o) => {
    if (!local) { status("On this page the connection is tested by signing in: Save and use", "warn"); return; }
    status("Testing connection...", "busy");
    const r = await backendPost("local/test", o);
    const msg = `Connected to ${r.org} (${r.region}). Token valid for ${Math.floor(r.expiresIn / 3600)}h ${Math.floor((r.expiresIn % 3600) / 60)}m.`;
    fail("");
    status("✓  " + msg, "ok");
    dialog("Connection OK", h("p", {}, msg));
  }) }, "Test connection");
  const keep = h("button", { type: "button", onclick: guarded(async (o) => { await save(o); status(`✓  Client ${o.name} saved`, "ok"); }) }, "Save");
  del.onclick = async () => {
    if (!current || !confirm(`Delete the saved client "${current.name}"${demo ? "" : local ? " from pyramid.cfg" : " from this browser"}?`)) return;
    try {
      if (local) S.localClients = (await backendPost("local/clients/delete", { name: current.name })).clients || [];
      else saveOrgs(loadOrgs().filter((x) => x.name !== current.name));
    } catch (e) { return fail(e.message); }
    status(`Client ${current.name} deleted`, "ok");
    renderList();
    fill(orgs()[0] || null);
  };
  for (const el of [name, cid, secret]) el.addEventListener("keydown", (e) => { if (e.key === "Enter") signin.click(); });
  const redirect = h("input", { value: redirectUri(), readonly: true });

  const note = demo
    ? h("p", { class: "note" }, "To use Pyramid with your own org, download the desktop app (",
      h("a", { href: `${REPO}/releases`, target: "_blank", rel: "noopener" }, "releases"), ") or run ", h("code", {}, "pyramid web"),
      ": same page, on your computer, with a real Client Credentials client.")
    : local
    ? h("p", { class: "note" }, "Client Credentials clients, as in the desktop app: what Pyramid can read comes from the role given to the client.")
    : h("p", { class: "note" }, "On this page you sign in on the Genesys login page with your own account (PKCE client) and see only what your roles allow. A Client secret only works in the desktop app or in ",
      h("code", {}, "pyramid web"), " (same page, run on your computer): Genesys Cloud does not let a web page use it.");
  const steps = local
    ? [h("li", {}, "Admin › Integrations › OAuth › Add client."),
      h("li", {}, "Grant type: Client Credentials; give it a role that can read what you want to export."),
      h("li", {}, "Save, and copy the Client ID and the Client secret here.")]
    : [h("li", {}, "Admin › Integrations › OAuth › Add client."),
      h("li", {}, "Grant type: Code Authorization with PKCE."),
      h("li", {}, "Authorized redirect URI:", h("div", { class: "copy-field" }, redirect,
        h("button", { type: "button", class: "small", onclick: () => navigator.clipboard?.writeText(redirect.value).then(() => status("Redirect URI copied", "ok")) }, "Copy"))),
      h("li", {}, "Save, and share the Client ID with the people who should run reports.")];

  panel.replaceChildren(h("div", { class: "oauth" },
    h("div", { class: "pane clients" },
      h("h3", {}, "Saved clients"), list,
      h("div", { class: "row-btns" },
        h("button", { type: "button", onclick: () => { fill(null); name.focus(); } }, "＋ New"), del)),
    h("div", { class: "pane details" },
      h("h3", {}, "Client details"),
      PRIVACY(),
      h("div", { class: "form-row" }, h("label", { for: "f-name" }, "Name"), name),
      h("div", { class: "form-row" }, h("label", { for: "f-region" }, "Region"), sel),
      h("div", { class: "form-row" }, h("label", { for: "f-client" }, "Client ID"), cid),
      h("div", { class: "form-row" }, h("label", { for: "f-secret" }, "Client secret"), secret),
      h("div", { class: "form-row" }, h("span", {}), h("label", { class: "check" + (local ? "" : " muted") }, show, " Show secret")),
      local ? null : h("div", { class: "form-row" }, h("span", {}),
        h("label", { class: "check" }, remember, " Remember on this browser ", h("small", {}, "(otherwise only until this tab closes)"))),
      formError,
      h("div", { class: "form-actions" }, signin, test, keep,
        S.connected ? h("button", { type: "button", class: "ghost", onclick: signOut }, local ? "Disconnect" : "Sign out") : null),
      note,
      h("details", { class: "admin" },
        h("summary", {}, "First time? An admin creates the OAuth client once"),
        h("ol", { class: "steps" }, ...steps)))));
  renderList();
  fill(current);
}

// ── sign-in ───────────────────────────────────────────────────────────────
async function startPkce(org) {
  const verifier = pkceVerifier(64);
  const state = pkceVerifier(16);
  store.set("sessionStorage", "pkce", JSON.stringify({ verifier, state, region: org.region, clientId: org.clientId, name: org.name }));
  const q = new URLSearchParams({
    client_id: org.clientId, redirect_uri: redirectUri(), response_type: "code",
    code_challenge: await pkceChallenge(verifier), code_challenge_method: "S256", state,
  });
  location.assign(`${loginBase(org.region)}/oauth/authorize?${q}`);
}

async function finishPkce(q) {
  history.replaceState(null, "", location.pathname);
  let pk = null;
  try { pk = JSON.parse(store.get("sessionStorage", "pkce") || "null"); } catch { /* ignore */ }
  store.set("sessionStorage", "pkce", null);
  S.editing = pk?.name ?? null;
  const fail = (msg) => { status(msg, "err"); showTab("oauth"); renderOAuth(msg); };
  if (q.get("error")) return fail(`Sign-in failed: ${q.get("error_description") || q.get("error")}`);
  if (!pk || pk.state !== q.get("state")) return fail("Sign-in could not be verified (state mismatch). Try again.");
  status("Signing in...", "busy");
  try {
    const resp = await fetch(`${loginBase(pk.region)}/oauth/token`, {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "authorization_code", code: q.get("code"), code_verifier: pk.verifier,
        client_id: pk.clientId, redirect_uri: redirectUri() }),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok || !body.access_token) throw new Error(body.error_description || body.error || `HTTP ${resp.status}`);
    store.set("sessionStorage", "token", JSON.stringify({ accessToken: body.access_token, region: pk.region, name: pk.name,
      expiresAt: Date.now() + (body.expires_in || 3600) * 1000 }));
    showTab("main");
    connectHosted(pk.region, pk.name);
  } catch (e) {
    fail(`Sign-in failed: ${e.message}. Check that the OAuth client uses the PKCE grant and that the redirect URI matches exactly.`);
  }
}

function connectHosted(region, name = "") {
  S.region = region;
  S.clientName = name || "";
  S.api = new Api({
    base: apiHost(region),
    headers: () => ({ Authorization: "Bearer " + (token()?.accessToken || "") }),
    onProgress: (t) => status(t, "busy"),
    onUnauthorized: () => store.set("sessionStorage", "token", null),
  });
  connect();
}

function connectLocal(name) {
  const c = S.localClients.find((x) => x.name === name);
  S.clientName = name;
  S.region = c?.region || "";
  S.api = new Api({ base: `local/api/${encodeURIComponent(name)}`, onProgress: (t) => status(t, "busy") });
  S.cache.clear();
  closeAllTabs(false);
  showTab("main");
  connect();
}

async function connectDemo(name) {
  const c = S.localClients.find((x) => x.name === name) || DEMO_CLIENT;
  S.clientName = c.name;
  S.region = c.region;
  S.cache.clear();
  closeAllTabs(false);
  showTab("main");
  status(`Signing in to ${c.name}...`, "busy");
  await demoSignIn();
  log("INFO", `Token acquired, valid for 86399s (demo)`);
  S.api = new Api({ base: "https://api.demo.invalid", headers: () => ({ Authorization: `Bearer ${DEMO_TOKEN}` }),
    fetchFn: S.demoFetch, onProgress: (t) => status(t, "busy") });
  return connect();
}

async function startDemo() {
  S.mode = "demo";
  S.localClients = [{ ...DEMO_CLIENT }];
  S.editing = DEMO_CLIENT.name;
  S.demoFetch = await demoApi((path) => log("INFO", `GET ${path}  (demo)`));
  const banner = $("demo-banner");
  banner.replaceChildren(h("b", {}, "DEMO"), " Made-up data from a fictitious org. This page does not connect to Genesys Cloud or to anything else. ",
    h("a", { href: `${REPO}/releases`, target: "_blank", rel: "noopener" }, "Download Pyramid"), " to use it with your org.");
  banner.hidden = false;
  log("WARN", "Demo mode: made-up data, no connection to Genesys Cloud");
  return connectDemo(DEMO_CLIENT.name);
}

async function connect() {
  status("Connecting...", "busy");
  try {
    const org = await S.api.get("/api/v2/organizations/me");
    S.orgName = org.name || S.clientName;
    S.connected = true;
    status(`Connected to ${S.orgName}`, "ok");
  } catch (e) {
    S.connected = false;
    if (S.mode === "hosted" && e.status === 401) store.set("sessionStorage", "token", null);
    status(`Error: ${e.message}`, "err");
  }
  clientLabel();
  if (S.top === "main" && !S.current) select(null);
  if (S.top === "oauth") renderOAuth();
}

function signOut() {
  if (S.mode === "hosted") store.set("sessionStorage", "token", null);
  S.connected = false;
  S.api = null;
  S.cache.clear();
  closeAllTabs(false);
  clientLabel();
  status("Signed out", "ok");
  showTab("oauth");
}

// ── Main: Reports + one sub-tab per report ────────────────────────────────
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
  if (S.top !== "main") showTab("main");
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
  S.current = null;
  if (reselect) select(null);
}

function renderHome() {
  const view = h("div", { class: "view home" });
  view.append(S.connected
    ? h("div", { class: "banner" }, h("b", {}, `●  Connected to  ${S.orgName}`),
      `${S.catalog.endpoints.length} reports  ·  each opens in its own tab  ·  ⚡ already fetched (Refresh fetches again)`)
    : h("div", { class: "banner warn" }, h("b", {}, "⚠  No client selected: add or pick one in the OAuth tab."),
      h("button", { class: "accent small", type: "button", onclick: () => showTab("oauth") }, "Open OAuth tab")));
  const grid = h("div", { class: "grid" });
  for (const s of S.catalog.sections) {
    grid.append(h("div", { class: "section", style: `--c: var(--s${s.color % 6})` },
      h("h3", {}, `${s.icon}  ${s.name}`),
      S.catalog.endpoints.filter((e) => e.section === s.id).map((ep) =>
        h("button", { type: "button", title: ep.help, disabled: S.busy || !S.connected, onclick: () => openReport(ep) },
          S.cache.has(ep.key) ? h("span", { class: "cached" }, "⚡") : null, ep.label))));
  }
  view.append(grid);
  return view;
}

async function openReport(ep, force = false) {
  if (!S.connected) return showTab("oauth");
  if (!force && S.cache.has(ep.key)) {
    status("⚡ From memory (Refresh to fetch again)", "ok");
    return openTab(S.cache.get(ep.key));
  }
  if (S.busy) return status("Another request is running; cancel it first", "warn");
  if (ep.slow && !force && !confirm(`${ep.help}\n\nThis can take several minutes in a large org. Continue?`)) return;
  setBusy(true);
  S.abort = new AbortController();
  log("INFO", `Started: ${ep.label}`);
  status(`${ep.label}...`, "busy");
  try {
    const res = await fetchReport(S.api, ep, S.abort.signal);
    S.cache.set(ep.key, res);
    status(`✓  ${ep.label}: ${ep.kind === "object" ? "fetched" : res.count + " records"}, ${res.calls} API calls`, "ok");
    openTab(res);
  } catch (e) {
    if (e instanceof Cancelled) status("Cancelled", "warn");
    else if (S.mode === "hosted" && e.status === 401) {
      status("Your session expired: sign in again in the OAuth tab", "err");
      S.connected = false;
      clientLabel();
    } else {
      const hint = e.status === 403 ? " (the roles of your account lack a permission for this report)" : "";
      status(`Error: ${e.message}${hint}`, "err");
    }
  } finally {
    setBusy(false);
    if (!S.current && S.top === "main") select(null);
  }
}

function setBusy(b) {
  S.busy = b;
  $("progress").hidden = !b;
  $("btn-cancel").hidden = !b;
  document.querySelectorAll(".home .section button").forEach((x) => { x.disabled = b || !S.connected; });
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
      h("h2", {}, ep.label), count, h("span", { class: "meta" }, `·  ${S.orgName}  ·  fetched ${stamp}  ·  ${res.calls} API calls`),
      h("div", { class: "actions" },
        h("button", { class: "ghost", type: "button", title: "Fetch again from the API (Alt+R)", onclick: () => openReport(ep, true) }, "🔄 Refresh"),
        h("button", { class: "ghost", type: "button", title: "The API's own JSON, page by page", onclick: () => download(fileName(ep, "json"), JSON.stringify(res.raw, null, 2), "application/json") }, "⬇ Raw JSON"),
        h("button", { class: "accent", type: "button", title: "What you see: filter and order included", onclick: () => {
          const vr = visibleRows();
          download(fileName(ep, "csv"), toCSV(cols.map((c) => c.header), vr), "text/csv;charset=utf-8");
          status(`✓  ${vr.length} rows exported${vr.length !== rows.length ? " (filtered)" : ""}`, "ok");
        } }, "⬇ Export CSV"))),
    h("div", { class: "searchbar" }, "🔍", search,
      h("span", { class: "hint" }, `click a row for every field${ep.actions.includes("members") ? " and the queue members" : ""}  ·  Alt+W close tab  ·  Esc reports`)),
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
        status(`✓  ${members.length} members in ${record.name}`, "ok");
      } catch (e) {
        status(`Error: ${e.message}`, "err");
        btn.disabled = false;
      }
    };
    parts.unshift(btn);
  }
  dialog(title, ...parts);
}

// ── Config tab ────────────────────────────────────────────────────────────
function renderConfig() {
  const panel = $("tab-config");
  const dark = isDark();
  const radio = (val, text) => h("label", { class: "check" },
    h("input", { type: "radio", name: "theme", value: val, checked: (val === "dark") === dark, onchange: () => setTheme(val) }), text);
  const local = readOrgs("localStorage").length, session = readOrgs("sessionStorage").length;
  panel.replaceChildren(h("div", { class: "config" },
    h("h3", {}, "Appearance"),
    h("div", { class: "form-row" }, h("span", {}, "Theme"), h("div", { class: "radios" }, radio("light", "☀  Light"), radio("dark", "☾  Dark"))),
    h("h3", {}, "Proxy"),
    h("p", { class: "note" }, "The browser uses the proxy settings of your system. In the desktop app and pyramid web, set the proxy in their Config tab."),
    h("h3", {}, "Storage"),
    PRIVACY(),
    S.mode === "demo"
      ? h("p", { class: "note" }, "Demo: nothing is kept in this browser except the theme.")
      : S.mode === "local"
      ? h("p", { class: "note" }, "Clients come from pyramid.cfg on this computer (managed by the desktop app). This browser keeps only the theme.")
      : [h("div", { class: "form-row" }, h("span", {}, "In this browser"),
        h("span", {}, `${session} client(s) for this tab only, ${local} remembered, ${token() ? "signed in" : "not signed in"}`)),
      h("div", { class: "form-actions" }, h("button", { class: "danger", type: "button", onclick: () => {
        if (!confirm("Remove every client, setting and token Pyramid keeps in this browser?")) return;
        forgetEverything();
        S.connected = false;
        S.api = null;
        S.cache.clear();
        closeAllTabs(false);
        clientLabel();
        applyTheme(null);
        status("Everything Pyramid kept in this browser was removed", "ok");
        renderConfig();
      } }, "Forget everything on this browser"))]));
}

// ── Log tab ───────────────────────────────────────────────────────────────
function renderLog() {
  const panel = $("tab-log");
  const levelSel = h("select", { "aria-label": "Level", onchange: (e) => { S.logLevel = e.target.value; renderLog(); } },
    LEVELS.map((l) => h("option", { value: l, selected: l === S.logLevel }, l)));
  const lines = h("div", { id: "log-lines", class: "loglines" },
    S.log.filter(([, l]) => LEVELS.indexOf(l) >= LEVELS.indexOf(S.logLevel)).map(([ts, l, m]) => h("div", { class: `ll ${l}` }, `${ts}  ${l.padEnd(5)}  ${m}`)));
  panel.replaceChildren(h("div", { class: "logview" },
    h("div", { class: "logbar" }, h("span", {}, "Level"), levelSel, h("span", { class: "spacer" }),
      h("button", { type: "button", class: "ghost", onclick: () => download(`pyramid_${Date.now()}.log`, S.log.map(([t, l, m]) => `${t}  ${l.padEnd(5)}  ${m}`).join("\n") + "\n", "text/plain") }, "Save log..."),
      h("button", { type: "button", class: "ghost", onclick: () => { S.log = []; renderLog(); } }, "Clear")),
    lines));
  lines.scrollTop = lines.scrollHeight;
}

// ── Help tab ──────────────────────────────────────────────────────────────
function renderHelp() {
  const general = [
    ["Getting started", "1. OAuth tab: add a client (name, region, Client ID) and Save and sign in.  2. Main tab: click a report; ⚡ marks the ones already fetched.  3. Search, sort by any column, click a row for every field, then Export CSV or Raw JSON."],
    ["Keyboard", "Esc  back to Reports    Alt+W  close the report tab    Alt+R  refresh    /  search"],
    ["Exports", "CSV is UTF-8 with the columns you see, in the order and filter you see (Excel and Power BI read it directly). Cells that would run as spreadsheet formulas get a leading apostrophe. Raw JSON is the API's own answer."],
    ["Rate limits and errors", "Pyramid waits and retries when Genesys Cloud answers 429 or a temporary 5xx, honouring Retry-After; Cancel stops it. A 403 means your roles lack a permission; nothing is kept after an error."],
    ["Privacy", "Nothing is stored on any server. The hosted page keeps your clients in this browser (this tab only unless remembered) and the token in this tab; pyramid web keeps secrets in the Pyramid process."],
  ];
  const block = (title, color, items) => h("div", { class: "helpblock", style: `--c: var(--s${color % 6})` },
    h("h3", {}, title), items.map(([t, d]) => h("div", { class: "helpitem" }, h("b", {}, t), h("p", {}, d))));
  $("tab-help").replaceChildren(h("div", { class: "help" },
    block("📖  Using Pyramid", 0, general),
    S.catalog.sections.map((s) => block(`${s.icon}  ${s.name}`, s.color,
      S.catalog.endpoints.filter((e) => e.section === s.id).map((e) => [e.label, e.help])))));
}

// ── About tab, with the pyramid of bricks running a Sieve of Eratosthenes ─
let sieveTimer = null;
function stopSieve() { if (sieveTimer) { clearTimeout(sieveTimer); sieveTimer = null; } }

function renderAbout() {
  const ROWS = 18, BW = 9, BH = 6, PAD = 8;
  const W = BW * ROWS + PAD * 2, H = BH * ROWS + PAD * 2;
  const canvas = h("canvas", { width: W, height: H, class: "sieve", "aria-hidden": "true" });
  $("tab-about").replaceChildren(h("div", { class: "about" },
    h("div", { class: "about-top" }, canvas,
      h("div", {},
        h("h2", {}, "Pyramid API Management"),
        h("p", { class: "muted" }, `Version ${VERSION}  ·  web`),
        h("p", {}, h("b", {}, "Developed by Ighor Toth  ·  toth@ighor.com")),
        h("p", {}, h("a", { href: REPO }, REPO)),
        h("p", { class: "muted" }, "MIT License  ·  written with Claude Code as co-author"),
        h("p", { class: "danger-text" }, "An independent tool: not a Genesys product, not affiliated with or endorsed by Genesys."))),
    h("table", { class: "kv" }, h("tbody", {},
      [["Reports", `${S.catalog.endpoints.length} in ${S.catalog.sections.length} sections`],
        ["API", "Genesys Cloud Platform API v2 (REST, read only)"],
        ["Mode", { local: "pyramid web (this computer)", demo: "demo (made-up data, no connection)" }[S.mode] || "hosted (your browser only)"],
        ["Desktop app", "Windows, macOS, Linux: github.com/igtoth/pyramid/releases"]].map(([k, v]) => h("tr", {}, h("th", {}, k), h("td", {}, v)))))));
  const ctx = canvas.getContext("2d");
  const bricks = [];
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < ROWS - r; c++) bricks.push([PAD + c * BW + (r * BW) / 2, H - PAD - BH - r * BH]);
  const N = bricks.length, prime = new Array(N + 1).fill(true);
  prime[0] = prime[1] = false;
  for (let i = 2; i * i <= N; i++) if (prime[i]) for (let j = i * i; j <= N; j += i) prime[j] = false;
  const paint = (n, fill, line) => {
    const [x, y] = bricks[n - 1];
    ctx.fillStyle = fill; ctx.fillRect(x, y, BW - 1, BH - 1);
    ctx.strokeStyle = line; ctx.strokeRect(x + 0.5, y + 0.5, BW - 2, BH - 2);
  };
  let order = [], step = 0;
  const restart = () => {
    for (let n = 1; n <= N; n++) paint(n, "#cd853f", "#7a4a1a");
    order = Array.from({ length: N }, (_, i) => i + 1).sort(() => Math.random() - 0.5);
    step = 0;
    sieveTimer = setTimeout(tick, 120);
  };
  const tick = () => {
    if (step > 0) { const p = order[step - 1]; paint(p, prime[p] ? "#ffd700" : "#7a8fa6", prime[p] ? "#b8860b" : "#5a6f86"); }
    if (step >= order.length) { sieveTimer = setTimeout(restart, 3000); return; }
    paint(order[step], "#5090ff", "#1a4acc");
    step++;
    sieveTimer = setTimeout(tick, 90);
  };
  stopSieve();
  restart();
}

// ── keyboard ──────────────────────────────────────────────────────────────
function onKey(e) {
  if ($("dialog").open) return;
  if (e.key === "Escape" && S.top === "main" && S.current) { select(null); e.preventDefault(); }
  else if (e.key === "Escape" && S.top !== "main") { showTab("main"); e.preventDefault(); }
  else if (e.altKey && (e.key === "w" || e.key === "W") && S.current) { closeTab(S.current); e.preventDefault(); }
  else if (e.altKey && (e.key === "r" || e.key === "R") && S.current) { openReport(S.current.res.endpoint, true); e.preventDefault(); }
  else if (e.key === "/" && S.current && S.top === "main" && document.activeElement?.tagName !== "INPUT") {
    S.current.el?.querySelector("input[type=search]")?.focus();
    e.preventDefault();
  }
}

init().catch((e) => { status(`Error: ${e.message}`, "err"); console.error(e); });

export { S as state, ApiError };
