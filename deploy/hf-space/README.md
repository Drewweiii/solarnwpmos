---
title: Nong Fab Solar Forecasting API
emoji: ☀️
colorFrom: yellow
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Nong Fab Solar Forecasting — API

Backend for the PTT LNG Terminal 2 (Nong Fab) solar forecasting site. FastAPI,
served on port 7860.

The website itself is hosted separately on Cloudflare Pages; this Space serves
only its data (forecasts, simulation, financial analysis, savings/carbon, grid
context, and the visitor chat WebSocket).

## What runs here

- Solar position and clear-sky irradiance computed with `pvlib` at the site's
  real coordinates (12.71 N, 101.15 E)
- Weather inputs read from public sources (NOAA GFS, Himawari, NASA POWER)
- Thai grid context from EGAT's public system-generation feed
- Tariff and emission figures from the published PEA / ERC announcements

Nothing here is measured by an on-site sensor — the site has no weather station
or SCADA meter, and every figure the API returns is labelled accordingly.

## Notes for whoever redeploys this

- **Disk is not persistent.** A restart clears anything written. The app is
  built for that: the real-data store defaults to in-memory and the auth
  tables are recreated on startup.
- **The Space sleeps after 48 hours with no traffic.** The first visitor after
  that waits for a cold start.
- **Secrets are set in the Space's own Settings tab**, not in this repo. See
  `deploy/hf-space/SETUP.md` in the source repository for the list.
- The image is built from `deploy/hf-space/Dockerfile` in the source repo and
  copied to this repo's root by `deploy/hf-space/push.sh` — edit it there, not
  here, or the next sync will overwrite your change.
