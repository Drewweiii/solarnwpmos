# Working agreement: multi-account handoff

The user runs this project across two separate Claude Code accounts, switching
between them in shifts to manage limited credit quota. Each switch is a fresh
session with no shared memory, so continuity depends entirely on what gets
written down.

## Handoff Report — when to produce one

Produce a "Handoff Report" (in Thai, matching the user's language) whenever:
- A work session is ending, OR
- The user types the exact phrase "สรุปงานเพื่อส่งไม้ต่อ"

The user copies this report and pastes it to the other account's Claude
session to resume work without re-explaining context. Keep it concise enough
for a capable model (Sonnet-tier) to pick up immediately — no need for
exhaustive prose, just enough to not have to ask again.

## Required structure (3 sections)

1. **สิ่งที่ทำเสร็จแล้ว (Completed Tasks)** — what was just accomplished this
   session: code changed (files/functions), content written, bugs fixed.
2. **บริบทและสถานะปัจจุบัน (Current Context & State)** — what the next session
   needs to know to continue without friction: tone/style conventions, key
   variable/file names, current file structure, rules just agreed on with the
   user, and exactly where things were left off.
3. **เป้าหมายและงานต่อไป (Next Steps for the Next Session)** — a numbered,
   unambiguous list of what to do first when the next session opens, so the
   incoming Claude can start immediately without asking redundant questions.

## Standing reminder: Railway does not auto-deploy (as of 2026-07-16)

The Railway-hosted API (`api/`, https://api-production-f161c.up.railway.app)
has no working auto-deploy — a GitHub source is connected and correctly
configured, but Railway itself shows "Auto deploy unavailable" and
troubleshooting with Railway's own documented steps didn't fix it (full
details in `nongfab-ems/README.md`'s "Deployment notes"). Every push that
touches `api/` or anything it depends on (`libs/`, `features/`, `forecast/`,
`simulation/`, `financial/`, `ingestion/`) needs a **manual click** on Railway's dashboard
(`api` service → Deployments tab → purple "Deploy" button) to actually go
live. Cloudflare (the frontend) still auto-deploys fine — this only affects
the API.

**Always include this reminder** in two places:
1. Every Handoff Report (put it in section 3, Next Steps), if this session
   touched `api/`-side code and the user hasn't confirmed they already
   clicked Deploy on Railway for it.
2. At the end of any session where you changed `api/`-side code, even
   outside a formal Handoff Report — a one-line reminder before the session
   ends, same spirit as the run-code status updates below.

Stop adding this reminder once the user confirms Railway's auto-deploy has
been fixed (e.g. by Railway support) — update this note then, don't keep
repeating a stale warning.

## Standing reminder: the Financial module runs on placeholder assumptions (as of 2026-07-16)

`/financial` (`financial/` module, `POST /financial` API route) computes
NPV/IRR/LCOE/payback for the solar investment, but **every cost/tariff/rate
input defaults to a documented placeholder, not a real figure for this
project** (see `financial/README.md`'s table): CAPEX (฿30,000/kWp
estimate), the PEA electricity tariff (฿4.0/kWh blended guess), WACC (8%),
BOI tax-holiday length (assumed 0 = none). Only the 20% corporate tax rate
is a real fact (Thailand's actual standard rate), not a placeholder.

This module exists because the user determined (2026-07-16) that
sub-daily/hour-ahead/day-ahead forecasting has little operational value at
this site (fully grid-tied, no battery, capacity capped by land) - what
actually matters is whether the investment pays back, which is what this
module answers, once given real numbers.

**Always include this reminder** in Handoff Reports (section 2, Current
Context & State) and at natural check-in points if the conversation touches
`/financial` or investment figures: ask the user whether they can now
supply the real CAPEX, PEA tariff/contract, WACC, and BOI status, so the
placeholder defaults in `financial/src/nongfab_financial/model.py` can be
replaced with confirmed figures. Stop reminding once the user has supplied
all four and they've been wired in as the new defaults - update this note
then.

## Run-code status updates — every time, not just at handoff

Separately from the Handoff Report above: every time you actually run code
(tests, build, lint, dev server boot, Playwright checks, background installs,
etc.), send the user a short status update in the chat about what ran and
the result (pass/fail, what it showed) — don't just run it silently and only
surface the outcome later in a bigger summary. Keep each one brief (a
sentence or two); this is a running visibility habit, not a second Handoff
Report.
