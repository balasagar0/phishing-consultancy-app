# Multi-Channel Phishing Detection: website and web app

A working website and web app around the CP1 phishing detection engine, for consultancy pilots. One installation serves several client
organisations. Each has its own people, roles, API keys, event store and encryption key.

- **Website** (`/`): what the service does, its honest results and limits, privacy, and a "request a pilot" form.
- **Web app** (`/app`): scan a message, investigate several messages, alert queue with triage and notes, campaigns, dashboard, CSV and printable
  client reports, people and roles, API keys, retention settings, audit log, and a consultant view over all client organisations.
- **API** (`/api/v1/...`): connectors send messages in and pull alerts out with an organisation's API key.
- **Installable**: on a phone or desktop, the browser offers "Install app" (a progressive web app). Static files are cached; no message data is.

This folder is separate from the CP1 project (`../project`), which it never changes. The detection engine in `engine/` is a pinned copy of
the project's tag `cp1-final`, taken read-only by `scripts/sync_engine.py`; `tests/test_engine_parity.py` checks that the app scores the eight
demo cases exactly as `cp1-final` does.

## What it does not do

Tell every client this before a pilot. The same text is on the website's Results page and in the app under "What the models can do".

- It does not assess voice calls or video. They are shown as "not assessed", never as safe.
- Campaign correlation was measured only on **simulated** campaigns of real messages. No real coordinated campaign has tested it.
- The risk is a score, not a probability. The email model raises false alarms on real legitimate mail, so verdicts are advice for an analyst,
  not automatic blocking.
- It has had no penetration test, no load test, and no run on a client's real traffic. Do those before a client relies on it.

## Run it on this laptop (Windows)

Needs Python 3.11+ and Node.js 18+. The first setup needs the internet; after that it runs offline.

```bat
setup_windows.bat
```

It installs the packages, builds the website, checks the engine, creates the database and asks for your email to create the consultant
account (you type the password). Then:

```bat
start_app.bat
```

The browser opens http://127.0.0.1:8765/. Sign in at `/app` with the consultant account, create a client organisation under **Client
organisations**, add its first admin, and open it.

Linux or macOS: `./setup.sh`, then `./start.sh`.

### A demo with sample data

```bat
cd backend
..\.venv\Scripts\python.exe -m server.cli seed-demo
```

This creates a "Demo Client" with an admin, an analyst and a viewer, and records the CP1 demo cases and Indian stories for a few made-up
recipients. They are hand-written examples, not real messages and not a test set. The demo passwords are random and written to
`data/demo_credentials.txt`; delete the `data` folder to remove everything.

## Put it on a server (HTTPS)

`docker-compose.yml` runs the app behind Caddy, which obtains an HTTPS certificate for your domain:

```bash
cp .env.example .env          # set MCPD_DOMAIN
docker compose up -d --build
docker compose exec app python backend/server/cli.py create-superadmin --email you@firm.example
```

Docker was not available on the build laptop, so the image and the compose file have not been run yet. Build and check them on the server
before the first client. Without Docker: run `./start.sh` behind any HTTPS reverse proxy and set `MCPD_SECURE_COOKIES=1`.

**Patent privacy.** The CP1 patent is not filed. Do not push this folder to a public repository, upload it, or host it where others can
reach it until the patent is filed and the team agrees (CP1 rule 8).

## Configuration

Environment variables, or a `.env` file in this folder (see `.env.example`): `MCPD_DATA_DIR`, `MCPD_PORT`, `MCPD_SECURE_COOKIES`,
`MCPD_SESSION_HOURS`, `MCPD_PURGE_INTERVAL_HOURS`, `MCPD_MASTER_KEY`, `MCPD_DATABASE_URL` (PostgreSQL), `MCPD_APP_NAME`.

## Connect a mailbox

Staff forward suspicious mail to a "report phishing" mailbox; the connector reads it and sends each message in:

```bash
set MCPD_URL=https://phishing.example.com
set MCPD_API_KEY=<a key from Integrations & API>
set MCPD_IMAP_PASSWORD=<the mailbox password>
.venv\Scripts\python.exe connectors\imap_connector.py --host imap.client.example --user report-phishing@client.example --interval 60
```

Anything else (an SMS gateway, a SIEM) can call the API directly; the **Integrations & API** page shows the requests.

## Roles

| Role | Can |
|---|---|
| Viewer | read the dashboard, alerts, campaigns and reports |
| Analyst | also scan, investigate, record messages, triage alerts and add notes |
| Admin | also manage people, API keys, privacy and retention settings, purge, and read the audit log |
| Consultant (superadmin) | create and disable client organisations, add their first admin, open any organisation, read pilot requests |

## Security and privacy, as built

- Passwords: scrypt with a random salt; at least 10 characters. Five wrong attempts lock an account for 15 minutes; sign-in is rate limited.
- Sessions: a random token in an HttpOnly, SameSite=Strict cookie (Secure over HTTPS), stored hashed; every change needs a CSRF header.
- API keys: shown once, stored hashed, revocable, 120 requests a minute each.
- Client separation: every query is scoped to the caller's organisation; each organisation has its own event-store file and its own HMAC key,
  derived from the master key, so one client's hashes never match another's.
- Stored: channel, time, score, label, model version, and the recipient and identifiers as HMAC-SHA256. Message text only if the organisation
  turns it on. Alert cases keep the recipient's name and plain indicators unless the organisation turns labels off.
- Retention: a daily purge deletes events, alert cases, notes and scan rows older than the organisation's retention period.
- Headers: a strict Content-Security-Policy, no framing, no sniffing, no referrer; request bodies over 2 MB are refused. Spreadsheet exports
  escape formulas.
- Nothing calls an outside service. No link in a message is opened.

## Tests

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests
.venv\Scripts\python.exe scripts\ui_check.py          (with the app running and the demo seeded; drives the installed Chrome)
```

`tests/` covers engine parity with `cp1-final`, sign-in, CSRF, lockout, roles, client separation, API keys, triage, privacy of stored data,
retention, reports, security headers and the mail connector. `scripts/ui_check.py` opens every page at a laptop and a phone size in Chrome,
signs in, scans, investigates, checks for console errors and checks that the installable app's service worker registers.

## Layout

| Path | What |
|---|---|
| `backend/server/` | the FastAPI server: `main.py` (app, headers, purge schedule), `routes_*.py`, `engine.py` (the engine and per-client stores), `db.py`, `security.py`, `cli.py` |
| `frontend/` | the React website and web app (`npm run build` writes `frontend/dist`, which the server serves) |
| `engine/` | the pinned cp1-final engine and models, with `ENGINE_MANIFEST.json` |
| `connectors/` | the IMAP mail connector |
| `scripts/` | `sync_engine.py`, `ui_check.py`, `make_icons.py` |
| `docs/` | `CLIENT_ONE_PAGER.md`, `OPERATIONS.md` |
| `data/` | created at run time: database, master key, client event stores (never in git) |

## Updating the engine

When the CP1 project tags a new build, run `python scripts/sync_engine.py --tag <new tag>`, then the tests. Engine parity must pass against the
new tag's own demo-case expectations before the update is used.
