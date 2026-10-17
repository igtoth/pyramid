// Demo mode (the published site): a made-up Genesys Cloud org answered inside
// the page, from demo.json. Nothing is sent anywhere: the page's Content
// Security Policy on the published site only allows its own files.
// The answers follow the real API's shapes (paging, cursors, 401 without a
// token), so the page runs exactly the code it runs against a real org.

export const DEMO_CLIENT = {
  name: "Lumen Harbor (demo)", region: "us_east_1",
  clientId: "00000000-de00-4000-8000-000000000000", hasSecret: true,
};
export const DEMO_TOKEN = "demo-token";

const sleep = (ms, signal) => new Promise((res, rej) => {
  const t = setTimeout(res, ms);
  signal?.addEventListener("abort", () => { clearTimeout(t); rej(new DOMException("Aborted", "AbortError")); }, { once: true });
});

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function page(path, items, q, cursor) {
  const size = Number(q.get("pageSize") || q.get("limit") || 25);
  if (cursor) {
    const start = Number(q.get("cursor") || q.get("after") || 0);
    const body = { entities: items.slice(start, start + size) };
    if (start + size < items.length) {
      const rest = new URLSearchParams(q);
      rest.delete("cursor");
      rest.delete("after");
      rest.set(q.has("limit") ? "cursor" : "after", String(start + size));
      body.nextUri = `${path}?${rest}`;
    }
    return body;
  }
  const number = Number(q.get("pageNumber") || 1);
  return { entities: items.slice((number - 1) * size, number * size), pageSize: size, pageNumber: number,
    total: items.length, pageCount: items.length ? Math.ceil(items.length / size) : 0 };
}

function answer(data, path, q) {
  if (data.objects[path]) return json(200, data.objects[path]);
  let m = path.match(/^\/api\/v2\/routing\/queues\/([^/]+)\/members$/);
  if (m) return data.queueMembers[m[1]] ? json(200, page(path, data.queueMembers[m[1]], q, true)) : json(404, { message: "queue not found" });
  m = path.match(/^\/api\/v2\/authorization\/roles\/([^/]+)\/users$/);
  if (m) return json(200, page(path, data.roleUsers[m[1]] || [], q, false));
  m = path.match(/^\/api\/v2\/gamification\/profiles\/([^/]+)\/metrics$/);
  if (m) return json(200, { entities: data.profileMetrics[m[1]] || [], total: 3 });
  let items = data.listings[path];
  if (!items) return json(404, { message: `The demo org has no data for ${path}` });
  if (path === "/api/v2/users" && q.has("state")) items = items.filter((x) => x.state === q.get("state"));
  if (data.cursorPaths.includes(path)) return json(200, page(path, items, q, true));
  if (!q.has("pageSize") && !q.has("pageNumber")) return json(200, { entities: items, total: items.length });
  return json(200, page(path, items, q, false));
}

// A fetch() for Api({ fetchFn }): same calls, answered here after a short,
// network-like wait. onRequest(path) lets the page log each call.
export async function demoApi(onRequest = () => {}) {
  const data = await (await fetch("demo.json")).json();
  return async (url, opts = {}) => {
    const u = new URL(url, location.href);
    await sleep(120 + Math.random() * 260, opts.signal);
    const auth = (opts.headers || {}).Authorization;
    onRequest(u.pathname + u.search);
    if (auth !== `Bearer ${DEMO_TOKEN}`) return json(401, { message: "Invalid login credentials." });
    return answer(data, u.pathname, u.searchParams);
  };
}

// The "token endpoint" of the demo: any client gets in, after a pause.
export async function demoSignIn(signal) {
  await sleep(500 + Math.random() * 400, signal);
  return { access_token: DEMO_TOKEN, expires_in: 86399 };
}
