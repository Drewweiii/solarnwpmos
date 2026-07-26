# IBM Plex Sans Thai — self-hosted (2026-07-26, project P)

Eight `.woff2` files: weights 400 / 500 / 600 / 700, each split into the `thai`
and `latin` unicode subsets. 118 KB total, and a page only downloads the subsets
its own text actually needs.

**Why self-hosted and not a CDN link.** This project loads nothing from a third
party at runtime. A `<link>` to fonts.googleapis.com would make every page view
a request to Google, would break entirely behind a corporate firewall (this site
is shown inside a PTT facility), and would put a render-blocking dependency on a
host nobody here controls. The files are 118 KB — cheaper than the problem.

**Why this typeface.** It carries Thai and Latin in one family with matching
metrics, which is the actual defect it fixes: the site used to be `system-ui`
alone, so Thai rendered in whatever the OS happened to have (Leelawadee UI on
Windows, Thonburi on macOS, something else on Android) while Latin rendered in
the system sans — two unrelated designs on the same line, different on every
visitor's machine. The Thai was drawn by Cadson Demak, a Bangkok foundry.

**Subsets kept.** `thai` and `latin` only. Google also serves `cyrillic-ext` and
`latin-ext`; nothing on this site uses them, so they are not shipped.

**License.** SIL Open Font License 1.1 — see `OFL.txt` in this directory, which
is the licence's own requirement for redistribution. Copyright © 2017 IBM Corp.
with Reserved Font Name "Plex".

**Where they are wired up.** `src/index.css` (the `@font-face` block and the
`--sans` / `--heading` tokens) and `index.html` (two `<link rel="preload">`).
