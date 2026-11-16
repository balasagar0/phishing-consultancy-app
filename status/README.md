# Status: what was done, what is left, and the claims to check

Written 17 Nov 2026, at the end of the work on CP1 and on the consultancy app. It covers two folders:

| Folder | What it is | Git |
|---|---|---|
| `D:\Capstone_HTE Project\prototype\project` | The CP1 project. Frozen at tag `cp1-final`. | Its own repository, no remote |
| `D:\Capstone_HTE Project\prototype\app` | The website and web app for consultancy pilots, with a pinned copy of the `cp1-final` engine. | Its own repository, no remote |

## The files

| File | What it holds |
|---|---|
| [DONE.md](DONE.md) | What was done, with the commit, the file or the test that shows it |
| [TODO.md](TODO.md) | What is left: before a client relies on the app, the 7 Nov roadmap area by area, the CP1 tasks for people, and document fixes |
| [CLAIMS.md](CLAIMS.md) | Every claim in DONE.md and TODO.md that can be checked, with the way to check it. A separate session fact-checks it |
| `FACTCHECK_REPORT.md` | Written by the fact-check session: a verdict for every claim and every correction it made |

## Rules for these files

- No model metric is typed here. Every figure lives in the CP1 project's `reports/` (start with `reports/FINAL_NUMBERS.md`; where it and
  `reports/results.md` disagree, `results.md` wins). These files say where a figure is, not what it is. Test counts and the demo-case value
  TC-06 = 0.595 are the only numbers, and CLAIMS.md says how to check each one.
- "Not built" means not built. "Tested" says against what: several app features were tested only against stand-ins on this laptop.
- The documents listed as wrong in the project's `CLAUDE.md` (the study guide, the old numbers register, the Review-2 and Review-3 packs,
  the old manuscript and training report) were not used.

## Superseded

`project/PROJECT_STATUS_AND_ROADMAP.md` (7 Nov 2026) is out of date. Its Part 2 ("next session: finish CP1") is done, and the app has built part
of its Part 3. TODO.md section 2 says, area by area, where each part of that roadmap stands now. The file itself was left as it is, because the
project is frozen; replacing it is listed in TODO.md section 4.
