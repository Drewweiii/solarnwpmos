# Working agreement: multi-account handoff

The user runs this project across two separate Claude Code accounts, switching
between them in shifts to manage limited credit quota. Each switch is a fresh
session with no shared memory, so continuity depends entirely on what gets
written down.

## Handoff Report — when to produce one

Produce a "Handoff Report" (in Thai, matching the user's language) whenever:
- A work session is ending, OR
- The user types the exact phrase "สรุปงานเพื่อส่งไม้ต่อ", OR
- The user types "เปลี่ยนแอค" (or a clear equivalent stating they're switching
  to the other account) — see the sub-section immediately below for the
  extra acknowledgment line this trigger requires.

The user copies this report and pastes it to the other account's Claude
session to resume work without re-explaining context. Keep it concise enough
for a capable model (Sonnet-tier) to pick up immediately — no need for
exhaustive prose, just enough to not have to ask again.

### Also commit it to `HANDOFF.md` (as of 2026-07-17)

Every time a Handoff Report is produced (any trigger above), also **append**
it to `HANDOFF.md` at the repo root — do not overwrite or prune earlier
entries, this file is a running append-only log, oldest entry first, newest
appended at the bottom. Prepend each entry with a `## <ISO date/time>` header
so entries are easy to tell apart when scrolling. Commit and push this
change together with (or immediately after) whatever other work is being
committed in the same turn — the whole point is that the other account can
open this file directly on GitHub and see the latest state without needing
the report pasted into chat first.

### On the "เปลี่ยนแอค" trigger specifically

Because this phrase signals a live account switch (not just an end-of-session
wrap-up), lead with a one-line acknowledgment that the switch was registered
— e.g. "รับทราบ — สลับบัญชีแล้ว กำลังส่งสรุปงานให้" — immediately followed by
the full 3-section Handoff Report below. Produce this every single time the
phrase is typed, not just once per session — if the user switches accounts
multiple times in one thread, send a fresh report each time reflecting
whatever changed since the last one.

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

## Standing policy: Thailand-first for time, weather, and other regional data (as of 2026-07-17)

Whenever code in this project pulls, computes, defaults, or displays
data that is regionally scoped — timezone/clock time, weather/climate
data, location-based reference datasets, or any other "which country's
convention applies here" choice — **Thailand must be the default, always,
with no exception silently substituted**:
- Time: Asia/Bangkok (ICT, UTC+7) is the default display timezone
  everywhere in the product (dashboards, reports, logs meant for the
  user). This is what the 2026-07-17 UTC-to-ICT fixes across Forecast,
  Simulation, 3D View, and Irradiance Map already established — see
  `nongfab-ems/web/README.md`'s matching dated entry for the fuller
  breakdown of which pages needed a pure-display conversion vs. a
  UTC-semantic value with an ICT-converted readout.
- Weather/climate/irradiance and any other geographically-scoped
  dataset: default to Thailand-sited or Thailand-appropriate sources
  (e.g. the Thai Meteorological Department, or reanalysis/satellite
  products queried at Nong Fab's own real Thailand coordinates) — not a
  generic/global default that happens to point elsewhere.

**If a task would require sourcing or defaulting to another country's
data** (a different country's weather service, a non-Thailand reference
dataset, a library default that assumes a different locale/timezone,
etc.), **stop and ask the user for explicit approval before proceeding**
— do not silently substitute it and mention it only after the fact. State
plainly what the non-Thailand source would be and why it seemed necessary,
and let the user decide.

## Run-code status updates — every time, not just at handoff

Separately from the Handoff Report above: every time you actually run code
(tests, build, lint, dev server boot, Playwright checks, background installs,
etc.), send the user a short status update in the chat about what ran and
the result (pass/fail, what it showed) — don't just run it silently and only
surface the outcome later in a bigger summary. Keep each one brief (a
sentence or two); this is a running visibility habit, not a second Handoff
Report.
