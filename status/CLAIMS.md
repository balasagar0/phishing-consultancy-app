# Claims to fact-check

Every checkable claim in [DONE.md](DONE.md) and [TODO.md](TODO.md). The fact-check session of 17 Nov 2026 filled the last column with one
of: **Confirmed**, **Wrong** (with what is true), or **Could not check** (with why), and wrote the details in `FACTCHECK_REPORT.md`.

Paths: `P` is `D:\Capstone_HTE Project\prototype\project`, `A` is `D:\Capstone_HTE Project\prototype\app`. Both are git repositories. Use
each folder's own `.venv`. The paths have a space: quote them.

## CP1 project

| # | Claim | How to check | Fact-check |
|---|---|---|---|
| C-01 | Tag `cp1-final` points at commit `18ba1d9` (7 Nov 2026) | `git -C P rev-parse cp1-final^{commit}`; `git -C P log -1 cp1-final` | **Confirmed**. `cp1-final` is an annotated tag on `18ba1d9`, dated 7 Nov 2026 |
| C-02 | Neither repository has a remote; nothing was pushed | `git -C P remote -v` and `git -C A remote -v` print nothing | **Confirmed**. No remote and no remote-tracking ref in either repository |
| C-03 | `CHECKLIST_STATUS.md` marks all six phases done, last updated 14 Nov 2026 | Read the top of `P/CHECKLIST_STATUS.md` and its phase table | **Confirmed**. Line 5: end of Phase 6, 14 Nov 2026; Phases 0 to 6 all 'done'. It says 'six' but lists seven (0 to 6) |
| C-04 | The Phase 5 documents are generated from `cp1-final` and pass their checks | In P: `.venv\Scripts\python.exe -m pytest tests/test_documents.py -q`. Then `git status`: if `reports/final_cases_results.json` changed, `git checkout` it (see P's `CLAUDE.md`) | **Confirmed**. 5 passed; `git status` clean afterwards, nothing to restore |
| C-05 | The final run was recorded and not adopted; v2's models stay live | `P/reports/final_run/README.md`; P's `CLAUDE.md`, decision of 7 Nov 2026 | **Confirmed** |
| C-06 | `docs/BUILT_VS_DESCRIBED.md` does not exist, but `CHECKLIST_STATUS.md` row R3-01 points to it | `dir P\docs`; search `CHECKLIST_STATUS.md` and `docs/PHASE6_SUMMARY.md` for the name | **Confirmed**. The name is also in row PT-04 and in `PROJECT_STATUS_AND_ROADMAP.md`, line 80 |
| C-32 | The app work did not change the CP1 project: its last commit is `ec411d2` (14 Nov 2026, 10:59) and its working tree is clean | `git -C P log -1`; `git -C P status --short` | **Confirmed**. `ec411d2`, 14 Nov 2026 10:59 +0530; tree clean |

## The app: history, engine, tests

| # | Claim | How to check | Fact-check |
|---|---|---|---|
| C-07 | A is its own repository with the commits `e1d2764`, `ddaa1ee` and `1b690e9` (14 Nov 2026), then this status folder | `git -C A log --oneline` | **Confirmed**. Then `5f1c27d` (17 Nov 2026), the status folder |
| C-08 | Every file in `A/engine` matches `cp1-final` | In A: `.venv\Scripts\python.exe scripts\sync_engine.py --verify` | **Wrong** in part. `--verify` passes and the 13 files taken from `cp1-final` match the tag byte for byte, but `final_numbers.json` is not in `cp1-final`: it comes from `191e335` (14 Nov). DONE.md corrected |
| C-09 | The app scores the eight demo cases as `cp1-final` does; TC-06's bundle risk is 0.595 | `A/tests/test_engine_parity.py`; compare with the demo-case table in P's `CLAUDE.md` | **Confirmed**. The 3 parity tests pass; their expected values equal the table in P's `CLAUDE.md` |
| C-10 | 44 tests pass in A | In A: `.venv\Scripts\python.exe -m pytest tests -q` (about 40 s) | **Confirmed**. 44 passed, 2 warnings, 37.9 s (re-run 17 Nov) |
| C-11 | The Chrome check passed 52 of 52 on 14 Nov 2026, including the live checks | `A/data/ui_check.json` (outside git). To re-run: the server on port 8765 with the demo seeded, then `.venv\Scripts\python.exe scripts\ui_check.py`. It plays the demo replay, which adds demo rows to `A/data` | **Confirmed** from the record (not re-run): 52 entries, all ok, file written 14 Nov 2026 14:28. The live checks ran at laptop size only |
| C-31 | `cryptography==50.0.2` was added to `requirements.txt` and `requirements.lock.txt` | Read both files; `git -C A show 1b690e9 -- requirements.txt` | **Confirmed**. The lock file also gained `cffi` and `pycparser`; DONE.md now says so |

## The app: security and clients

| # | Claim | How to check | Fact-check |
|---|---|---|---|
| C-12 | Roles are viewer, analyst, admin and consultant (superadmin), enforced on every route | `A/backend/server/db.py` (ROLES), `deps.py` (`need`), `tests/test_auth_and_roles.py` | **Confirmed**. Of 56 API routes, 51 need a session or an API key (roles through `need`); 5 are public by design |
| C-13 | scrypt passwords; HttpOnly SameSite=Strict session cookie; CSRF header on every change; lockout after 5 wrong passwords for 15 minutes; a strict CSP | `security.py`, `deps.py`, `routes_auth.py`, `config.py`; the tests in `test_auth_and_roles.py` | **Confirmed**. The 15-minute lock is in code, not in a test; the CSP allows inline styles, not inline scripts |
| C-14 | Each organisation has its own event-store file and an HMAC key derived from the master key; no data crosses | `engine.py` (`org_key`, `store`); `tests/test_tenancy_and_ingest.py::test_organisations_are_separate` | **Confirmed** |
| C-15 | Connector secrets are encrypted with AES-256-GCM and never returned by the API | `secretbox.py`; `connectors.public()` returns `has_secret` only; `test_connectors.py` checks no password reaches a stored file | **Confirmed** |
| C-25 | Connectors and alert webhooks refuse private and local addresses unless `MCPD_ALLOW_PRIVATE_HOSTS=1` | `security.vet_host`, `vet_url`; `test_webhooks.py::test_private_addresses_are_refused_unless_the_operator_allows_them` | **Confirmed** |
| C-34 | The server contacts no outside service except the mail servers, Microsoft 365 and webhook addresses an admin sets up | Search `A/backend` for `urlopen`, `opener.open`, `socket`, `requests`, `httpx`, `smtplib`; `A/engine` is the pinned CP1 code | **Confirmed**. Only the IMAP host, two fixed Microsoft addresses and webhook addresses; the engine's `tldextract` runs offline |
| C-35 | The demo passwords are only in `A/data/demo_credentials.txt`, which git ignores | `git -C A check-ignore -v data/demo_credentials.txt`; search the tracked files for "demo_credentials". Do not print the passwords | **Confirmed**. Ignored by `.gitignore` line 1; the 4 passwords are in no other file and no commit (checked without printing them) |

## The app: real time

| # | Claim | How to check | Fact-check |
|---|---|---|---|
| C-16 | The IMAP connector opens the folder read-only (EXAMINE) and never sends STORE, COPY, MOVE or EXPUNGE | `connectors.py` (`select(..., readonly=True)`, no flag commands); `test_connectors.py::test_an_imap_inbox_is_read_live_and_never_changed` | **Confirmed** for the server's connector. The stand-alone `connectors/imap_connector.py` does mark messages read; DONE.md now says so |
| C-17 | With IMAP IDLE, a new message is recorded within 5 s; without IDLE the folder is checked every 30 s by default (10 s at least) | `connectors._idle`, `imap_session`; the `< 5` assertion in `test_connectors.py`; `routes_connectors.ImapCfg.poll_seconds` | **Confirmed**, against the stand-in only |
| C-18 | Only mail that arrives after a connector starts is read; pausing and resuming skips nothing | `_start_point`, the saved `last_uid`; the same test (the "already there" and "arrives while paused" messages) | **Confirmed** for the default. `backfill` (0 to 50) can take the last few; a new UIDVALIDITY or a changed host, user or folder starts afresh |
| C-19 | Microsoft 365 works through Microsoft Graph with client credentials, polling every 30 s by default (15 s at least) | `connectors.Graph`, `graph_session`; `routes_connectors.GraphCfg`; `test_connectors.py::test_a_microsoft_365_mailbox_through_graph` | **Confirmed**, against the stand-in only |
| C-20 | No connector has run against a real Gmail, Google Workspace, Microsoft 365 or Zoho account; the tests use stand-ins | `A/tests/fakes.py`; the tests' imports; there is no account or secret anywhere in A | **Confirmed**. The only connector ever saved in `A/data` is the demo replay; no `.env` file |
| C-21 | `POST /api/v1/hooks/sms` takes JSON or a Twilio-style form, an API key by Bearer, X-API-Key or HTTP Basic, and `mode=reports`; `POST /api/v1/hooks/email` takes one raw email up to 10 MB | `routes_ingest.py`, `deps._key_of`, `main.Guard` (MAX_EMAIL); `tests/test_webhooks.py` | **Confirmed**. The X-API-Key header is handled in code, but no test sends it |
| C-22 | The live stream (`/api/live/stream`) gives each organisation only its own events, needs a session and an organisation, and ends at sign-out | `routes_live.py`; `tests/test_live_stream.py` (on a real port) | **Confirmed**. It ends at the next session check, every 30 s (the test shortens that to 0.3 s); DONE.md now says so |
| C-23 | The live feed never stores message text | `db.MessageLog` has no text column; `services.record_events`; the marker checks in `test_connectors.py` and `test_tenancy_and_ingest.py` | **Confirmed** |
| C-24 | The alert webhook is signed (`X-MCPD-Signature: sha256=` HMAC of "timestamp.body"), holds no message text, and does not follow redirects | `hooks_out.py`, `security.no_redirect_opener`; `test_webhooks.py` (signature, marker, redirect) | **Wrong** in part. Signed only when the admin sets a signing secret, which is optional. No message text and no redirects: confirmed. DONE.md corrected |
| C-26 | Only the command line can create a demo replay; the API accepts only `imap` and `graph` | `routes_connectors.ConnectorIn.kind`; `cli.add_demo_replay` | **Confirmed** |
| C-27 | Each demo replay run uses fresh made-up recipients (`.r2`, `.r3` and so on) | `connectors.demo_session` | **Confirmed**. Run 1 uses the plain addresses, run 2 `.r2`, and so on |
| C-29 | Live updates and connectors assume one server process; no broker is built | `live.py` docstring; no Redis or queue in `requirements.txt` | **Confirmed** |
| C-30 | The daily purge also deletes live-feed rows and the keys of messages already seen | `services.purge_org` | **Confirmed** |
| C-33 | The demo replay's campaign risks differ from the demo-case table, because its messages are seconds apart | `connectors.demo_session` sets each message's time to now. To see it, use a throw-away data folder (`MCPD_DATA_DIR`) and a second port, never the demo data in `A/data` | **Confirmed** in a throw-away data folder: TC-06 did not come out at 0.595 in the replay (details in the report) |

## The app: not done

| # | Claim | How to check | Fact-check |
|---|---|---|---|
| C-28 | The Docker image and compose file were never built or run; Docker is not installed on this laptop | `docker --version` fails; the note in `A/README.md` and the `Dockerfile` header | **Confirmed**. `docker` is not found in Git Bash or PowerShell |
