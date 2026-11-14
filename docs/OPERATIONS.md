# Operations guide

For whoever runs the service for clients.

## First install

1. Install (README: `setup_windows.bat`, `setup.sh`, or Docker). Create the consultant account when asked.
2. Sign in at `/app`, open **Client organisations**, create the client and add its first admin. Give the admin their password privately; they
   change it under **My account**.
3. The client's admin adds analysts and viewers, sets the retention period, and creates an API key for each connector.

## Keys and secrets

- **Master key.** Every client's HMAC key is derived from it, and so is the key that encrypts connector passwords, Microsoft 365 client
  secrets and webhook signing secrets. It lives in `MCPD_MASTER_KEY` or in `data/master.key`. If it is lost, stored hashes can no longer be
  matched (new events stop linking to old ones) and every connector's secret must be entered again. Back it up separately from the data, and
  never into git.
- **API keys** are shown once. If one leaks, revoke it under **Integrations & API** and create a new one.
- **Demo credentials** (`data/demo_credentials.txt`) are for a local demo only. Never seed demo data on a client server.

## Backups

Back up the whole data folder (`MCPD_DATA_DIR`): `app.db` and `orgs/<id>/events.db`. With the service running, copy the SQLite files with
`sqlite3 <file> ".backup <copy>"`, not a plain file copy. Test a restore before the first client depends on it.

## Retention and deletion

- The purge runs every `MCPD_PURGE_INTERVAL_HOURS` (default 24) for every active organisation, using its retention period, and writes an
  `retention.purge` line in its audit log.
- An admin can purge sooner under **Settings & people**.
- To remove a client completely: disable the organisation, then delete `orgs/<id>/` and the organisation's rows in `app.db` (a script for
  this is not built yet; do it by hand, with a backup first).

## Updating

- **The app:** pull the new version, `pip install -r requirements.txt`, `npm ci && npm run build` in `frontend/`, run the tests, restart.
- **The engine:** `python scripts/sync_engine.py --tag <new CP1 tag>`, then `pytest tests`. Engine parity must pass. Tell clients when
  scores may change.

## Real-time sources

- **Connectors run inside the server.** Each active mailbox connector is a thread of the server process; they start with the server and stop
  with it. `MCPD_RUN_CONNECTORS=0` stops the server from reading mailboxes (for example on a second copy restored for a test).
- **One process.** Live updates and connectors assume one server process. Do not start uvicorn with `--workers` above 1; several processes or
  servers would need a message broker, which is not built.
- **Stopping.** The start scripts pass `--timeout-graceful-shutdown 3`, because open live streams would otherwise keep the server waiting.
- **Gmail and Google Workspace.** IMAP must be on for the mailbox, and the connector needs an app password (2-step verification on). A
  Workspace admin may have to allow IMAP.
- **Microsoft 365.** Register an app in Microsoft Entra, give it the Mail.Read application permission with admin consent, create a client
  secret, and restrict the app to the one mailbox with an application access policy. Client secrets expire: note the date and replace the
  secret in the connector before then.
- **Private networks.** The server refuses private and local addresses for mailboxes and webhooks. On an install inside a client's network
  that must reach an on-premises mail server, set `MCPD_ALLOW_PRIVATE_HOSTS=1`, and only there.
- **Watching an inbox** reads everything that person receives. Agree it in writing with the client, and make sure the people concerned have
  been told, before you switch it on.
- **A connector in error** shows its last problem on the Connectors page and retries with a growing pause (up to 5 minutes). Common lines:
  "Invalid credentials" (password or app password), "certificate did not verify" (wrong host or security setting), "HTTP 403" from Microsoft
  (permission or consent missing).
- **Demo replay.** `python -m server.cli seed-demo` adds one to the demo organisation only. Never run `seed-demo` on a client server.

## Monitoring

- `GET /api/health` answers `ok`, or `degraded` when a model file is missing (that channel then shows "not assessed").
- The server prints errors only, never message content. Run uvicorn with `--no-access-log` (the scripts do), because access lines can carry
  query strings.
- Check the audit log for repeated `auth.login_failed` lines.
- Check the Connectors page (or the Live feed's source cards) for a connector in "Problem", and the alert webhook's last result.

## Before a client relies on it

These are not done yet: a penetration test, a load test, a restore drill, a data processing agreement template, an evaluation on the
client's own traffic, and a first run of each connector against a real mailbox (they were tested only against stand-ins). Do them, and record
the results, before the pilot moves to real use.
