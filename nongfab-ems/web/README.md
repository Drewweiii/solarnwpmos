# Module 7 — Dashboard

React + TypeScript + Vite dashboard for the Backend API (Module 6). STEP 8
(Feature A, "CU Solar Forecast" style) is built: a zone selector
(GIS/ISB/Jetty/รวม-All), Day-ahead/Intra-day toggle, a Recharts combo chart
(generated-power bars + forecast line + prediction-interval band), a weather
strip (temp + icon at 06/09/12/15), and KPI cards (capacity, daily
cumulative energy, current power, solar plant factor).

STEP 8B (Feature B+C, Aurora/SolarTH-style 3D view) is also built, at `/3d`:
a real Three.js scene (`@react-three/fiber`) showing each zone's panel grid
colored by solar-access % (or by string, toggle-able), a compass/altitude
readout, a sun-path arc line, and a date + time scrubber (with auto-play)
that drives both the sun position and every panel's shading live. Still to
come (STEP 8C, not started): Energy Report + interactive SLD viewer,
MapLibre irradiance map.

## Auth

The API requires a JWT bearer token on every route, so this app gates
everything behind a login screen (`POST /auth/token`, OAuth2 password flow -
same demo accounts as `api/README.md`'s "Auth" section: `admin`/
`admin-demo-pw`, `operator`/`operator-demo-pw`, `viewer`/`viewer-demo-pw`).
The token is decoded client-side only for display (username/role) - the
backend re-validates the signature on every request regardless, so nothing
here is a security boundary by itself.

## Data model notes

- **"All" (รวม) zone**: the backend has no single aggregate endpoint, so
  this view fires one `/performance` + `/forecast` call per real zone in
  parallel and sums them client-side (`lib/queries.ts`, `lib/chartData.ts`).
  Power sums across zones; irradiance/temperature average (they're
  intensities, not extensive quantities) - see `chartData.ts`'s doc comments.
- **Day-ahead vs Intra-day**: maps to the backend's `day` vs `hour` forecast
  horizons. Intra-day's `hour` horizon is genuinely a single next-hour
  point (not a multi-point series - see Module 4's `hour_ahead` model), so
  it renders as one marker rather than a full line.
- **Weather strip icons**: derived from modeled irradiance (`ssrd_w_m2`,
  already computed server-side), not a separate weather feed - no new
  external data source, so the standing "confirm before deciding on
  external-source credentials/ToS" rule doesn't apply here.
- `/performance/{zone}`'s `hourly` field (added in this step, not in Module
  6's original shape) exposes today's synthetic baseline hour-by-hour so
  this chart has a real "generated power" series to plot - see
  `api/src/nongfab_api/routes_performance.py`.
- **3D scene axis convention** (`lib/solar3d.ts`, `components/Solar3DScene.tsx`):
  east maps to Three.js's +X, north to -Z, up to +Y. The backend
  (`nongfab_features.panel_geometry`) already applies each zone's azimuth
  rotation when computing panel positions, so `Solar3DScene` only needs to
  apply azimuth/tilt to each panel *mesh's own orientation*, not re-derive
  positions - see that file's header comment.
- **Solar-access color, not real-time WebGL shadows**: each panel's color
  comes from the backend's analytical row-shading calculation
  (`nongfab_features.shading`), which is the actual source of truth: Three.js
  shadow-mapping isn't used to compute shading, only a directional light for
  visual depth. This is deliberate - the panels are simplified box meshes,
  and a real-time shadow map from them would be *less* accurate than the
  purpose-built geometric model already backing the color.

## Known gaps

Same "no real accumulated history yet" caveat as every backend module: all
data here comes from the backend's synthetic-baseline/synthetic-forecast dev
behavior, not live sensor history. `/forecast` 404s until a model has been
trained via Module 4's dev API (`POST /train-now/{zone}/{horizon}`) - the
page shows a plain status message rather than fabricating a forecast line.

- The 3D view models inter-row self-shading only - no obstacle survey
  (trees/structures) exists yet (see `features/README.md`'s own "Known
  gaps"), so a panel can never show less than 100% access purely from an
  external obstruction, only from another row of panels.
- `String view` colors each sub-array/block with a hash-derived color for
  visual distinction, not a designed palette - can land on a dark, low-
  contrast color against the night scene's dark background (a cosmetic gap,
  not a data-correctness one).
- The production bundle is ~1.6MB (~450KB gzipped) after adding Three.js -
  no code-splitting yet. Deferred until Feature D/E (MapLibre) also lands,
  since a single code-splitting pass across all the heavy per-page
  dependencies (Three.js, Recharts, MapLibre) makes more sense than three
  separate passes.

## Verified live (2026-07-14)

Ran a real `uvicorn` (Module 6) + `vite dev` pair and drove the page with a
real headless Chromium (Playwright), logged in as `admin`, and confirmed:
KPI cards match the backend's real `/assets` + `/performance` numbers for
both a single zone and the "All" aggregate; the weather strip renders
correct icons/temps at all 4 hours; the Day-ahead/Intra-day toggle
re-fetches with the right horizon; a zone/horizon with no trained model
shows the "no model trained yet" message instead of crashing; light and
dark mode both render correctly.

**Found and fixed a real bug**: the backend had no CORS policy at all, so
the browser blocked every dashboard request outright ("blocked by CORS
policy" - not a 401, the request never reached FastAPI). Added
`CORSMiddleware` + an `API_CORS_ORIGINS` setting in `api/`. The first fix
attempt was itself broken - the settings field was named `cors_origins_raw`
which pydantic-settings maps to env var `API_CORS_ORIGINS_RAW`, not the
documented `API_CORS_ORIGINS`, so overriding it via env var silently did
nothing (curl against the live server proved this: the header value never
changed no matter what `API_CORS_ORIGINS` was set to). Renamed the field so
the env var name actually matches the docs, and added
`api/tests/test_config.py`, which builds `Settings()` through real env-var
parsing rather than direct keyword arguments specifically so this class of
bug can't silently reappear.

### Verified live - STEP 8B, the 3D view (2026-07-14)

Ran the same real `uvicorn` + `vite dev` pair, but this time with headless
Chromium launched with `--use-gl=swiftshader` (software WebGL - jsdom can't
render it at all, so this was the only way to actually see the canvas
render). Confirmed: GIS/ISB/Jetty all render their real panel counts
(84/196/320), correctly colored green/red by solar access; the compass and
"avg solar access" readout update correctly moving the time scrubber from
night (0% access, negative altitude) to midday (100%, ~80° altitude); the
sun-path arc line renders and tracks the compass; `String view` colors
panels by sub-array; Jetty's `simulated_zone` badge appears only for Jetty.
No console/WebGL errors.

**Found and fixed a real bug**: the default 3D camera was framed on the
*whole layout's* bounding box. For GIS/ISB (one compact block) that's fine,
but Jetty's 4 real sub-arrays are spread across its ~1.25km trestle span -
framing the whole thing either shrank every panel to an invisible speck, or
(after a first fix attempt that capped the zoom distance) centered the
camera on the empty geometric middle of a symmetric 4-block spread, where
no sub-array actually sits. The screenshot showed a plain dark plane with no
panels visible at all. Fixed `Solar3DScene.tsx` to frame the default camera
on the *first block* specifically (still rendering every other block, still
reachable by scrolling out) - re-verified live that Jetty now shows real
panels by default.

## Run locally

```bash
npm install
npm run dev      # http://localhost:5173 - needs api/ running, see api/README.md
npm run test
npm run lint
npm run build
```

Point at a non-default API with `VITE_API_URL` (see root `.env.example`).

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
