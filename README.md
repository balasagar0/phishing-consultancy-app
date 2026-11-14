# Multi-Channel Phishing Detection: website and web app

A working website and web app around the CP1 phishing detection engine, for consultancy pilots. One installation serves several client
organisations. Each has its own people, roles, API keys, event store and encryption key.

- **Website** (`/`): what the service does, its honest results and limits, privacy, and a "request a pilot" form.
- **Real time**: messages arrive by themselves. The server reads mailboxes itself (IMAP with IDLE, or Microsoft 365 through Microsoft Graph), and
  SMS gateways and mail servers push each message in by webhook. Every open page updates within a second; nobody has to paste anything.
- **Web app** (`/app`): live feed of every message, alerts that appear by themselves (with a pop-up and optional desktop notification), alert
  queue with triage and notes, campaigns, dashboard, CSV and printable client reports, connectors, people and roles, API keys, retention
  settings, audit log, and a consultant view over all client organisations. Scanning or investigating a message by hand is still there.
- **API** (`/api/v1/...`): systems send messages in and pull alerts out with an organisation's API key; an alert webhook pushes each new alert
  to Slack, a SIEM or a ticketing system.
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
- The mailbox connectors were tested against stand-ins on this laptop (a small IMAP server and the Microsoft Graph endpoints, in
  `tests/fakes.py`), not against a real Gmail, Microsoft 365 or Zoho account. Check each one with the client's own mailbox, using
  **Test connection**, before the pilot starts.
- Live updates and connectors run inside one server process. Several processes or servers would need a message broker; that is not built.

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

To show the real-time side, sign in as the demo admin, open **Live feed** and press **Play the demo feed**. The demo replay sends the same
hand-written messages in one by one, every 4 seconds, with the current time: rows appear in the feed, campaigns build up, and alerts pop up on
every open page. Each replay uses its own made-up people. Running `seed-demo` again on an existing demo adds the replay if it is missing. Only the
command line can create a demo replay, so no client organisation gets made-up data.

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
`MCPD_SESSION_HOURS`, `MCPD_PURGE_INTERVAL_HOURS`, `MCPD_MASTER_KEY`, `MCPD_DATABASE_URL` (PostgreSQL), `MCPD_APP_NAME`, `MCPD_PUBLIC_URL`
(links in alert webhooks), `MCPD_RUN_CONNECTORS` (0 stops the server from reading mailboxes), `MCPD_ALLOW_PRIVATE_HOSTS` (1 lets connectors and
webhooks reach private and local addresses; off by default).

## Messages arrive by themselves (real time)

An admin sets these up under **Connectors** in the app. Every message goes through the same path: it is scored, linked to the person's other
messages, shown in the live feed, and opens an alert when its campaign reaches the line.

| Source | How it arrives | How fast |
|---|---|---|
| **IMAP mailbox** (Gmail or Google Workspace with an app password, Zoho, on-premises Exchange, Dovecot) | The server signs in and watches the folder | Seconds with IMAP IDLE; otherwise it checks every 30 s (10 s at least) |
| **Microsoft 365 mailbox** | Microsoft Graph with an app registration (Mail.Read application permission, client secret) | Checks every 30 s (15 s at least) |
| **SMS** | A phone forwarding app or SMS gateway posts each SMS to `POST /api/v1/hooks/sms` | As it is sent |
| **Report-smishing number** | Staff forward suspicious SMS to a gateway number (Twilio or similar) that posts to `/api/v1/hooks/sms?mode=reports` | As it is sent |
| **Mail server or mail-flow rule** | Posts each raw email to `POST /api/v1/hooks/email?recipient=<address>` | As it is delivered |
| **Any other system** | `POST /api/v1/events` with an API key | As it is sent |

Each mailbox connector reads either a **reporting mailbox** (staff forward suspicious mail; an email forwarded as an attachment is checked and
the person who forwarded it is the recipient) or **watches an inbox** (every new message is checked; the mailbox's owner is the recipient).
Watching a person's inbox reads all their new mail: do it only under the client's written policy, with notice to the people concerned.

What a connector does and does not do:

- It reads only mail that arrives after it starts, and remembers where it got to, so a restart neither skips nor repeats a message.
- It opens the folder read-only. It never sets a flag, moves or deletes mail.
- It counts a message larger than 10 MB as skipped without reading it. A message read twice is recorded once.
- Its password or client secret is stored encrypted (AES-256-GCM, with a key derived from the master key) and never shown again.
- Problems show on the connector as one line ("the mail server said: Invalid credentials"), and it retries with a growing pause.

**Alert webhook.** Under Connectors, an admin can give an address (a Slack incoming webhook, a SIEM, a ticketing system). The moment an alert
opens, the server POSTs a short JSON notice: a Slack-style `text` line and the alert's fields, never message text. With a signing secret,
`X-MCPD-Signature: sha256=<HMAC-SHA256 of "<X-MCPD-Timestamp>.<body>">` lets the receiver check it. Set `MCPD_PUBLIC_URL` to put a link to
the alert in the notice.

**Stand-alone mail connector.** For a mailbox the server cannot reach (inside the client's own network), `connectors/imap_connector.py` reads
it there and sends each message in with an API key:

```bash
set MCPD_URL=https://phishing.example.com
set MCPD_API_KEY=<a key from Integrations & API>
set MCPD_IMAP_PASSWORD=<the mailbox password>
.venv\Scripts\python.exe connectors\imap_connector.py --host imap.client.example --user report-phishing@client.example --interval 60
```

## Roles

| Role | Can |
|---|---|
| Viewer | read the dashboard, alerts, campaigns and reports |
| Analyst | also scan, investigate, record messages, triage alerts and add notes |
| Admin | also manage people, connectors, the alert webhook, API keys, privacy and retention settings, purge, and read the audit log |
| Consultant (superadmin) | create and disable client organisations, add their first admin, open any organisation, read pilot requests |

## Security and privacy, as built

- Passwords: scrypt with a random salt; at least 10 characters. Five wrong attempts lock an account for 15 minutes; sign-in is rate limited.
- Sessions: a random token in an HttpOnly, SameSite=Strict cookie (Secure over HTTPS), stored hashed; every change needs a CSRF header.
- API keys: shown once, stored hashed, revocable, 120 requests a minute each.
- Client separation: every query is scoped to the caller's organisation; each organisation has its own event-store file and its own HMAC key,
  derived from the master key, so one client's hashes never match another's.
- Stored: channel, time, score, label, model version, and the recipient and identifiers as HMAC-SHA256. Message text only if the organisation
  turns it on. Alert cases keep the recipient's name and plain indicators unless the organisation turns labels off.
- Retention: a daily purge deletes events, alert cases, notes, scan rows and live-feed rows older than the organisation's retention period.
- Headers: a strict Content-Security-Policy, no framing, no sniffing, no referrer; request bodies over 2 MB are refused (10 MB for one raw
  email on the email webhook). Spreadsheet exports escape formulas.
- Live feed: one row per message with channel, score, source and campaign, never the text. Names and plain indicators only when the organisation
  keeps labels. The live stream checks the session every 30 s and ends when the person signs out or loses access.
- Connector secrets and the webhook signing secret are encrypted at rest and write-only in the API. Mailboxes are opened read-only.
- The server contacts only the mail servers, Microsoft 365 and webhook addresses an admin sets up. It refuses private and local addresses unless
  the operator allows them, so one client's admin cannot make it probe the network it runs in. No link in a message is opened.

## Tests

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests
.venv\Scripts\python.exe scripts\ui_check.py          (with the app running and the demo seeded; drives the installed Chrome)
```

`tests/` covers engine parity with `cp1-final`, sign-in, CSRF, lockout, roles, client separation, API keys, triage, privacy of stored data,
retention, reports, security headers and the mail parsing. For the real-time side it covers:

- the live stream on a real port: a page hears its own organisation's messages and alerts within seconds, and nothing of another's; the
  stream needs a session and ends at sign-out;
- IMAP against a stand-in server: new mail is scored within 5 s with IDLE, older mail is left alone, the mailbox is never changed (read-only,
  no flags), and pausing and resuming skips nothing. Also polling without IDLE, the reporting-mailbox mode, Test connection, a wrong password
  and access by role and organisation;
- Microsoft 365 against a stand-in of the Graph endpoints;
- that no password, secret or message text reaches any stored file;
- the SMS and email webhooks (JSON, Twilio-style form with Basic auth, report-number mode, duplicates, refusals);
- the alert webhook's signature and content, and the refusal of private addresses;
- the demo replay.

`scripts/ui_check.py` opens every page at a laptop and a phone size in Chrome, signs in, scans, investigates, plays the demo replay and checks
that new messages appear in the open Live feed and that an alert pops up, checks for console errors, and checks that the installable app's
service worker registers.

## Layout

| Path | What |
|---|---|
| `backend/server/` | the FastAPI server: `main.py` (app, headers, purge schedule), `routes_*.py`, `engine.py` (the engine and per-client stores), `db.py`, `security.py`, `cli.py` |
| `backend/server/` (real time) | `connectors.py` (IMAP, Microsoft 365 and demo replay threads), `live.py` (the event bus), `routes_live.py` (the live stream), `mailparse.py`, `hooks_out.py` (alert webhook), `secretbox.py` (encrypted secrets) |
| `frontend/` | the React website and web app (`npm run build` writes `frontend/dist`, which the server serves) |
| `engine/` | the pinned cp1-final engine and models, with `ENGINE_MANIFEST.json` |
| `connectors/` | the stand-alone IMAP mail connector, for a mailbox the server cannot reach |
| `scripts/` | `sync_engine.py`, `ui_check.py`, `make_icons.py` |
| `docs/` | `CLIENT_ONE_PAGER.md`, `OPERATIONS.md` |
| `data/` | created at run time: database, master key, client event stores (never in git) |

## Updating the engine

When the CP1 project tags a new build, run `python scripts/sync_engine.py --tag <new tag>`, then the tests. Engine parity must pass against the
new tag's own demo-case expectations before the update is used.
