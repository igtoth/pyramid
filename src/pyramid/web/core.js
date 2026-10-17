// Pyramid web: the pure parts (no DOM). Mirrors src/pyramid/data.py,
// fetch.py and client.py so the browser and the desktop app export the
// same rows; tests/web/core.test.mjs checks them against the Python output.

export const LIST_SEP = "; ";
const FORMULA_START = ["=", "+", "-", "@", "\t", "\r"];
const PLAIN_NUMBER = /^[+-]?\d[\d.]*$/;  // E.164 numbers and negatives are not formulas
const LONE_SURROGATE = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g;
const ACRONYMS = { id: "ID", dnis: "DNIS", url: "URL", uri: "URI", api: "API", mx: "MX", kpi: "KPI", dnc: "DNC", smtp: "SMTP", rrule: "RRule" };

export const API_HOSTS = {
  us_east_1: "https://api.mypurecloud.com",
  us_east_2: "https://api.use2.us-gov-pure.cloud",
  us_west_2: "https://api.usw2.pure.cloud",
  ca_central_1: "https://api.cac1.pure.cloud",
  sa_east_1: "https://api.sae1.pure.cloud",
  mx_central_1: "https://api.mxc1.pure.cloud",
  eu_west_1: "https://api.mypurecloud.ie",
  eu_west_2: "https://api.euw2.pure.cloud",
  eu_central_1: "https://api.mypurecloud.de",
  eu_central_2: "https://api.euc2.pure.cloud",
  eusc_de_east_1: "https://api.edee1.eusc-pure.cloud",
  me_central_1: "https://api.mec1.pure.cloud",
  ap_south_1: "https://api.aps1.pure.cloud",
  ap_southeast_1: "https://api.apse1.pure.cloud",
  ap_southeast_2: "https://api.mypurecloud.com.au",
  ap_northeast_1: "https://api.mypurecloud.jp",
  ap_northeast_2: "https://api.apne2.pure.cloud",
  ap_northeast_3: "https://api.apne3.pure.cloud",
};
export const loginHost = (apiHost) => apiHost.replace("://api.", "://login.");

// ── catalog ───────────────────────────────────────────────────────────────

export function headerFor(path) {
  let parts = path.split(".");
  if (parts.length > 1 && ["name", "id", "display"].includes(parts[parts.length - 1])) parts = parts.slice(0, -1);
  const words = parts[parts.length - 1].replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_/g, " ").split(/\s+/).filter(Boolean);
  return words.map((w) => ACRONYMS[w.toLowerCase()] || (w === w.toUpperCase() ? w : w[0].toUpperCase() + w.slice(1))).join(" ");
}

export function normalizeCatalog(raw) {
  const endpoints = raw.endpoints.map((e) => ({
    key: e.key, label: e.label, section: e.section, help: e.help || "", path: e.path || null,
    kind: e.kind || "list", pageSize: "pageSize" in e ? e.pageSize : 100, sizeParam: e.sizeParam || "pageSize",
    cursor: e.paging === "cursor", query: e.query || {}, variants: e.variants || [], drop: e.drop || [],
    special: e.special || null, actions: e.actions || [], slow: !!e.slow,
    columns: (e.columns || []).map((c) => (typeof c === "string" ? { header: headerFor(c), path: c } : { header: c[0], path: c[1] })),
  }));
  return { sections: raw.sections, endpoints, byKey: Object.fromEntries(endpoints.map((e) => [e.key, e])) };
}

// ── data ──────────────────────────────────────────────────────────────────

const isEmpty = (v) => v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0) ||
  (typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0);

export function resolve(obj, path) {
  let cur = obj;
  for (const part of path.split(".")) {
    if (Array.isArray(cur)) {
      cur = cur.map((x) => resolve(x, part)).filter((x) => !isEmpty(x));
      continue;
    }
    if (cur === null || typeof cur !== "object") return null;
    cur = cur[part];
    if (cur === undefined || cur === null) return null;
  }
  return cur;
}

function sortedJson(v) {
  if (Array.isArray(v)) return "[" + v.map(sortedJson).join(",") + "]";
  if (v && typeof v === "object") return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + sortedJson(v[k])).join(",") + "}";
  return JSON.stringify(v);
}

export function cell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(value);
  if (typeof value === "string") return value.replace(LONE_SURROGATE, "\ufffd");
  if (Array.isArray(value)) return value.map(cell).filter(Boolean).join(LIST_SEP);
  if (typeof value === "object") {
    for (const k of ["name", "displayName", "id"]) {
      if (typeof value[k] === "string" || typeof value[k] === "number") return String(value[k]);
    }
    return Object.keys(value).length ? sortedJson(value) : "";
  }
  return String(value);
}

export function tableColumns(columns, records) {
  const cols = [...columns];
  if (records.length && records.slice(0, 50).some((r) => r && "id" in r) && !cols.some((c) => c.path === "id")) {
    cols.push({ header: "ID", path: "id" });
  }
  return cols;
}

export const rowsOf = (records, columns) => records.map((r) => columns.map((c) => cell(resolve(r, c.path))));

export function flattenObject(obj, prefix = "") {
  const out = [];
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    for (const k of Object.keys(obj).sort()) {
      if (k === "selfUri") continue;
      const key = prefix ? `${prefix}.${k}` : k;
      const v = obj[k];
      if (v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length) out.push(...flattenObject(v, key));
      else if (Array.isArray(v) && v.length && v.every((x) => x && typeof x === "object" && !Array.isArray(x)))
        v.forEach((x, i) => out.push(...flattenObject(x, `${key}[${i}]`)));
      else out.push([key, cell(v)]);
    }
  } else out.push([prefix || "value", cell(obj)]);
  return out;
}

export const csvSafe = (v) => (FORMULA_START.some((c) => v.startsWith(c)) && !PLAIN_NUMBER.test(v) ? "'" + v : v);

export function toCSV(header, rows) {
  const q = (v) => {
    const s = csvSafe(String(v));
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return "﻿" + [header, ...rows].map((r) => r.map(q).join(",")).join("\r\n") + "\r\n";
}

// ── API ───────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(status, message, correlationId) {
    super(status ? `HTTP ${status}: ${message}` + (correlationId ? ` (correlation id ${correlationId})` : "") : message);
    this.status = status;
  }
}
export class Cancelled extends Error {}

const sleep = (ms, signal) => new Promise((res, rej) => {
  const t = setTimeout(res, ms);
  signal?.addEventListener("abort", () => { clearTimeout(t); rej(new Cancelled("cancelled")); }, { once: true });
});

// Seconds from Retry-After (seconds or an HTTP date), between 1 s and 2 min.
export function retryAfter(value) {
  if (!value) return null;
  let secs = Number(value);
  if (Number.isNaN(secs)) {
    const t = Date.parse(value);
    if (Number.isNaN(t)) return null;
    secs = (t - Date.now()) / 1000;
  }
  return Math.min(120, Math.max(1, secs));
}

function queryString(params) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === null || v === undefined) continue;
    for (const item of Array.isArray(v) ? v : [v]) sp.append(k, item === true ? "true" : item === false ? "false" : String(item));
  }
  const s = sp.toString();
  return s ? "?" + s : "";
}

// base: "https://api.mypurecloud.com" (hosted) or "local/api/<client>" (pyramid web)
// headers(): extra headers per request (the bearer token when hosted)
export class Api {
  constructor({ base, headers = () => ({}), onProgress = () => {}, onUnauthorized = null, fetchFn = null, maxRetries = 6 }) {
    this.base = base.replace(/\/$/, "");
    this.headers = headers;
    this.onProgress = onProgress;
    this.onUnauthorized = onUnauthorized;
    this.fetch = fetchFn || ((...a) => fetch(...a));
    this.maxRetries = maxRetries;
    this.calls = 0;
  }

  url(path, params) {
    const u = path.startsWith("http") ? path : this.base + path;
    const qs = queryString(params);
    return qs ? u + (u.includes("?") ? "&" + qs.slice(1) : qs) : u;
  }

  async get(path, params, signal) {
    const url = this.url(path, params);
    for (let attempt = 0; ; attempt++) {
      if (signal?.aborted) throw new Cancelled("cancelled");
      let resp;
      try {
        this.calls++;
        resp = await this.fetch(url, { headers: { Accept: "application/json", ...this.headers() }, signal });
      } catch (e) {
        if (signal?.aborted || e.name === "AbortError") throw new Cancelled("cancelled");
        if (attempt < this.maxRetries) {
          const wait = Math.min(60, 2 ** attempt + Math.random());
          this.onProgress(`Network error, retrying in ${Math.round(wait)}s`);
          await sleep(wait * 1000, signal);
          continue;
        }
        throw new ApiError(null, `Cannot reach the API: ${e.message}`);
      }
      if (resp.ok) return resp.status === 204 ? {} : resp.json();
      if ([429, 502, 503, 504].includes(resp.status) && attempt < this.maxRetries) {
        const wait = retryAfter(resp.headers.get("Retry-After")) ?? Math.min(60, 2 ** attempt + Math.random());
        this.onProgress(`HTTP ${resp.status}, retrying in ${Math.round(wait)}s (${attempt + 1}/${this.maxRetries})`);
        await sleep(wait * 1000, signal);
        continue;
      }
      let body = {};
      try { body = await resp.json(); } catch { /* not JSON */ }
      if (resp.status === 401 && this.onUnauthorized) this.onUnauthorized();
      throw new ApiError(resp.status, body.message || body.error_description || resp.statusText || "error",
        resp.headers.get("inin-correlation-id") || body.contextId);
    }
  }

  // Every page of a listing (see client.py: pageNumber when the answer has
  // pageCount, nextUri otherwise).
  async *pages(path, { params = {}, pageSize = 100, sizeParam = "pageSize", cursor = false, signal, label = "" } = {}) {
    const p0 = { ...params };
    if (pageSize) p0[sizeParam] = pageSize;
    let numberPaging = !cursor, page = 1, nextUrl = null;
    const seen = new Set();
    for (let i = 0; i < 10000; i++) {
      let data;
      if (nextUrl) data = await this.get(nextUrl, null, signal);
      else {
        const p = { ...p0 };
        if (numberPaging && pageSize) p.pageNumber = page;
        data = await this.get(path, p, signal);
      }
      yield data;
      if (!data || typeof data !== "object") return;
      const count = data.pageCount;
      this.onProgress(`${label} page ${count ? `${page}/${count}` : page}`.trim());
      // walk by pageNumber only when we sent one; otherwise the same URL would come back
      if (Number.isInteger(count) && nextUrl === null && numberPaging && pageSize) {
        if (page >= count || !(data.entities || []).length) return;
        page++;
        continue;
      }
      const nxt = data.nextUri;
      if (!nxt || seen.has(nxt) || !(data.entities || []).length) return;
      seen.add(nxt);
      numberPaging = false;
      nextUrl = nxt.startsWith("http") ? nxt : this.base + nxt;
      page++;
    }
    throw new ApiError(null, `Stopped after 10000 pages of ${path}`);
  }

  async entities(path, opts) {
    const raw = [], out = [];
    for await (const page of this.pages(path, opts)) {
      raw.push(page);
      out.push(...(page.entities || []));
    }
    return [out, raw];
  }
}

// ── reports (fetch.py) ────────────────────────────────────────────────────

async function allUsers(api, signal, expand) {
  const users = [], raw = [];
  for (const state of ["active", "inactive"]) {
    const params = { state, sortOrder: "ASC" };
    if (expand) params.expand = expand;
    const [recs, pages] = await api.entities("/api/v2/users", { params, pageSize: 500, signal, label: `Users (${state})` });
    users.push(...recs);
    raw.push(...pages);
  }
  return [users, raw];
}

const byName = (a, b) => a.toLowerCase().localeCompare(b.toLowerCase());

export async function queueMembers(api, queueId, signal) {
  const [members] = await api.entities(`/api/v2/routing/queues/${queueId}/members`, { pageSize: 100, signal, label: "Members" });
  return members;
}

export async function fetchReport(api, ep, signal) {
  const start = api.calls;
  let res;
  if (ep.special === "users_queues") {
    const [users, rawUsers] = await allUsers(api, signal, ["skills"]);
    const [queues] = await api.entities("/api/v2/routing/queues", { pageSize: 100, signal, label: "Queues" });
    const byUser = {};
    for (const [i, q] of queues.entries()) {
      api.onProgress(`Queue members ${i + 1}/${queues.length}: ${q.name || ""}`);
      for (const m of await queueMembers(api, q.id, signal)) {
        const uid = m.id || m.user?.id;
        if (uid) (byUser[uid] ||= []).push(q.name || q.id);
      }
    }
    for (const u of users) u.queues = (byUser[u.id] || []).sort(byName);
    res = { records: users, raw: { users: rawUsers, queues } };
  } else if (ep.special === "users_roles") {
    const [users, rawUsers] = await allUsers(api, signal);
    const [roles] = await api.entities("/api/v2/authorization/roles", { pageSize: 100, signal, label: "Roles" });
    const byUser = {};
    for (const [i, r] of roles.entries()) {
      api.onProgress(`Role members ${i + 1}/${roles.length}: ${r.name || ""}`);
      const [members] = await api.entities(`/api/v2/authorization/roles/${r.id}/users`, { pageSize: 100, signal });
      for (const m of members) if (m.id) (byUser[m.id] ||= []).push(r.name || r.id);
    }
    for (const u of users) u.roles = (byUser[u.id] || []).sort(byName);
    res = { records: users, raw: { users: rawUsers, roles } };
  } else if (ep.special === "profile_metrics") {
    const profiles = (await api.get("/api/v2/gamification/profiles", null, signal)).entities || [];
    const records = [], raw = [];
    for (const [i, p] of profiles.entries()) {
      api.onProgress(`Profile ${i + 1}/${profiles.length}: ${p.name || ""}`);
      const data = await api.get(`/api/v2/gamification/profiles/${p.id}/metrics`, null, signal);
      raw.push({ profile: p, metrics: data });
      for (const m of data.entities || []) records.push({ ...m, profileName: p.name });
    }
    res = { records, raw };
  } else if (ep.kind === "object") {
    const obj = await api.get(ep.path, Object.keys(ep.query).length ? ep.query : null, signal);
    res = { obj, raw: obj };
  } else {
    const records = [], raw = [];
    for (const variant of ep.variants.length ? ep.variants : [{}]) {
      const extra = Object.values(variant).join(", ");
      const [recs, pages] = await api.entities(ep.path, {
        params: { ...ep.query, ...variant }, pageSize: ep.pageSize, sizeParam: ep.sizeParam, cursor: ep.cursor,
        signal, label: extra ? `${ep.label} (${extra})` : ep.label,
      });
      records.push(...recs);
      raw.push(...pages);
    }
    res = { records, raw };
  }
  if (ep.drop.length && res.records) for (const r of res.records) for (const f of ep.drop) delete r[f];
  res.endpoint = ep;
  res.calls = api.calls - start;
  res.fetchedAt = new Date().toISOString().slice(0, 19);
  res.count = ep.kind === "object" ? 1 : res.records.length;
  return res;
}

// ── PKCE ──────────────────────────────────────────────────────────────────

const b64url = (bytes) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export function pkceVerifier(n = 64) {
  const bytes = new Uint8Array(n);
  crypto.getRandomValues(bytes);
  return b64url(bytes);
}

export async function pkceChallenge(verifier) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return b64url(new Uint8Array(digest));
}
