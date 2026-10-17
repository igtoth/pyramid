# Privacy policy

Pyramid does not collect, send or sell any information about you or your
organization. It has no telemetry, no analytics and no server of its own.

## What it talks to

Only Genesys Cloud, and only when you ask for a report or test a connection:

- `login.<region>` to get an access token;
- `api.<region>` for the reports (GET requests only).

The web version is served by GitHub Pages, which sees that you loaded the page
(see GitHub's privacy statement). The page itself only connects to Genesys
Cloud; its Content Security Policy blocks every other host.

## What it stores

| Where | What |
|---|---|
| `pyramid.cfg` in your user profile (desktop app, command line, `pyramid web`) | saved OAuth clients (name, region, client ID, **secret in plain text**), proxy, theme, last client used. Readable only by you on macOS and Linux. |
| the browser tab's `sessionStorage` (web version) | the orgs you added (name, region, client ID) and the access token, until the tab closes |
| the browser's `localStorage` (web version) | only the orgs you ticked "Remember on this browser" for, and the theme; "Forget everything on this browser" removes them |
| memory, while Pyramid runs | the reports you opened |
| files you export | exactly what you exported |

Reports can contain personal data (names, e-mail addresses, login dates).
Handling the files you export is up to you, under the law that applies to you
(GDPR, LGPD, ...) and your organization's policies.

## Secrets

OAuth client secrets and recording API keys returned by Genesys Cloud are
removed from every report and export. The client secret you save is sent only
to `login.<region>` to get a token. `pyramid web` never hands it to the browser.

Questions: toth@ighor.com
