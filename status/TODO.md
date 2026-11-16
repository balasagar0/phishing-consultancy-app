# What is left

Four parts: what must happen before a client relies on the app; the 7 Nov roadmap, area by area; the CP1 tasks for people; and fixes to
documents found while writing this. Where only a person can do a step, the line says who.

## 1. Before any client relies on the app

In this order. Rule 8 of the CP1 brief comes first: nothing is hosted, uploaded or shown to a client until the patent is filed.

| # | Step | Who | Why |
|---|---|---|---|
| 1 | File the patent (PT-01 to PT-09) | Bala, with KL IPFC | Until then the app must not be hosted where others can reach it, or pushed anywhere |
| 2 | Run each connector against a real mailbox with **Test connection**, then for a day: a Gmail or Workspace mailbox with an app password, and a Microsoft 365 mailbox with an app registration | The owner, who types the passwords and secrets into the app | They were tested only against stand-ins (C-20) |
| 3 | Build and run the Docker image and the compose file on a server, with HTTPS | Whoever runs the server | Never built (C-28) |
| 4 | Load test: a burst of mail, many open live pages, several connectors | Developer | Not done; everything runs in one process |
| 5 | Penetration test and a short threat model | An outside tester, or the team with a checklist | Not done |
| 6 | Restore drill: back up the data folder and the master key, restore on another machine, check that connectors still sign in | Whoever runs the server | Not done; losing the master key means re-entering every connector secret |
| 7 | A data processing agreement template and a written policy for watching inboxes (India's DPDP Act, 2023) | The team, with legal advice | The one-pager promises a written agreement first |
| 8 | Measure false alarms and misses on the client's own traffic during the pilot | The team and the client's analysts | Every model figure comes from public datasets; the correlation figures are simulated |

## 2. The 7 Nov roadmap, area by area

From Part 3 of `project/PROJECT_STATUS_AND_ROADMAP.md`. "Built" means code and a passing test exist.

| Area | Where it stands now | Left to do |
|---|---|---|
| Real evaluation data | Not done. No real bundle exists | The team collects 40 coordinated and 40 benign bundles, 150 to refit (R2-10) |
| Model quality | Not done. The open classifier defects stand (D-01, D-09, D-10, D-16, D-17). D-12 and D-18 are open too, each with a written proposal to accept, not an acceptance | Retrain with real phishing email and real legitimate SMS (CP2) |
| Calibrated risk | Not built | Needs real bundles first |
| Live message sources | **Built for email and SMS.** IMAP (IDLE or polling), Microsoft 365 (Graph, polling), SMS and email webhooks; links in mail and SMS become URL events | Run against real mailboxes (section 1, step 2). Not built: the Gmail API, Graph push notifications (they need a public HTTPS address), a browser extension for links, an Android reader app. Time from arrival to alert was measured only against a stand-in |
| Background processing | Not built. Connectors are threads in the server process; requests are scored while they wait | A queue and workers, then a load test |
| Database | Partly. SQLAlchemy, SQLite in WAL mode; a PostgreSQL address can be configured, but no PostgreSQL driver is in `requirements.txt` (`.env.example` says to install `psycopg`) | Test on PostgreSQL; add migrations (the app adds new tables, but cannot yet change existing ones); a restore drill |
| Client separation | **Built.** Separate event store and HMAC key per organisation, derived from one master key; a test shows no data crosses | Keep the master key in a secrets manager; a key rotation drill |
| Sign-in and roles | **Built** with passwords, roles and API keys | Single sign-on (OAuth2 or SAML) if a client asks for it |
| Alert workflow | **Built.** Triage states, assignment, notes, audit log, on-screen pop-ups, desktop notifications, alert webhook | Email notifications are not built. Microsoft Teams was not tested |
| Learning from feedback | Not built | Analyst verdicts as labels, with consent, under the adoption rule |
| Monitoring | Partly. `/api/health`, connector states, the alert webhook's last result | Metrics and dashboards for the operator, with no message content |
| Packaging | Partly. Setup and start scripts run on this laptop; Docker files written but never run | Section 1, step 3 |
| Quality gate | Not built. Tests are run by hand | CI on every commit, once there is somewhere to run it after the patent is filed |
| Security review | Partly. Input checks, CSP, CSRF, lockout, encrypted secrets, private-address refusal, no redirects | Section 1, step 5; dependency and container scanning |
| Privacy and compliance | Partly. Hashing, no text stored by default, a scheduled purge, a written client one-pager | Requests from a person to see or delete their data; a breach procedure; the agreement in section 1, step 7 |
| Data licences | Not done | Confirm or replace the datasets with no stated licence (`project/DATA_SOURCES.md`) before any paid use |
| Voice and video | Not built | Only with usable data and a measured error rate (`project/docs/CP2_BACKLOG.md`) |
| Client documentation | **Built.** `README.md`, `docs/OPERATIONS.md`, `docs/CLIENT_ONE_PAGER.md` | An analyst guide and an onboarding checklist |

Smaller things in the app:

- Removing a client completely is done by hand (`docs/OPERATIONS.md`); a script is not built.
- A Microsoft 365 client secret expires; the app does not warn before that date.
- The demo replay sends messages seconds apart, so its campaign risks differ from the demo-case table (TC-06 does not come out at 0.595
  there). Use **Investigate** for the reference values (C-33).
- The browser console shows React Router warnings about version 7; pytest shows two deprecation warnings (httpx in the test client, and
  `registered_domain` in the pinned engine). None is an error. The engine must not be edited to silence its warning.

## 3. CP1: tasks for people and the owner's decisions

The full list, by owner, is `project/docs/PHASE6_SUMMARY.md`, sections 3 and 4. The decisions waiting on the owner:

1. Which open defects to accept in writing. Three are High and block exit criterion 7. Accepting one is the team's call.
2. Voice scope: keep `no`, or switch to `yes` and follow the brief's Appendix A.
3. Whether to file the patent before or after real bundles test the correlation claim.
4. Keep or delete the v3 email model and the mail export, together.
5. Which laptop is the demo laptop; then Viraj runs the preflight, the benchmark and one run with Wi-Fi off.
6. Who collects the real bundles, from whose accounts, with what written consent.

## 4. Document fixes found while writing this

These are in the frozen CP1 project. Each needs the owner's go-ahead, because changing the project after `cp1-final` changes its history.

- `CHECKLIST_STATUS.md`, row R3-01, points to `docs/BUILT_VS_DESCRIBED.md`. That file does not exist: the 7 Nov decision replaced it with
  `docs/PATENT_BASIS.md` (C-06). `docs/PHASE6_SUMMARY.md` repeats the pointer, because it is generated from the checklist. The name also
  appears in row PT-04's third column ("Inputs: BUILT_VS_DESCRIBED", copied from the brief) and in `PROJECT_STATUS_AND_ROADMAP.md`, line 80.
- `CHECKLIST_STATUS.md` says "All six phases done" (line 5 and the closing summary), but its phase table lists seven, Phase 0 to Phase 6,
  all done.
- `CHECKLIST_STATUS.md`, "Things found in Phase 0", item 1, says the patent specification is no longer needed, then ends "S should add the
  complete specification to `docs/inputs/`". The last sentence predates the decision.
- `PROJECT_STATUS_AND_ROADMAP.md` (7 Nov) is out of date (see `README.md` in this folder). Replace it with a pointer to this folder, or update it.
