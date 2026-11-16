# Fact-check report

Written 17 Nov 2026 by a separate Claude Code session, started by the session that wrote this folder. It checks the status folder at commit
`5f1c27d` of the app repository.

**Result: 33 claims Confirmed, 2 Wrong (C-08, C-24), 0 Could not check.** Three other statements in DONE.md, TODO.md and README.md were
wrong or incomplete, and were corrected. Every verdict rests on something seen in this session: a command and its output, or a file and line.

## How it was checked

- `P` is `D:\Capstone_HTE Project\prototype\project`, `A` is `D:\Capstone_HTE Project\prototype\app`. Each folder's own `.venv` was used.
- In P, only `tests/test_documents.py` was run. `git status` in P was clean before and after; nothing had to be restored.
- In A, the whole test suite was run once. `scripts/ui_check.py` was not re-run; C-11 rests on `A/data/ui_check.json`.
- The routes and their sign-in checks (C-12) were listed by importing the app with `MCPD_DATA_DIR` set to a throw-away folder.
- C-33 was checked without a second server: a script ran the app's own `connectors.demo_session` twice in a throw-away data folder in the
  session's scratchpad. That folder was deleted afterwards. `A/data` was only read, and its database only opened read-only.
- The demo passwords were never printed. A script read them and counted matches in other files and in git history.
- No mail content was read. Nothing named `email_own` and no mail export was touched.
- The scores quoted below are of the hand-written demo cases. They are demos, not a test set, and no rate is computed from them.

## The claims

### CP1 project

| # | Verdict | Evidence | Correction |
|---|---|---|---|
| C-01 | Confirmed | `git rev-parse cp1-final^{commit}` printed `18ba1d94b103…`. `git log -1 cp1-final`: `2026-11-07 16:49:46 +0530`, "Merge module/testing-docs: Phase 4 checks before cp1-final". `cp1-final` is an annotated tag (object `7fd59ec`) | None |
| C-02 | Confirmed | `git remote -v` printed nothing in P or in A. Neither has a `remote.*` setting or any `refs/remotes/` ref, so neither has pushed to a tracked remote | None |
| C-03 | Confirmed | `P/CHECKLIST_STATUS.md:5`: "end of Phase 6 (wrap-up), 14 Nov 2026. All six phases done." The phase table (lines 15–21) marks Phases 0 to 6 "done" | None to the claim. The checklist says "six" but lists seven phases (0 to 6). This is a finding in P, added to TODO.md section 4 |
| C-04 | Confirmed | `.venv\Scripts\python.exe -m pytest tests/test_documents.py -q` printed `5 passed in 0.68s`. `git status --short` afterwards printed nothing, so `reports/final_cases_results.json` did not change | None |
| C-05 | Confirmed | `P/reports/final_run/README.md:9`: "**Not adopted.**" (rule (c) fails on TC-06; "The shipped models are v2's"). P's `CLAUDE.md:171` records the 7 Nov decision | None |
| C-06 | Confirmed | `docs/BUILT_VS_DESCRIBED.md` does not exist in `P/docs`. `CHECKLIST_STATUS.md:70` (R3-01) and `docs/PHASE6_SUMMARY.md:89` point to it. `scripts/render_docs.py:46` reads the checklist, which is why the summary repeats it | None to the claim. The name also appears in `CHECKLIST_STATUS.md:100` (PT-04, column "Inputs: BUILT_VS_DESCRIBED") and `PROJECT_STATUS_AND_ROADMAP.md:80`. Added to TODO.md section 4 |
| C-32 | Confirmed | `git -C P log -1`: `ec411d2 2026-11-14 10:59:33 +0530`. `git -C P status --short` printed nothing, before and after this check | None |

### The app: history, engine, tests

| # | Verdict | Evidence | Correction |
|---|---|---|---|
| C-07 | Confirmed | `git -C A log`: `e1d2764` (14 Nov 11:42:12), `ddaa1ee` (14 Nov 11:42:13), `1b690e9` (14 Nov 14:32:43), `5f1c27d` (17 Nov 00:29:51), all by the configured identity | None |
| C-08 | **Wrong** in part | `scripts\sync_engine.py --verify` printed "engine verified: every file matches cp1-final". The blob hash of each of the 13 files taken from the tag (`api.py`, six `src/` files, four models, `requirements.txt`, `tests/test_demo_cases.py`) equals `git -C P rev-parse cp1-final:<path>`. But the 14th file, `engine/final_numbers.json`, is not in `cp1-final` ("path … exists on disk, but not in 'cp1-final'"). Its blob equals `191e335:reports/final_numbers.json` (14 Nov), and its `build.commit` field is `18ba1d9`. `--verify` checks the app's own manifest and the tag's model manifest; it does not read the tag again (`sync_engine.py:51-62`) | The 13 code and model files match `cp1-final` byte for byte. The numbers file comes from commit `191e335`, written from `cp1-final` and committed after the tag. DONE.md 2.1 and 2.4 corrected |
| C-09 | Confirmed | `tests/test_engine_parity.py` (3 tests) passed in the full run. Its expected values come from `engine/tests/test_demo_cases.py:12-20`, which is byte-identical with `cp1-final`. They equal the demo-case table in P's `CLAUDE.md` for TC-01 to TC-08, including TC-06 = 0.595 | None |
| C-10 | Confirmed | `.venv\Scripts\python.exe -m pytest tests -q`: `44 passed, 2 warnings in 37.87s`. The 8 test files hold 8+3+5+3+3+7+7+8 = 44 tests. `git status` in A was clean afterwards (the tests use a temporary data folder) | None |
| C-11 | Confirmed (from the record) | `A/data/ui_check.json`: 52 entries, all `"ok": true`, file written 14 Nov 2026 14:28. The live checks are entries 24–27: the stream connects, "42 rows before, 45 after, 12 s", an alert pops up, the dashboard shows the live status. `scripts/ui_check.py:32` launches `channel="chrome"` | None. Note: the live checks ran at laptop size only; the phone run has none. Not re-run in this session |
| C-31 | Confirmed | `requirements.txt:16` and `requirements.lock.txt:9`: `cryptography==50.0.2`. `git show 1b690e9` adds both lines. The installed version prints `50.0.2` | None to the claim. The same commit also added `cffi==2.1.1` and `pycparser==3.12` to the lock file, so "one new package" in DONE.md was corrected |

### The app: security and clients

| # | Verdict | Evidence | Correction |
|---|---|---|---|
| C-12 | Confirmed | `db.py:8`: `ROLES = ("viewer", "analyst", "admin", "superadmin")`; `db.py:34` calls the superadmin the consultant. Listing all 56 API routes with their dependencies: 42 use `need(<role>)`, 3 use `session_ctx`, `/api/live/stream` calls `session_ctx` in its body (`routes_live.py:24`), 5 use an API key. The 5 open routes are `/api/health`, `/api/public/model-card`, `/api/public/contact`, `/api/auth/login` and `/api/auth/me` (which answers "not signed in"). `test_auth_and_roles.py::test_roles` passed | None |
| C-13 | Confirmed | scrypt: `security.py:12`. Cookie: `routes_auth.py:51` (`httponly=True`, `samesite="strict"`). CSRF on POST, PUT, PATCH and DELETE: `deps.py:38`. Lockout: `config.py:40-41` (5 tries, 15 minutes), `routes_auth.py:43`. CSP: `security.py:62`. Tests `test_session_cookie_is_http_only_and_strict`, `test_state_change_needs_the_csrf_token` and `test_lockout_after_repeated_failures` passed | None. Notes: the 15-minute length is in code, not in a test. The CSP allows inline styles (`style-src 'self' 'unsafe-inline'`), not inline scripts |
| C-14 | Confirmed | `engine.py:41-42`: `org_key` is HMAC-SHA256 of `org:<id>` under the master key. `engine.py:50`: each organisation's store is `orgs/<id>/events.db`. `test_organisations_are_separate` passed | None |
| C-15 | Confirmed | `secretbox.py:9-23`: AES-GCM with a 32-byte key (HMAC-SHA256 of the master key), so AES-256. `connectors.py:46` (`public`) and `routes_connectors.py` `hook_out` return `has_secret` only. `test_connectors.py:28` and `:38` check that no secret is returned or stored in clear | None |
| C-25 | Confirmed | `security.py:76-108`: `vet_host` refuses any address that is not global unless `MCPD_ALLOW_PRIVATE_HOSTS` is on; `vet_url` also refuses plain http. `test_private_addresses_are_refused_unless_the_operator_allows_them` passed | None |
| C-34 | Confirmed | Searching `A/backend` for `urlopen`, `opener.open`, `socket`, `requests`, `httpx`, `smtplib` and `http.client` finds only the IMAP connection (`connectors.py:85-89`), Graph through `no_redirect_opener` (`connectors.py:209`, addresses fixed at `connectors.py:30-31`), the alert webhook (`hooks_out.py:47`) and DNS lookups in `vet_host`. `A/engine` has no network call, and `url_features.py:7` sets `tldextract` offline. The frontend loads nothing from outside | None |
| C-35 | Confirmed | `git check-ignore -v data/demo_credentials.txt` printed `.gitignore:1:data/`. In tracked files, "demo_credentials" appears only as a file name (README, `cli.py`, `docs/OPERATIONS.md`, `scripts/ui_check.py`, CLAIMS.md). A script found 4 passwords in the file (not printed), then found none of them in any other file in A (outside `.venv`, `node_modules`, `.git`) and none in the 4 commits | None |

### The app: real time

| # | Verdict | Evidence | Correction |
|---|---|---|---|
| C-16 | Confirmed (server connector) | `connectors.py:170`: `m.select(..., readonly=True)`; Python's `imaplib` sends `EXAMINE` for that. `connectors.py:132` fetches with `BODY.PEEK[]`. No STORE, COPY, MOVE or EXPUNGE in `backend/`. `test_an_imap_inbox_is_read_live_and_never_changed` passed; it asserts EXAMINE and `not f.changed_mailbox()` | None to the claim. But the stand-alone script `connectors/imap_connector.py` opens the folder with SELECT (line 26) and marks messages read with `UID STORE +FLAGS (\Seen)` (lines 32, 36). Its own docstring says so. DONE.md now says so too |
| C-17 | Confirmed (stand-in only) | `connectors.py:136` (`_idle`) and `:163-189`. `test_connectors.py:33` asserts under 5 s, and passed against `FakeImap`. Without IDLE: `routes_connectors.py:27` (`default=30, ge=10`) and `connectors.py:164` (`max(10, …)`) | None |
| C-18 | Confirmed (default settings) | `connectors.py:110` (`_start_point`) starts at UIDNEXT − 1 when `backfill` is 0; `last_uid` is saved after each message. The same test checks that the "already there" message is not read and the "arrives while paused" one is read after resuming | None. Notes: `backfill` (0 to 50, `routes_connectors.py:29`) can ask for the last few messages. A new UIDVALIDITY, or a changed host, user or folder, starts afresh from new mail |
| C-19 | Confirmed (stand-in only) | `connectors.py:215-241` (`Graph`, `grant_type=client_credentials`), `:245` (`max(15, …)`), `routes_connectors.py:39` (`default=30, ge=15`). `test_a_microsoft_365_mailbox_through_graph` passed against `FakeGraph` | None |
| C-20 | Confirmed | `tests/fakes.py:1-5` (FakeImap, FakeGraph, Receiver); the Graph test points the connector at `127.0.0.1`. No real mail host appears in `tests/`. A has no `.env`. In `A/data/app.db` (read-only) the only connector is the demo replay, the audit log has no `connector.created`, and there are no API keys and no alert webhooks | None. Note: `A/data` holds demo accounts and a local `master.key`, but no mailbox account or secret |
| C-21 | Confirmed | `routes_ingest.py`: JSON or form (`hook_sms`), `?mode=reports`, a raw email for `/hooks/email`. `deps.py:52` (`_key_of`): Bearer, HTTP Basic, X-API-Key. `main.py:21,57`: 11 MB request limit for the email hook; `mailparse.py:15` and `services.py:102`: a message over 10 MB is refused. The 5 SMS and email webhook tests passed | None. Note: no test sends the key as `X-API-Key` |
| C-22 | Confirmed | `routes_live.py:24-31` needs a session and an organisation; it subscribes to that organisation only. The 3 tests in `test_live_stream.py` passed on a real port | None to the claim. The stream ends at its next session check: `RECHECK_S = 30` (`routes_live.py:21`); the test shortens it to 0.3 s. DONE.md now says so |
| C-23 | Confirmed | `db.py:149-168`: `MessageLog` has no text column. `services.py:68-95` (`record_events`) writes only channel, source, score, label, campaign and tokens. The marker checks (`test_connectors.py:38`, `test_nothing_readable_is_kept_in_the_event_store`) passed | None |
| C-24 | **Wrong** in part | The header and HMAC are as stated (`hooks_out.py:45`), and the test checks them. But the signature is added only `if secret:`, and the secret is optional (`routes_connectors.py:164`: `secret: str \| None = None`). Without one, the notice goes unsigned. No message text (`hooks_out.py:27-36`, marker test) and no redirects (`security.py:113`, `test_an_alert_webhook_does_not_follow_redirects`): confirmed | The notice is signed only when the admin sets a signing secret. DONE.md 2.3 corrected |
| C-26 | Confirmed | `routes_connectors.py:67` and `:81`: `kind: Literal["imap", "graph"]`; `:112` refuses config or secret changes on a demo source. Only `cli.py:89-95` (`add_demo_replay`) creates `kind="demo"` | None |
| C-27 | Confirmed | `connectors.py:304`: `person.replace("@", f".r{run}@")` when `run > 1`. In the throw-away replay, run 1 wrote 25 feed rows to the plain addresses and run 2 wrote 25 to `.r2` addresses, each opening its own campaigns. `ui_check.json` entry 26 also shows a `.r2` address | None. Note: the run number lives in the demo source's state, so deleting and re-creating that source starts again at run 1 |
| C-29 | Confirmed | `live.py:6`: "One server process only. With several processes or servers, put a broker … behind publish()". No Redis, Celery, Kafka, RabbitMQ or queue package in either requirements file | None |
| C-30 | Confirmed | `services.py:130` deletes `MessageLog` rows and `:131` deletes `SeenMessage` rows older than the cut-off. `db.py:171-172` describes `SeenMessage` as keyed hashes of messages already recorded | None |
| C-33 | Confirmed | `connectors.py:305` sets each message's time to now. The throw-away replay (25 messages from 11 stories, 4 s apart, 104 s) gave TC-06 a campaign risk of 0.579. Run 2 (0.05 s apart) gave 0.53. TC-06 with its own times (0, 7, 15 min) through the same engine gives 0.595. TC-01, TC-02, TC-04, TC-05 and TC-08 matched the table at 4 s spacing; at 0.05 s spacing TC-08 showed 0.999. These are hand-written demo cases, not a test set | None |

### The app: not done

| # | Verdict | Evidence | Correction |
|---|---|---|---|
| C-28 | Confirmed | `docker --version` in Git Bash: "docker: command not found". `Get-Command docker` in PowerShell found nothing, and `C:\Program Files\Docker` does not exist. `Dockerfile:2`, `docker-compose.yml:5` and `README.md:80` say it was not run | None |

## Other statements in DONE.md, TODO.md and README.md

Checked and true:

- DONE.md section 1: each phase's date matches its tag or merge (`v2-baseline` and `test-run-20261102-0` to `-2` on 2 Nov; `test-run-20261107-3`,
  `cp1-rc1` and `cp1-final` on 7 Nov; `bbb67c2` on 7 Nov; `ec411d2` on 14 Nov). Every file it names exists in P. The checklist has 69
  item rows. The five owner decisions match P's `CLAUDE.md`.
- DONE.md section 2: the website pages, the triage states (`db.py:10`), desktop notifications (`Live.jsx:17-23`), the PWA files, the setup
  and start scripts, the Docker, compose and Caddy files, and the three docs all exist. The results page holds no typed percentage. Demo
  replay: one message every 4 s (`cli.py:93`). WAL mode: `db.py:215-216`. "Every test used SQLite": `tests/conftest.py:10-11`.
- TODO.md section 1: PT-01 to PT-09 are the filing steps (PT-10 is "keep everything private", done). The client one-pager promises a written
  agreement first, naming India's DPDP Act, 2023 (`docs/CLIENT_ONE_PAGER.md:35`).
- TODO.md section 2: the 18 areas match Part 3 of `PROJECT_STATUS_AND_ROADMAP.md` (lines 151–174). There is no CI configuration in A.
  `docs/OPERATIONS.md:31` covers removing a client by hand. The two pytest warnings are the two seen in this session's run. The frontend uses
  `react-router-dom` 6.28.0, which warns about version 7. The browser console itself was not opened in this session.
- TODO.md section 3 matches section 4 of `P/docs/PHASE6_SUMMARY.md`. `P/reports/exit_criteria.md:14` shows criterion 7 "Not met" on three
  High defects (D-01, D-09, D-17).
- TODO.md section 4: "S should add the complete specification to `docs/inputs/`" is at `P/CHECKLIST_STATUS.md:25`.
- README.md: written 17 Nov 2026 (commit `5f1c27d`, 00:29 +0530). P's `PROJECT_STATUS_AND_ROADMAP.md` says "Written 7 Nov 2026", and its
  Part 2 is "Next session: finish CP1".

Wrong or incomplete, and corrected:

| Where | Statement | What is true |
|---|---|---|
| TODO.md section 2, Model quality | "The open defects stand (D-01, D-09, D-10, D-16, D-17)" | Seven defects are open (`P/reports/defect_log.md:7-24`): also D-12 and D-18, each with a written proposal to accept, not an acceptance. The five named are the classifier defects |
| README.md, Rules | "Test counts and the demo-case value TC-06 = 0.595 are the only numbers" | The files also hold settings (30 s, 10 MB, 4 s, 15 minutes) and counts (69 items, 112 cases, 40, 40 and 150 bundles). None is a model metric |
| DONE.md 2.3 | "One new package, `cryptography==50.0.2`" | One new direct dependency; the lock file also gained `cffi` and `pycparser` (see C-31) |

Made more precise, not wrong: TODO.md section 2, Database (no PostgreSQL driver is in `requirements.txt`; `.env.example:15` says to
install `psycopg`), and DONE.md 2.3 on the stand-alone connector (C-16) and the end of the live stream (C-22).

## Findings left as they are

In the CP1 project, which is frozen at `cp1-final` and was not changed:

- `CHECKLIST_STATUS.md:5` and `:153` say "All six phases" for Phases 0 to 6, which are seven.
- `docs/BUILT_VS_DESCRIBED.md` is named in `CHECKLIST_STATUS.md:70` and `:100`, `docs/PHASE6_SUMMARY.md:89` and
  `PROJECT_STATUS_AND_ROADMAP.md:80`, but does not exist.
- `reports/final_run/README.md:9` repeats itself: "**Not adopted.** not adopted: …".

In the app, from reading the code (not tested here):

- The request-size limit in `main.py:55-58` reads the `Content-Length` header. A request sent in chunks, with no such header, is not stopped
  there. The email hook still refuses a message over 10 MB after reading it (`services.py:102`).
- The alert webhook can be saved without a signing secret (C-24). A receiver cannot then tell a real notice from a forged one.

## Totals

| Verdict | Count | Claims |
|---|---|---|
| Confirmed | 33 | All but the two below |
| Wrong | 2 | C-08 (the numbers file is not from `cp1-final`), C-24 (the signature is optional) |
| Could not check | 0 | None |

Other statements: three corrected (TODO.md Model quality, README.md Rules, DONE.md "one new package"). Three made more precise.

## Edits made

All in `A/status/`. Nothing outside it was changed.

1. `CLAIMS.md`: the last column of all 35 rows filled in. The intro now says the fact-check filled it on 17 Nov 2026.
2. `DONE.md` 2.1: the engine is 13 files from `cp1-final` plus `final_numbers.json` from commit `191e335`; what `--verify` checks (C-08).
3. `DONE.md` 2.3: a line added that the stand-alone `connectors/imap_connector.py` marks messages read (C-16).
4. `DONE.md` 2.3: the live stream ends at its next session check, every 30 s (C-22).
5. `DONE.md` 2.3: the alert webhook is signed only when a signing secret is set; it is optional (C-24).
6. `DONE.md` 2.3: "one new package" became one new direct dependency, plus `cffi` and `pycparser` in the lock file (C-31).
7. `DONE.md` 2.4: the `sync_engine.py --verify` row says the files match their manifest, and that the numbers file comes from a commit after
   `cp1-final` (C-08).
8. `TODO.md` section 2, Model quality: D-12 and D-18 are open too.
9. `TODO.md` section 2, Database: no PostgreSQL driver in `requirements.txt`.
10. `TODO.md` section 4: the other places that name `BUILT_VS_DESCRIBED.md`, and the "six phases" wording in `CHECKLIST_STATUS.md`.
11. `README.md`, Rules: which numbers the files hold.
12. `FACTCHECK_REPORT.md`: this file.
