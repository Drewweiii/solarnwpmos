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

## Run-code status updates — every time, not just at handoff

Separately from the Handoff Report above: every time you actually run code
(tests, build, lint, dev server boot, Playwright checks, background installs,
etc.), send the user a short status update in the chat about what ran and
the result (pass/fail, what it showed) — don't just run it silently and only
surface the outcome later in a bigger summary. Keep each one brief (a
sentence or two); this is a running visibility habit, not a second Handoff
Report.
