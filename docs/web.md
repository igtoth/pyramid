# The web version

The same 53 reports as the desktop app, in the browser. One page, two ways in.

## 1. Hosted: https://igtoth.github.io/pyramid/

The page is static (HTML, CSS and JavaScript from `src/pyramid/web/` plus
`catalog.json`), published to GitHub Pages by the `web` and `pages` jobs of
[`build.yml`](../.github/workflows/build.yml). It has no backend: your browser
signs in to Genesys Cloud and calls the API itself.

### Set up the OAuth client (an admin, once per org)

1. Admin › Integrations › OAuth › **Add client**.
2. App name: `Pyramid web`. Grant type: **Code Authorization with PKCE**
   (sign in with your own account, no secret). (Genesys stopped offering the
   implicit grant for new clients on 25 May 2026 and removes it in 2027; PKCE
   is the replacement.)
3. Authorized redirect URI: `https://igtoth.github.io/pyramid/`, exactly,
   with the trailing slash.
4. Scope: none needed beyond the default; what each person can read comes from
   **their own roles**, not from the client.
5. Save and share the **client ID** with the people who should run reports.

### Sign in

The OAuth tab works like the desktop app's: **Saved clients** on the left;
**Name**, **Region**, **Client ID** on the right; **Save and use**, **New**,
**Delete**. *Save and use* sends you to the Genesys login and you come back
signed in with your own account.

The **Client secret** field is there but disabled. Genesys Cloud does not let
a web page use the Client Credentials grant: its token endpoint answers
without CORS headers, so the browser throws the answer away (in the console:
*blocked by CORS policy: No 'Access-Control-Allow-Origin' header*), and its
own JavaScript SDK refuses that grant in a browser. Nothing on the page can
get around it. For a Client Credentials client, use the desktop app or
`pyramid web` (below), which ask for the token from your computer.

**Nothing is stored on any server.** Pyramid has no server; everything stays in
your browser:

| What | Where | Until |
|---|---|---|
| saved clients (name, region, client ID) | `sessionStorage` of the tab | the tab closes |
| ...with **Remember on this browser** ticked | `localStorage` | you delete the client or click Forget everything |
| the access token | `sessionStorage` of the tab | the tab closes, Sign out, or it expires |

**Forget everything on this browser** (Config tab) removes all of it at once.

### What leaves your browser

Only requests to Genesys Cloud: `login.<region>` for the sign-in and
`api.<region>` for the reports. The page's Content Security Policy blocks
every other host. GitHub serves the files and sees that you loaded the page,
like any GitHub Pages site.

### Host it yourself

Copy `src/pyramid/web/*` and `src/pyramid/catalog.json` into one folder on any
static web server (HTTPS), and register that folder's URL as the redirect URI
of the OAuth client. Nothing to build.

## 2. Local: `pyramid web`

```sh
pyramid web               # opens http://127.0.0.1:8710/?k=<session key>
pyramid web --port 9000 --no-browser
```

Serves the same page on your computer, with the desktop app's OAuth tab:
**Name**, **Region**, **Client ID**, **Client secret** (*Show secret*),
**Save and use**, **Test connection**, **Save**, **New**, **Delete**. Clients
are **Client Credentials** clients, saved in the same `pyramid.cfg` as the
desktop app, so a client added in one shows up in the other.

A secret you type goes to the Pyramid process once, when you save or test;
it is never sent back to the page (editing a client, leave the secret empty
to keep the saved one). The page calls `/local/api/<client>/api/v2/...` and
the Pyramid process gets the token and adds it.

- Listens on `127.0.0.1` only.
- The address it opens carries a random session key, traded for an
  `HttpOnly`, `SameSite=Strict` cookie; without it the proxy answers 401.
- The `Host` header must be this server (no DNS rebinding).
- Only `GET` requests to `/api/v2/` are forwarded.
- Saving, testing and deleting clients are JSON `POST`s to `/local/clients`
  and `/local/test` that also need the `X-Pyramid` header and a same-origin
  `Origin`; no other site can send them.

## Differences from the desktop app

| | Desktop | Web |
|---|---|---|
| Sign-in | Client Credentials (saved per org) | hosted: your own account (PKCE); `pyramid web`: Client Credentials, same as the desktop |
| Several orgs | switch in the OAuth tab | sign out and in, or one browser tab per org |
| Large tables | all rows | 2,000 at a time ("Show more"); search, sort and export use every row |
| Queue members | right-click a queue | click a queue, then "Show queue members" |

## Troubleshooting

| Message | Cause |
|---|---|
| `invalid_client` / `unauthorized_client` at sign-in | the client is not a PKCE client, or the region is not the org's |
| `invalid_client` on Test connection (`pyramid web`) | wrong secret, or the region is not the org's (`us_east_2` is the US government cloud; most US orgs are `us_east_1`) |
| `redirect_uri_mismatch` | the redirect URI in the client differs from the page address (trailing slash included) |
| HTTP 403 on a report | your roles lack the permission that report needs |
| Your session expired | tokens expire (the OAuth client sets how long); sign in again |
