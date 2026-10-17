# The web version

The same 53 reports as the desktop app, in the browser. One page, two ways in.

## 1. Hosted: https://igtoth.github.io/pyramid/

The page is static (HTML, CSS and JavaScript from `src/pyramid/web/` plus
`catalog.json`), published to GitHub Pages by the `web` and `pages` jobs of
[`build.yml`](../.github/workflows/build.yml). It has no backend: your browser
signs in to Genesys Cloud and calls the API itself.

### Set up the OAuth client (an admin, once per org)

1. Admin › Integrations › OAuth › **Add client**.
2. App name: `Pyramid web`. Grant type: **Code Authorization with PKCE**.
   PKCE needs no secret. (Genesys stopped offering the implicit grant for new
   clients on 25 May 2026 and removes it in 2027; PKCE is the replacement.)
3. Authorized redirect URI: `https://igtoth.github.io/pyramid/`, exactly,
   with the trailing slash.
4. Scope: none needed beyond the default; what each person can read comes from
   **their own roles**, not from the client.
5. Save and share the **client ID** with the people who should run reports.

### Sign in

Open the page, pick the org's region, paste the client ID, **Sign in with
Genesys Cloud**. The page sends you to the Genesys login, you come back
signed in. The region and client ID are remembered in this browser
(`localStorage`); the access token only lives in this tab's
`sessionStorage` and is gone when you close it.

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

Serves the same page on your computer with the **Client Credentials** clients
saved in the desktop app (OAuth tab). The browser never sees a secret: it
calls `/local/api/<client>/api/v2/...` and the Pyramid process adds the token.

- Listens on `127.0.0.1` only.
- The address it opens carries a random session key, traded for an
  `HttpOnly`, `SameSite=Strict` cookie; without it the proxy answers 401.
- The `Host` header must be this server (no DNS rebinding).
- Only `GET` requests to `/api/v2/` are forwarded.

## Differences from the desktop app

| | Desktop | Web |
|---|---|---|
| Sign-in | Client Credentials (saved per org) | your own account (PKCE) or the saved clients (`pyramid web`) |
| Several orgs | switch in the OAuth tab | sign out and in, or one browser tab per org |
| Large tables | all rows | 2,000 at a time ("Show more"); search, sort and export use every row |
| Queue members | right-click a queue | click a queue, then "Show queue members" |

## Troubleshooting

| Message | Cause |
|---|---|
| `invalid_client` / `unauthorized_client` at sign-in | the client is not a PKCE client, or the region is not the org's |
| `redirect_uri_mismatch` | the redirect URI in the client differs from the page address (trailing slash included) |
| HTTP 403 on a report | your roles lack the permission that report needs |
| Your session expired | tokens expire (the OAuth client sets how long); sign in again |
