# Operations guide

For whoever runs the service for clients.

## First install

1. Install (README: `setup_windows.bat`, `setup.sh`, or Docker). Create the consultant account when asked.
2. Sign in at `/app`, open **Client organisations**, create the client and add its first admin. Give the admin their password privately; they
   change it under **My account**.
3. The client's admin adds analysts and viewers, sets the retention period, and creates an API key for each connector.

## Keys and secrets

- **Master key.** Every client's HMAC key is derived from it. It lives in `MCPD_MASTER_KEY` or in `data/master.key`. If it is lost, stored
  hashes can no longer be matched, so new events stop linking to old ones. Back it up separately from the data, and never into git.
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

## Monitoring

- `GET /api/health` answers `ok`, or `degraded` when a model file is missing (that channel then shows "not assessed").
- The server prints errors only, never message content. Run uvicorn with `--no-access-log` (the scripts do), because access lines can carry
  query strings.
- Check the audit log for repeated `auth.login_failed` lines.

## Before a client relies on it

These are not done yet: a penetration test, a load test, a restore drill, a data processing agreement template, and an evaluation on the
client's own traffic. Do them, and record the results, before the pilot moves to real use.
