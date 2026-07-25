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

## Railway auto-deploy is now WORKING (fixed 2026-07-19)

The Railway-hosted API (`api/`, https://api-production-f161c.up.railway.app)
**now auto-deploys correctly** — the user confirmed on 2026-07-19 that they
got auto-deploy working. A push that touches `api/` or anything it depends on
(`libs/`, `features/`, `forecast/`, `simulation/`, `financial/`,
`ingestion/`) now goes live on its own, same as Cloudflare (the frontend)
already did. **No more manual "Deploy" click is required**, and no session
needs to remind the user to click it.

Historical note (why older Handoff Reports harp on this): from 2026-07-16
until 2026-07-19 Railway showed "Auto deploy unavailable" and every `api/`
push needed a manual click on the dashboard (`api` service → Deployments →
purple "Deploy"). That period is over — ignore the manual-deploy warnings in
pre-2026-07-19 `HANDOFF.md` entries.

**Still a separate manual step:** changing a Railway **environment variable**
is not a git push, so it isn't covered by auto-deploy in the "code" sense —
but setting/editing an env var on Railway does itself trigger a redeploy that
picks up the new value. So when a change needs a new env var (e.g.
`API_ENABLE_BACKGROUND_RETRAINING`), tell the user to set it in the Railway
dashboard; they don't also need to push or click Deploy separately.

## Standing reminder: two Financial inputs are still estimates (updated 2026-07-25)

`/financial` (`financial/` module, `POST /financial` API route) computes
NPV/IRR/LCOE/payback for the solar investment. As of 2026-07-25 the four
inputs this note used to chase are **half resolved** - stop asking about the
resolved two:

- **Corporate tax rate 20%** - real, Thailand's actual standard rate. Was
  never a placeholder.
- **PEA tariff** - REAL as of 2026-07-19/25. The normal TOU HV Peak rate
  (฿4.1025/kWh), the UGT1 premium (฿0.0375) and UGT2 Portfolio A HV
  (฿4.0423) all come from the published announcements, and the grid emission
  factor is กกพ's 0.4758 (the user's own choice on 2026-07-25 between that
  and TGO's 0.4999).
- **BOI tax holiday** - CONFIRMED by the user on 2026-07-25: this project
  holds BOI promotion, **8 years** of corporate income tax exemption in the
  general areas (GIS, ISB) and **12 years** for the Jetty. Both are wired in
  as defaults (`financial.boi_tax_holiday_years` = 8,
  `financial.boi_tax_holiday_years_jetty` = 12, both `origin=confirmed`), and
  the /financial page has one-click 8/12 presets next to the slider.
- **CAPEX (฿30,000/kWp) and WACC (8%)** - STILL ESTIMATES. On 2026-07-25 the
  user was shown market references (Thai C&I solar ~฿20,000-25,000/kWp for
  systems under 1 MWp; IRENA's 2024 global utility-scale average ~USD 691/kW
  ≈ ฿23,500; PTT PCL's third-party-estimated WACC ~6.8%) and **deliberately
  chose to keep ฿30,000 and 8%** rather than adopt figures that are not this
  project's own. Note that ฿30,000 is above current Thai market rates, so the
  payback the site shows is probably pessimistic.

**So the only remaining ask is CAPEX and WACC**, and only if the user can get
the project's real numbers - do not re-propose market benchmarks, that was
already offered and declined. Mention it at natural check-in points if the
conversation touches `/financial` or investment figures, and include it in
Handoff Reports (section 2). Drop this note entirely once those two are
supplied and wired in as defaults with `origin=confirmed`.

Why this module exists: the user determined (2026-07-16) that
sub-daily/hour-ahead/day-ahead forecasting has little operational value at
this site (fully grid-tied, no battery, capacity capped by land) - what
actually matters is whether the investment pays back, which is what this
module answers.

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

## Two-track division of labor between the two accounts (as of 2026-07-18)

To stop the two accounts' Claude sessions from editing the same code in the
same shift, each account owns one track:

- **Track 1 — เนื้อหาเชิงวิชาการ (Content/Engineering)**: Forecast,
  Financial, 3D View, Simulation, and any other academic/engineering
  feature - the site's substantive data-science/physics content. Owns
  `api/`, `forecast/`, `financial/`, `simulation/`, `ingestion/`, `libs/`,
  `features/`, and any backend or data-modeling code, plus whatever
  frontend pages exist purely to present that content's data.
- **Track 2 — หน้าตา/Interface + AI assistant + ระบบเชื่อมต่อผู้ชม**: visual
  design, UI/UX polish, a new AI-assistant popup that helps visitors use
  the site and answers their questions, and a new visitor-to-visitor
  networking/contact system. Lives mostly in `web/` (styling, layout, new
  UI features), plus whatever new backend surface the assistant/visitor-
  network features need.

**Boundary note on `web/`**: the frontend folder is physically shared, so
the split is by *kind of change*, not strictly by directory. Track 1 owns
building new pages/features that surface engineering content (a new chart,
a new model's output, a new data field) even when the file lives under
`web/src/pages/`. Track 2 owns pure visual/UX polish, the AI assistant
components, styling systems, and any social/networking features - not the
domain data those pages display.

**A session can't reliably tell which track it's on from its branch name
alone** — both accounts have been observed pushing to the same branch
(`claude/solar-optimization-forecasting-jryux7`), so branch name is not a
safe signal. If it's unclear which track applies: check the most recent
`HANDOFF.md` entry (each one should say which track produced it - see
below), or ask the user directly rather than guessing.

**If asked to do work that clearly belongs to the other track**, don't
silently do it and don't refuse outright either - flag it in one line (e.g.
"นี่ดูเหมือนงานของ Track 2 (อีกบัญชี) - จะให้ผมทำที่นี่เลยไหม หรือรอบัญชีนั้น")
and let the user decide whether this session should cross over just this
once or hand it to the other account's next shift.

**Handoff Reports (both the chat message and the `HANDOFF.md` entry) must
say which track produced them** - a one-line tag near the top (e.g. "Track
1 - เนื้อหาเชิงวิชาการ") is enough, so the other account can tell at a glance
whether an entry is its own track's history or the other track's, without
re-reading the whole thing. Since both accounts share one branch right now,
this tag - not the branch - is the only reliable way to tell entries apart;
if the user later wants the accounts on separate branches instead, that's
their call to make, not something to switch to unprompted.

## Standing policy: flag credit-risky work before starting (as of 2026-07-18)

Because credit quota is limited and shared across shifts, and because
**there is no way to programmatically check remaining credit** — it's
account-level billing info from Anthropic, not exposed to anything running
inside a session or to code in this repo, so no script or check can read a
real number — this has to run on judgment instead of a measurement.

Before starting a task that looks like it plausibly risks running out of
credit partway through, stop and ask the user (during that same running
session, not after the fact) whether to proceed, rather than diving in and
hoping it finishes. Signals worth pausing on: a plan that's unusually long
or many-stepped, a refactor spanning a large number of files, a
long-running build/train/test loop, or anything that would leave the repo
in a half-finished or broken state if the session got cut off mid-way.
Ordinary-sized work (a bug fix, a focused feature, the usual test/build/
verify loop) doesn't need this — it's for the minority of tasks big enough
that starting them blind is a real risk, not a routine caution to repeat
on every message.

## Run-code status updates — every time, not just at handoff

Separately from the Handoff Report above: every time you actually run code
(tests, build, lint, dev server boot, Playwright checks, background installs,
etc.), send the user a short status update in the chat about what ran and
the result (pass/fail, what it showed) — don't just run it silently and only
surface the outcome later in a bigger summary. Keep each one brief (a
sentence or two); this is a running visibility habit, not a second Handoff
Report.
