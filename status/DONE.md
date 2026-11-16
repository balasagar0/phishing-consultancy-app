# What was done

Each line names the commit, file or test that shows it. CLAIMS.md lists the checkable ones with a claim number (C-01 and so on).

## 1. The CP1 project (`prototype/project`)

The CP1 finish task (`CP1_FINISH_TASK.md`, Phases 0 to 6) is done. The owner's summary is `docs/PHASE6_SUMMARY.md`; the status of all 69
checklist items is `CHECKLIST_STATUS.md`; every number is in `reports/FINAL_NUMBERS.md`.

| Phase | Done on | What | Shown by |
|---|---|---|---|
| 0. Baseline | 2 Nov 2026 | v2 reproduced; models and reports backed up; rules and checklist set up | tag `v2-baseline`, tag `test-run-20261102-0`, `reports/baseline_check.md` |
| 1. Tests and defects | 2 Nov 2026 | The test plan's 112 cases ported; defects fixed, one regression test each | tag `test-run-20261102-1`, `tests/test_final_cases.py`, `tests/test_defects.py`, `reports/defect_log.md` |
| 2. Live flow | 2 Nov 2026 | Event store with hashed identities, campaigns and alerts; the console served by the API | tag `test-run-20261102-2`, `src/event_store.py`, `console/` |
| 3. Models | 7 Nov 2026 | Three email retrain attempts and URL and SMS checks; none adopted; the private-mail pipeline built and audited | tag `test-run-20261107-3`, `reports/candidates/`, `PRIVACY_AND_ETHICS.md` |
| 4. Freeze | 7 Nov 2026 | Tags `cp1-rc1` and `cp1-final`; the final run recorded and not adopted, so v2's models stay live; every check run on `cp1-final` | tag `cp1-final` (commit `18ba1d9`, C-01), `reports/final_run/README.md` (C-05), `reports/exit_criteria.md` |
| 5. Documents | 7 Nov 2026 | One set of numbers and every document generated from it by code | merge `bbb67c2`, `scripts/make_documents.py`, `docs/templates/`, `tests/test_documents.py` (C-04) |
| 6. Wrap-up | 14 Nov 2026 | The owner's summary; the checklist finished | merge `ec411d2`, `docs/PHASE6_SUMMARY.md`, `CHECKLIST_STATUS.md` (C-03) |

Decisions the owner made and that the build follows (from the project's `CLAUDE.md`):

- Voice stays out of CP1: calls and video are "not assessed", never safe.
- The patent will be written from this build (`docs/PATENT_BASIS.md`), not from the old specification.
- v2's email model stays live; the final run's retrain was recorded and not adopted.
- The owner's mail export and the v3 model stay on the laptop, outside git.
- Git stays local: no remote, no push (C-02).

## 2. The consultancy app (`prototype/app`)

A separate git repository (C-07). The CP1 project was not changed by any of this work (C-32).

### 2.1 The engine, pinned (commit `e1d2764`, 14 Nov 2026)

- `engine/` is a read-only copy of the CP1 files at `cp1-final`, taken with `git archive` by `scripts/sync_engine.py`, with SHA-256 hashes in
  `engine/ENGINE_MANIFEST.json`. `sync_engine.py --verify` checks every file (C-08).
- `tests/test_engine_parity.py` checks that the app scores the eight demo cases exactly as `cp1-final` does, for example TC-06 = 0.595 (C-09).

### 2.2 Website and web app (commit `ddaa1ee`, 14 Nov 2026)

- **Website** at `/`: home, how it works, results with their limits (read from the pinned build's numbers file, never typed), privacy, and a
  "request a pilot" form.
- **Web app** at `/app`: dashboard, scan a message, investigate a set of messages, alert queue with triage (new, investigating, confirmed,
  false alarm, closed), assignment and notes, campaigns with timelines, CSV and printable reports, people and roles, API keys, retention and
  privacy settings, audit log, and a consultant view over every client organisation.
- **Several clients on one install**: each organisation has its own people, API keys, event-store file and HMAC key derived from the master key
  (C-14). Roles: viewer, analyst, admin, consultant (C-12).
- **Security as built**: scrypt passwords, an HttpOnly SameSite=Strict session cookie, a CSRF header on every change, lockout after five wrong
  passwords, rate limits, hashed API keys, a strict Content-Security-Policy (C-13).
- **Installable** as a progressive web app.
- **Packaging**: setup and start scripts for Windows and Linux; a Dockerfile, a compose file and a Caddyfile for HTTPS, written but never built
  or run (C-28).
- **Docs**: `README.md`, `docs/OPERATIONS.md`, `docs/CLIENT_ONE_PAGER.md`.

### 2.3 Real time (commit `1b690e9`, 14 Nov 2026)

Messages arrive by themselves; nobody has to paste them.

- **Mailbox connectors run by the server** (`backend/server/connectors.py`), set up on the **Connectors** page:
  - IMAP: uses IMAP IDLE where the server offers it, and checks every 30 s where it does not (C-17).
  - Microsoft 365 through Microsoft Graph, with an app registration and a client secret (C-19).
  - Each reads a reporting mailbox (staff forward suspicious mail) or watches an inbox (the owner is the recipient).
  - Read-only: the folder is opened with EXAMINE, and nothing is flagged, moved or deleted (C-16). Only new mail is read, and a pause or restart
    skips nothing (C-18).
  - Passwords and client secrets are encrypted with AES-256-GCM (`secretbox.py`) and never returned by the API (C-15).
  - Private and local addresses are refused unless the operator allows them (C-25).
- **Webhooks** (`routes_ingest.py`): `POST /api/v1/hooks/sms` (JSON, a Twilio-style form, HTTP Basic, a report-number mode) and
  `POST /api/v1/hooks/email` (one raw email, up to 10 MB) (C-21).
- **Live stream**: an in-process event bus (`live.py`) and Server-Sent Events at `/api/live/stream`. Each organisation hears only its own
  events, and the stream ends when the person signs out (C-22).
- **Live feed** page: one row per message with channel, source, recipient, score and campaign, never the text (C-23). The dashboard, alerts and
  campaigns update by themselves. New alerts pop up on screen, with optional desktop notifications.
- **Alert webhook** (`hooks_out.py`): a signed JSON notice the moment an alert opens; redirects are not followed (C-24).
- **Demo replay**: replays the hand-written demo cases with the current time, one every 4 s, for demos. Only the command line can create one
  (C-26). Each run uses fresh made-up recipients (C-27).
- **Retention**: the daily purge also deletes live-feed rows and the keys of messages already seen (C-30).
- One new package, `cryptography==50.0.2` (C-31).

### 2.4 Checks run on 14 Nov 2026

| Check | Result | Claim |
|---|---|---|
| `pytest tests` in `app/` | 44 passed | C-10 |
| `scripts/ui_check.py` in the installed Chrome, laptop and phone sizes | 52 of 52 passed, including new messages appearing in an open Live feed and an alert popping up | C-11 |
| `scripts/sync_engine.py --verify` | every engine file matches `cp1-final` | C-08 |
| `git status` in `project/` after the app work | clean | C-32 |

### 2.5 What was not verified

- The connectors never ran against a real Gmail, Google Workspace, Microsoft 365 or Zoho mailbox. They were tested against stand-ins in
  `tests/fakes.py` (C-20).
- The Docker image and the compose file were never built (Docker is not installed on this laptop) (C-28).
- No penetration test, no load test, no restore drill, no run on a client's real traffic.
- PostgreSQL support exists in configuration only; every test used SQLite.
