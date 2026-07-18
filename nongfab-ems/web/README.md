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
that drives both the sun position and every panel's shading live.
**(2026-07-16)** panels now sit on a real building volume (GIS/ISB) or an
elevated pier deck (Jetty, matching its real trestle-over-water structure -
see `Solar3DScene.tsx`'s own `BUILDING_HEIGHT_M`/`PIER_DECK_HEIGHT_M`
docstrings for why these are documented literature defaults, not a survey -
`config/assets.yaml` has no real building-height data), on a dark
grid-line floor (`@react-three/drei`'s `<Grid>`) - the first step toward a
reslink.org-style "digital twin" look the user asked to be replicated (see
that commit's message for the fuller reference-video breakdown).

**(2026-07-16, same pass)** `/3d`'s page chrome was also restyled toward the
reslink.org reference, per the user's explicit choice to copy the card look
including its CTAs - but mapped onto real controls, not literal marketing
furniture:

- **`Solar3DIconRail.tsx`** - a dark vertical icon rail overlaid on the
  canvas' top-left corner (reslink's own toolbar placement), replacing the
  old horizontal "Solar access / String view" tab row and the separate
  Play/Pause button. The rail holds the controls this page actually has
  (view-mode toggle x2, play/pause, "reset camera view" -
  `Solar3DScene.tsx` now exposes a `resetCamera()` imperative handle via
  React 19's plain-prop `ref`, no `forwardRef` wrapper needed - plus a
  grid/satellite ground-style toggle added in the follow-up entry below).
  Hand-drawn
  inline SVG icons, same pattern as the existing `Compass.tsx` - no new
  icon-library dependency for 5 icons.
- **`SolarAccessGauge.tsx`** - the red-yellow-green gradient status bar from
  reslink's header, now next to the zone selector, driven by
  `average_solar_access_pct` (the same metric the old plain-text readout
  already showed - this is a visual treatment of existing data, not a new
  metric).
- Reslink's `DESKTOP`/`MOBILE` toggle and `Book a demo`/`Get 3D Access` CTA
  buttons were deliberately **not** replicated - the user's own call: those
  are marketing furniture for reslink's own embeddable-widget product, with
  no equivalent purpose inside this internal EMS dashboard.

**(2026-07-16, follow-up)** The "photorealistic satellite-textured render"
gap flagged above got a first real implementation, not just a punt to
later - the user's own call after a feasibility check found this
sandbox's egress policy blocks every map-tile provider outright
(`arcgisonline.com`, `mapbox.com`, `maptiler.com`,
`tile.openstreetmap.org` - all 403 at the CONNECT tunnel, same
restriction that blocked reslink.org itself and NASA POWER earlier in
this project) was to **write the code anyway without live verification**,
the same precedent as the NASA POWER UV ingestion module:

- **`lib/satelliteTile.ts`** - standard Web Mercator slippy-map tile math
  (`latLonToTile`, unit-tested) plus `esriWorldImageryTileUrl()`, which
  builds a single-tile URL against Esri World Imagery (chosen because it's
  **keyless** - no Mapbox/MapTiler-style API token needed - reachable at
  `server.arcgisonline.com` under Esri's free-tier ToS for this kind of
  low-volume display use). `DEFAULT_SATELLITE_ZOOM = 17` was chosen so one
  tile's real-world footprint (~300m at this latitude) comfortably covers
  GIS/ISB's own panel-array footprint - not pixel-perfect georeferencing,
  a single-tile visual approximation (Jetty's ~1.25km trestle span is
  still far bigger than one tile regardless of zoom, so its texture only
  covers the central portion of the layout - stitching multiple tiles is
  a further follow-up, not attempted here).
- **`Solar3DScene.tsx`'s new `SatelliteGroundPlane`** loads the tile via
  `THREE.TextureLoader`'s callback API (not drei's Suspense-based
  `useTexture`) specifically so a blocked/failed fetch degrades to
  "render nothing" - the existing dark ground plane and grid floor
  underneath stay exactly as they were, rather than throwing into a
  Suspense boundary this scene doesn't otherwise need. A new 5th icon-rail
  button (`groundStyle: 'grid' | 'satellite'`) toggles between the two;
  `Solar3DPage.tsx` computes the tile URL from the current zone's own real
  centroid (`config/assets.yaml` via `/assets`, not the plant's one shared
  nominal center `/geometry` uses for solar position).
- **Verified live** (headless Chromium, this sandbox): confirmed the
  fetch does fail exactly as expected
  (`net::ERR_TUNNEL_CONNECTION_FAILED`, one benign browser resource-load
  console error, no uncaught JS exception) and the scene degrades
  gracefully - grid hidden, dark ground plane still visible, panels/
  building still render, no blank/broken canvas. Confirmed the toggle
  button's `aria-pressed`/`aria-label`/active-class state all flip
  correctly across grid -> satellite -> grid. **The actual tile image has
  never been confirmed to load** - that only happens once this deploys
  somewhere with real egress to `arcgisonline.com`.

STEP 8C (Feature D+E) is also built:

- **`/energy-report`** - a per-zone Energy Report: system summary
  (capacity, module count, array area, inverter), annual generation
  (energy, specific yield, performance ratio - a flat extrapolation, see
  `simulation/README.md`), **(2026-07-16)** a monthly generation bar chart
  (Recharts, real pvlib-solar-position-based monthly variation with a
  rainy-season June-October legend - reslink.org used as the design
  reference, see `simulation/README.md`'s own section), a full loss
  breakdown including temperature (Jetty's soiling correctly higher than
  GIS/ISB's), a sun-exposure card (average real per-panel solar access at
  local solar noon), CO2 saved/trees equivalent, a 25-year lifecycle
  estimate (lifetime generation + year-25 output as a documented-degradation
  projection), and an interactive SLD viewer (`SLDViewer.tsx`) built from the
  zone's real equipment data (not a scanned image) - click any string or
  inverter node to see its specs.
- **`/irradiance-map`** - a MapLibre GL map (`IrradianceMapView.tsx`)
  showing all 3 zones' pins plus a plant-wide irradiance overlay (0-1000
  W/m^2, with a documented synthetic cloud factor - see `features/README.md`),
  a date + time scrubber (with auto-play, same pattern as `/3d`), and
  layer-toggle checkboxes for the irradiance overlay, zone pins, and zone
  boundary independently. Clicking a zone pin opens a popup with its
  lat/lon, installed capacity, estimated output, plant factor, estimated
  irradiance, and cloud factor.

Both pages, plus `/3d`, are now code-split (`React.lazy`) into their own
chunks fetched on navigation - see "Known gaps" below.

A recheck against the full Feature A-E spec (2026-07-15) found and closed 5
more gaps across the existing pages:

- **`/forecast`** now shows a per-zone info panel (latitude, longitude,
  installed capacity, estimated energy, plant factor, estimated irradiance,
  cloud factor) when a single real zone is selected - hidden for the "All"
  (รวม) aggregate, since lat/lon is inherently a single-point value.
- **`/3d`** now shows a "Forecast vs actual" readout tied to the sun-path
  scrub time (Feature C <-> Feature A integration - the nearest day-ahead
  forecast point and nearest actual/generated point to the scrubbed
  instant, not just a standalone 3D scene), and a string power-balance
  warning banner when `/geometry/{zone}`'s new `string_balance` reports a
  block exceeding its design constraint (Jetty only - see
  `features/README.md`).

STEP 9 (Module 5's Simulation Playground - everything else STEP 9 asked for
was already built in earlier steps, see `simulation/README.md`) adds
**`/simulation`**: a per-zone what-if playground built on the existing
`POST /simulate/{zone}` (no new backend route - `useSimulate()` in
`lib/queries.ts` is this app's first `useMutation`, not a `useQuery`, since
running a scenario is an explicit action, not a background fetch). Sliders
for the 4 what-if parameters (extra cloud attenuation, curtailment,
degradation, years since commissioning) plus 3 optional Monte Carlo std
sliders (all three at 0 skips Monte Carlo - the chart then shows a plain
adjusted line, no interval band), a "Run simulation" button (deliberately
not auto-run-on-slider-change, since the route is gated at operator-or-
higher as a heavier computation - see `api/routes_simulate.py`'s own
docstring), a baseline-vs-adjusted chart with an optional PI band, and a
loss-breakdown panel. A viewer-role account gets a specific "requires an
operator or admin account" message on the resulting 403, not a generic
error. **No battery/BESS dispatch** - STEP 9's brief also asked for it, but
that directly contradicts an explicit, twice-confirmed decision elsewhere
in this repo (fully on-grid, no battery anywhere, permanently out of
scope - see root README) - confirmed with the user this pass that the
existing no-battery decision stands, so it wasn't built.

## Auth

The API requires a JWT bearer token on every route, so this app gates
everything behind a login screen (`POST /auth/token`, OAuth2 password flow -
same demo accounts as `api/README.md`'s "Auth" section: `admin`/
`admin-demo-pw`, `operator`/`operator-demo-pw`, `viewer`/`viewer-demo-pw`).
The token is decoded client-side only for display (username/role) - the
backend re-validates the signature on every request regardless, so nothing
here is a security boundary by itself.

**Auto-logout on redeploy (2026-07-17)**: the user's own explicit request -
any code Claude ships, to either GitHub (-> Cloudflare, frontend) or Railway
(backend), should force every currently-logged-in session to sign back in,
so nobody keeps using a stale frontend against a new backend or vice versa.
Two complementary mechanisms, both routed through `lib/auth.tsx`'s
`forceLogout(reason)`:

- **`lib/api.ts`**'s `request()` calls a module-level "unauthorized handler"
  (registered by `AuthProvider` on mount) on any 401 from an authenticated
  call - covers ordinary token expiry *and*, as of the API's new `deploy_id`
  JWT claim (`api/src/nongfab_api/auth.py`), a token minted before the
  API's most recent Railway redeploy.
- **`lib/deployWatch.ts`**'s `useDeployWatch()` hook (mounted in
  `Layout.tsx`, so only while already authenticated) polls `GET /version`
  (backend `deploy_id` change) and diffs the freshly-fetched `index.html`
  against its own session baseline (frontend/Cloudflare redeploy - Vite's
  content-hashed asset filenames mean any rebuild changes it) once a
  minute, catching both an idle session with no other API calls in flight
  *and* the one case the backend-side check can't see at all: a
  frontend-only redeploy that never touches the API.

Either path shows a short Thai explanation on the next Login screen
(`.login-notice`) instead of silently kicking the user back with no
context - a manual "Sign out" click stays silent, only auto-triggered
logouts show a reason.

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
- **SLD viewer is generated, not scanned** (`SLDViewer.tsx`,
  `EnergyReportPage.tsx`): plain HTML buttons/divs laid out as a topology
  diagram (string -> inverter -> AC), built from the zone's own real
  equipment counts (`nongfab_features.sld.build_sld()`) - not an image of
  the original SLD PDF (none is bundled in this repo). Every node is a
  `<button>` so it's keyboard-operable and click-testable without
  simulating hover.
- **Irradiance map has no real basemap tiles** (`IrradianceMapView.tsx`):
  MapLibre is initialized with a self-contained blank style (a solid
  background color, no external source) rather than a real tile provider,
  since picking one means an API-key/ToS decision this session didn't make
  (see the "stop and ask before deciding on external-source ToS" rule in
  root instructions) - the irradiance overlay and zone pins are functionally
  complete without real street/satellite tiles underneath. Swapping in a
  real basemap style URL is a follow-up, not a redesign.
- **Time-scrubber queries use `placeholderData: keepPreviousData`**
  (`lib/queries.ts`'s `useGeometry`/`useIrradianceMap`): each scrubbed `at`
  is a distinct query-cache key, so without this, `data` would go
  `undefined` between every tick, unmounting/remounting the whole WebGL/
  MapLibre canvas underneath (discarding camera pan/zoom, and - for the
  irradiance map - silently resetting the layer-toggle checkboxes back to
  their default). Found live this pass - see "Verified live" below.
- **`nearestToTimestamp()`** (`lib/chartData.ts`, generalized from the
  existing `nearestToNow()`): the 3D page's Feature C <-> Feature A
  integration reuses this to find the forecast point and the actual/
  generated point nearest the *scrubbed* time, not real "now" - the same
  "pick the nearest row" idea `nearestToNow`/the backend's `/ws/live`
  already use, just against an arbitrary target instead of `Date.now()`.
- **Zone-pin popup content is computed server-side, not client-side**
  (`IrradianceMapView.tsx`'s `popupHtml()`): `estimated_ac_kw`/
  `plant_factor` come straight from `/irradiance-map`'s response (Module 6
  already ran them through Module 5's real PV-conversion + loss-model
  chain) - this component only formats them, it doesn't compute them.

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
- **`/3d`'s time-of-day slider is labeled and operates in UTC, not Nong
  Fab's local time (Asia/Bangkok, UTC+7)** - confirmed live while verifying
  the 2026-07-16 building-massing change: the page's own default (12:00 UTC)
  renders as full nighttime (0% solar access, sun altitude -4°) for a plant
  at ~12.7N, 101.1E, since that's actually 19:00 local. The label is honest
  (says "UTC", doesn't claim local time), so this isn't a data-correctness
  bug, but it is a real first-impression gap for a Thailand-focused
  dashboard - a visitor opening `/3d` sees a dark, panel-less-looking scene
  by default instead of the plant lit up at whatever the actual local time
  of day is. Not fixed this pass (out of the requested scope, and the same
  UTC-indexed-sine-curve pattern exists in a few other synthetic generators
  - see `simulation/README.md`'s own note on this in the monthly-estimate
  section); flagged here as a concrete follow-up candidate.
- `String view` colors each sub-array/block with a hash-derived color for
  visual distinction, not a designed palette - can land on a dark, low-
  contrast color against the night scene's dark background (a cosmetic gap,
  not a data-correctness one).
- Code-splitting landed with STEP 8C: adding MapLibre grew the single
  bundle to ~2.6MB (~720KB gzipped), which was the trigger to do the pass
  deferred in STEP 8B (see the old note this replaced). `/3d`,
  `/energy-report`, and `/irradiance-map` are now `React.lazy` route
  chunks fetched on navigation; `/forecast` (Recharts) stays eager since
  it's the default landing page anyway. The initial login/forecast load is
  now ~677KB (~200KB gzipped); Three.js and MapLibre (~245KB/~275KB
  gzipped each) only load when their route is visited.
- `SLD viewer` (GIS/ISB) shows an even-split approximation of per-string
  module counts, not a real per-string survey - same caveat and same
  `approximate_string_distribution` flag as `panel_geometry.py`'s own
  GIS/ISB visualization approximation (only Jetty has real per-string data).
- Irradiance map's `cloud_factor` is a documented synthetic placeholder
  (deterministic sine-wave field, not a real Himawari sample) - see
  `features/README.md`'s "SLD topology & irradiance grid" section for why
  and what the real follow-up looks like.
- The spec's Feature E layer-toggle list included an "actual/estimated"
  category alongside site/grid/boundary. Only 3 real toggles exist
  (irradiance overlay, zone pins, zone boundary) - deliberately no
  "actual/estimated" toggle, since there is no real telemetry anywhere in
  this system yet to show as "actual" (same data-accumulation caveat as
  every other module); faking a second data layer to fill out the toggle
  would violate this project's own "don't fabricate site-specific data"
  rule. Revisit once Module 1/2 have accumulated real history.
- The string power-balance flag (`/3d`'s warning banner) is only ever
  non-empty for Jetty - GIS/ISB's block layout doesn't assign a real
  electrical string to each geometry row, so there's nothing honest to
  flag there (see `features/README.md`'s `string_power_balance()` section).
  `estimated_ac_kw`/`plant_factor` in the irradiance map's zone-pin popup
  use a fixed nominal ambient temperature (`NOMINAL_AMBIENT_TEMP_C = 30`
  in `routes_irradiance_map.py`), not a real reading, for the same
  no-real-history reason.

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

### Verified live - STEP 8C, Energy Report + irradiance map (2026-07-15)

Same real `uvicorn` + `vite dev` pair, headless Chromium with software
WebGL (needed for MapLibre's canvas too, not just Three.js). Confirmed:
`/energy-report` renders system summary/annual/losses(incl. temperature)/
CO2/SLD for GIS with real numbers; switching to Jetty shows the simulated
badge, higher soiling (6.0% vs GIS's 2.5%), and the SLD's real sub-array
ids (`01A.L`/`02A.L`/`03A.R`/`04A.R`) instead of synthetic `INV-N` labels;
clicking a string or inverter node in the SLD viewer updates the detail
panel. `/irradiance-map` renders a MapLibre canvas with 100 grid points and
3 labeled zone pins, the clear-sky GHI readout tracks the time scrubber
(0 W/m² at night), and both layer-toggle checkboxes work. No console/WebGL
errors; the only 404s seen were `/forecast/*/day` (pre-existing, documented
"no model trained yet" behavior, unrelated to this pass).

**Found and fixed two real bugs, both in `web/`, neither in the backend**:

1. Toggling "Irradiance overlay" off, then moving the time scrubber, made
   the overlay **reappear** even though the checkbox stayed unchecked.
   Root cause: `useIrradianceMap`'s query key includes `at`, so every
   scrubber tick was a *new* cache entry - `data` went `undefined` during
   each refetch, which unmounted `IrradianceMapView` (its containing
   `{map.data && ...}` block), destroying the whole MapLibre instance and
   recreating it from scratch with default (visible) layer visibility,
   silently discarding the toggle state. The same class of bug already
   existed in `useGeometry` (`/3d`'s scrubber), just less visible there
   since a remounted Three.js camera happens to reset to the same
   deterministic framing rather than a wrong one - but it was still
   discarding any user pan/zoom on every tick, including every 400ms during
   auto-play. Fixed both hooks with `placeholderData: keepPreviousData`
   (`lib/queries.ts`) so `data` stays defined across a refetch instead of
   going through `undefined`.
2. Independently, the layer-visibility effect could run *before* MapLibre's
   async `'load'` event had actually added the layers (`map.getLayer(id)`
   returns undefined until then), silently no-op-ing a toggle clicked in
   that window with no way to recover once the layers did appear (the
   effect never re-runs unless the toggle props themselves change again).
   Fixed `IrradianceMapView.tsx` with a `layersReady` state flag set inside
   the `'load'` handler, added to the visibility effect's dependency array,
   so it correctly re-applies the current toggle state once the layers
   actually exist.

### Verified live - recheck-driven spec gap closures (2026-07-15)

A recheck against the full Feature A-E spec (paired with the API side - see
`api/README.md`'s own "Verified live a fifth time") found and closed 5
addressable gaps; re-verified live the same real `uvicorn` + `vite dev` +
headless-Chromium-with-software-WebGL setup:

- `/forecast`, GIS selected: the new zone-info panel renders lat/lon,
  installed, estimated, plant factor, est. irradiance, and cloud factor;
  confirmed it disappears when switching to "All" (รวม), since lat/lon has
  no single-point meaning there.
- `/3d`, Jetty selected, date `2026-07-14`, time scrubbed to `11:15` UTC
  (low sun ~6deg elevation, azimuth ~291deg - close to Jetty's own
  270deg-facing default): the string power-balance warning banner
  correctly lists all 4 real sub-arrays (`01A.L`/`02A.L`/`03A.R`/`04A.R`),
  each at ~2.97kW imbalance against the 2kW design limit. The forecast/
  actual readout shows "Forecast: no model trained yet" (correct - no
  model exists in this dev API instance) alongside a real "Actual" value.
- `/irradiance-map`: clicked a real zone pin on the live canvas (scanned a
  small grid of screen positions near the pin cluster to find one, since
  pixel coordinates for a MapLibre feature aren't exposed statically) and
  confirmed the popup shows lat/lon, installed, estimated output, plant
  factor, est. irradiance, and cloud factor - e.g. ISB at night: `lat/lon:
  12.68134, 101.11832`, `plant factor: 0.0%`. The new "Zone boundary"
  checkbox toggles independently of the other two.

No new bugs found this round.

### Verified live - STEP 9, Simulation Playground (2026-07-15)

Same real `uvicorn` + `vite dev` pair, headless Chromium. Ran GIS with
default (all-zero) scenario params - chart shows baseline bars and an
adjusted line sitting exactly on top of them (no scenario applied yet is
correctly a no-op), loss breakdown matches the real PVWatts figures.
Moved curtailment to 40% and re-ran - the adjusted line correctly dropped
to ~60% of baseline at every point (`curl`-verified the same request
directly too: e.g. Jetty's noon baseline 187.5kW -> adjusted 112.5kW,
exactly 60%). Switched to Jetty and re-ran - loss breakdown correctly
shows 6.00% soiling (vs GIS's 2.50%) and the "Simulated zone" badge
appears. No console/page errors; the only 404s were the pre-existing
`/forecast/*/day` "no model trained yet" ones, unrelated to this page.

One thing chased down that turned out **not** to be a bug: an early
screenshot of the Jetty chart appeared to be missing its baseline bars
entirely. Inspecting the actual DOM (`.recharts-bar-rectangle` elements)
found the bars present with correct heights - Recharts animates bars
growing from 0 height on data change, and the screenshot had been taken
before that animation settled. Confirmed by re-screenshotting the same
state after a longer wait: bars appeared exactly as expected. A real
product bug would have been an empty/wrong DOM, not a mistimed screenshot,
so this was reported as "verified, no bug" rather than "fixed."

### Verified live - `/3d` building massing + grid floor (2026-07-16)

Same real `uvicorn` + `vite dev` pair, headless Chromium (no explicit
`--use-gl=swiftshader` needed this time - software WebGL rendered
correctly by default). Screenshotted all 3 zones at night (page default,
12:00 UTC) and again after driving the time-of-day slider to 05:00 UTC
(~noon local) via Playwright:

- GIS/ISB: a solid gray building volume now sits under the panel grid
  (previously panels floated directly over a flat ground plane with no
  structure at all), panels correctly colored red at night / green at
  midday, sun-path arc line and compass both still correct.
- Jetty: a thin elevated deck (not a solid building block) with visible
  support-pile legs at its corners, matching its real trestle-over-water
  structure - the `simulated_zone` badge still appears correctly.
- The dark-navy grid floor (`@react-three/drei`'s `<Grid>`) is clearly
  visible extending toward the horizon in Jetty's far-zoomed default camera
  framing (its 4 sub-arrays are spread across a ~1.25km trestle - see the
  existing camera-framing note above) - visually the closest this scene has
  gotten to the reslink.org reference's "abstract block + grid" mode.

**Found something worth flagging, not a bug in this change**: this same
pass is what surfaced the UTC-vs-local-time default-view gap now documented
under "Known gaps" above (`/3d` defaults to a night view for a Thailand
plant because its slider is UTC-indexed) - pre-existing behavior, unrelated
to the building-massing/grid-floor work itself, just noticed while
screenshotting it.

### Verified live - `/3d` icon rail + solar-access gauge (2026-07-16)

Same real `uvicorn` + `vite dev` pair, headless Chromium. Screenshotted the
new chrome at night (page default) and after driving the time slider to
local noon:

- The gradient gauge's white marker sits at the far left with "0%" at
  night, and at the far right with "100%" at noon - correctly tracking
  `average_solar_access_pct` live as the time scrub moves, not a static
  decoration.
- The icon rail's sun/layers icons correctly reflect the active view mode
  (purple highlight moves between them on click); clicking the layers icon
  switches GIS to string-color mode - panels stay uniformly green rather
  than showing distinct per-string colors, which is *correct*, not a bug:
  GIS has only one `block_id` (no real per-string survey - see
  `panel_geometry.py`'s own docstring), so `stringColor()` hashes to one
  color for the whole grid; Jetty's 4 real sub-arrays would show 4 distinct
  colors instead.
- Clicking play switches the icon to the pause glyph and the time slider
  visibly advances (05:00 -> 05:15 across one screenshot); clicking reset
  camera view doesn't throw and the scene remains rendered. No console or
  WebGL errors across any of it.

### Fixed - GIS ground-mount vs rooftop 3D representation (2026-07-16)

The user shared their own Google Earth screenshots (corner-pinned
UL/UR/LL/LR for GIS, ISB, Jetty) for "PTTLNG Nong Fab (LMPT2), Rong Pui
Alley, Mueang Rayong District, Rayong" and asked for a recheck before going
live. That prompted re-reading `config/assets.yaml`'s own `tilt_deg`
comments, which had already documented (predating the building-massing
feature above) that GIS "looks ground-mount from photos" while only ISB
"looks like rooftop tilted rows from photos" - a distinction the
building-massing work above missed, rendering GIS under the same solid
`BUILDING_HEIGHT_M` block as ISB.

Replaced the binary building/pier split in `Solar3DScene.tsx` with a 3-way
`MountType` (`'ground' | 'rooftop' | 'pier'`), keyed off zone id via
`mountTypeForZone()`. Ground-mount (GIS) now renders 4 short corner support
legs (`GROUND_MOUNT_CLEARANCE_M = 1.0`, a typical fixed-tilt rack's minimum
clearance - not a measurement) instead of a solid mass, with panels sitting
just above grade rather than atop a 10m building that doesn't exist there.

Also added `facility_code: "LMPT2"` and `street_address` to `Site` in
`config/assets.yaml`/`assets.py` (defaulted fields, so existing minimal test
fixtures didn't need updating) - previously not captured anywhere in the
asset registry.

**Verified live**: same real `uvicorn` + `vite dev` pair, headless
Chromium, time slider driven to 05:00 UTC (local noon) via Playwright:
- GIS: panels now sit near grade with no solid mass beneath them (short
  support legs, not visible at this camera distance/angle) - previously a
  gray building block identical to ISB's.
- ISB: unchanged, still a solid rooftop block.
- Jetty: unchanged, still the thin elevated pier deck.

### Fixed - "frozen dashboard numbers" + `/3d` default view + panel color (2026-07-16)

The user asked "why don't the dashboard numbers ever change" and shared a
Forecast-page screenshot showing `Power: 0.0 kW`, a stuck `Daily cumulative
energy`, and "No day-ahead forecast model has been trained for this zone
yet". Investigation confirmed there is genuinely no real production
telemetry anywhere in this system (no Huawei FusionSolar/SolarFusion
integration - see `api/routes_performance.py`'s own docstring), then found
three separate, real causes on top of that:

1. **No `refetchInterval`** on `usePerformance`/`useForecast` (`lib/
   queries.ts`) - the dashboard only fetched once per page load. Fixed:
   both now poll every 60s (approved by the user over "leave it alone").
2. **`ac_energy_kwh_today` summed the whole 24h synthetic day**, not "so
   far" - it already showed the day's final total regardless of the actual
   time, which is why it looked frozen no matter when you checked. Fixed in
   `routes_performance.py` to sum only hours up to now.
3. **The big one**: `synthetic_day_irradiance_temp()`'s (`dev_data.py`) day/
   night sine curve peaked at 12:00 UTC (=19:00 ICT, Thai *nighttime*) - it
   was never actually aligned to Thailand's real daylight hours, unlike
   `/geometry`/`/sun-path`'s real pvlib solar position. So at real Thai
   midday the whole plant would show `Actual: 0.0 kW` and every panel red,
   which is almost certainly also why the *live* Railway deployment showed
   "no forecast model trained" (a generic error banner for any request
   failure, not specifically a training-status message) - `get_forecast_
   with_fallback()` is coded to never throw for a known zone, so a 500/mis-
   labeled response there points at a stale production build rather than
   this bug, but the visual symptom (0 kW, red panels) is explained by this
   phase misalignment either way. Fixed: shifted the phase to `(hour + 1)`,
   peaking at 05:00 UTC (Thai noon) - shared by every caller (`/performance`,
   `/simulate`, `/energy-report`, `/irradiance-map`, `/ws/live`).
4. Added `live_efficiency_factor()` (`dev_data.py`): a bounded [0.85, 1.0]
   multiplier on top of the physics estimate, keyed off real wall-clock
   time (5-minute buckets, linearly interpolated) instead of a fixed seed -
   so `/performance` actually drifts across the 60s poll instead of
   returning bit-for-bit identical numbers, while never claiming *more*
   than the physics model. User's explicit choice over a frozen fixed value
   or fully random jitter.
5. `/3d`'s default time-of-day slider moved from 12:00 UTC (=19:00 ICT,
   nighttime) to 05:00 UTC (=12:00 ICT, local noon) - the same
   already-documented "Known gaps" item above, now resolved.
6. Panel coloring in 'access' view mode now multiplies each panel's
   `solar_access_pct` by the zone's live output ratio (`Solar3DScene`'s new
   `zoneOutputRatio` prop, computed in `Solar3DPage.tsx` from `/performance`
   vs. the zone's rated capacity) before coloring - user's explicit choice
   over keeping the color purely shading-based, since the shading model is
   geometrically binary (0% or 100%) almost all day and rarely showed the
   orange/yellow the user wanted. No real per-panel telemetry exists, so
   this applies one zone-level ratio uniformly, not a true per-panel value.

**Verified live**: real `uvicorn` + `vite dev` + Playwright. At the new
05:00 UTC default, GIS showed `Actual: 44.3 kW` and solid green panels
(previously `Actual: 0.0 kW`, all red); at 09:45 UTC (near this synthetic
model's dusk), `Actual: 11.2 kW` and orange panels - confirming the
gradient. The Forecast page's "no forecast model trained" banner did not
reproduce against this freshly-built local API, and at the real current
wall-clock time (15:25 UTC = 22:25 ICT, genuine Thai nighttime), `Power:
0.0 kW` correctly appeared - the model now agrees with real Thai time
instead of contradicting it.

### Added - live clock block + approximate prediction interval (2026-07-16)

Same session, two more small user-requested additions to the Forecast page:

- **Live clock block** beside the power chart (`ForecastPage.tsx`'s new
  `LiveClock` component): shows Thai local time (ICT) large and prominent,
  with UTC underneath as a secondary reference plus a hint that the chart's
  own x-axis is UTC-labeled - directly aimed at the "why don't the times
  match" confusion this whole dated section has been about.
- **Approximate prediction-interval band on the physics fallback**: the
  chart's shaded "Prediction interval" band was previously invisible
  whenever no ML model had trained yet (`lower`/`upper` were always `null`
  on that path). `forecast/serving.py`'s `get_forecast_with_fallback()` now
  adds a fixed +/-20% band (`FALLBACK_PI_HALF_WIDTH_PCT`, a documented
  approximation, not a measured interval - see that constant's own
  docstring) so the chart shows something rather than nothing. No explicit
  hand-off logic needed: the existing try/except already prefers a real
  ML model's quantile-based interval the moment one is trained, so the
  fixed band stops being served automatically once enough real history
  accumulates. `ForecastResponse.model_type` is now surfaced on the
  frontend so an italic caption appears under the chart whenever the band
  shown is this approximation, never presenting it as a real confidence
  interval.

**Verified live**: real `uvicorn` + `vite dev` + Playwright. The clock
block correctly showed Thai local time exactly +7h ahead of the UTC line
(00:31:25 ICT / 17:31:25 UTC, both ticking live). The prediction-interval
band rendered as a visible shaded region around each of the 3 forecast
peaks, with the "approximate ±20%" caption present underneath.

### Added - `/financial` investment-analysis playground (2026-07-16)

The user reframed the whole project's priorities partway through this
session: sub-daily/hour-ahead/day-ahead forecasting (Module 4) has little
operational value at this site (fully grid-tied, no battery, capacity
capped by available land - nothing dispatch-related changes based on a
forecast), and what actually matters is investment payback. New page
`FinancialPage.tsx`, mirroring the Simulation Playground's slider-input +
output-card UX rather than inventing a new layout:

- Sliders for every `nongfab_financial.model.FinancialAssumptions` field
  (OPEX %, tariff, tariff/OPEX escalation, WACC, tax rate, BOI holiday
  years, degradation, lifetime), plus a CAPEX auto-estimate/custom-figure
  toggle.
- KPI cards: CAPEX, NPV, IRR, LCOE, simple payback, discounted payback.
- A 25-year cumulative (discounted vs. undiscounted) cash flow chart with
  a zero reference line, so the payback crossing is visible directly on
  the chart, not just in the KPI numbers.
- A persistent warning banner: every assumption is a documented
  placeholder pending the user's real CAPEX/PEA-tariff/WACC/BOI figures
  (Thailand's 20% corporate tax rate is the one real fact) - see
  `financial/README.md`'s own table.
- Runs once automatically on mount with placeholder defaults so the page
  isn't empty on first load, then re-runs on demand as the user adjusts
  sliders (`useEffect` + `useFinancial()` mutation, same "run on demand"
  pattern as `useSimulate()`).

**Verified live**: real `uvicorn` + `vite dev` + Playwright. Loaded with
default placeholders: CAPEX ฿6,006,000 (auto from 200.2 kWp installed),
NPV ฿12,886,082, IRR 26.2%, LCOE ฿1.47/kWh, simple payback 4.0yr,
discounted payback 5.0yr - the cumulative cash flow chart's zero-crossing
matched those payback years visually. Caught and fixed a real bug during
this pass: the Y-axis's default 90px width clipped the leading digit off
large THB figures (e.g. "5,000,000" rendered as ",000,000") - fixed by
switching to a compact "฿12.9M" tick formatter instead of full digit
strings.

### Fixed - forecast x-axis kept drifting on every poll + added a model info panel (2026-07-16)

The user spotted a real bug: the Forecast chart's x-axis tick labels kept
changing on every page load/60s auto-refresh - "01:47" one poll, "02:29"
the next - and asked why, worried it would confuse viewers. Root cause:
`forecast/serving.py`'s timestamp grids (`get_forecast_with_fallback()` and
`get_latest_forecast()`) were anchored directly to the raw, unrounded
`datetime.now(timezone.utc)`, which includes whatever random seconds/
minutes happened to be on the clock at request time - every poll baked a
different sub-minute offset into every forecast timestamp. This was always
latent, but the 60s `refetchInterval` added earlier this session (see this
file's own dated entry above) made it constantly visible instead of only
on a manual reload.

Fixed with a new `_ceil_to(dt, step)` helper that rounds a timestamp up to
the next clean boundary (`:00` for hourly grids, `:00/:10/:20...` for the
10-minute minute-ahead grid) before it's used as the anchor - applied to
both the physics-fallback path (the one actually serving live now) and the
real-ML-model path (so this doesn't resurface once a model trains), plus
`_synthetic_day_df()`'s own internal anchor. 7 new tests in
`test_serving.py`, including a direct regression test that two calls a few
seconds apart now produce identical timestamp grids.

Also added, per the same request: a collapsible "ℹ️ โมเดลพยากรณ์ที่ใช้ใน
หน้านี้" info panel (native `<details>`/`<summary>`, no extra JS state)
below the horizon toggle, with a table naming every forecast model (Day-
ahead → NeuralProphet, Intra-day → LightGBM/Random Forest auto-select,
Minute-ahead → CNN-LSTM, the last of which isn't exposed via this page's
toggle but is used elsewhere) plus a plain-language explanation of what
each horizon is actually for.

**Verified live**: real `uvicorn` + `vite dev` + Playwright. The chart's
x-axis ticks now read clean hour boundaries (`00:00`, `09:00`, `18:00`,
`03:00`...) instead of the previous drifting `:47`/`:29` offsets, and the
tooltip on hover shows a clean `16:00` too. The collapsible model info
panel opens correctly, showing all three models with their ranges/purpose.

### Added - date shown on the forecast x-axis, not just time (2026-07-16)

Follow-up to the fix above: the day-ahead horizon spans 72h/3 calendar
days, but the x-axis and tooltip still only showed `HH:MM` - the same
`09:00` label repeats three times across the chart with nothing to tell
which day it's on. User asked for the date to visibly progress alongside
the time.

Added `formatDateHourUtc()` in `timeScrub.ts`, combining a short UTC date
(`17 Jul`) with the existing `HH:MM` into `"17 Jul 09:00"`. Used for both
the chart's `XAxis` tick formatter and the `Tooltip` label formatter
(`minTickGap` raised from 24 to 60 to keep the wider labels from
overlapping). The minute-ahead/intra-day weather strip elsewhere on the
page keeps the plain `HH:MM` formatter, since that view never spans a day
boundary. Date is pinned to `'en-GB'` day-month order explicitly (not the
browser's default locale) so the axis reads the same regardless of the
viewer's locale settings. 2 new tests in `timeScrub.test.ts`, including a
UTC-midnight boundary check (`23:00` on one day → `00:00` on the next
shows the date advancing correctly).

### Added - minute-ahead red-line panel + LightGBM/RandomForest dot coloring + model error line (2026-07-16)

Two related requests: (1) show the Minute-ahead (CNN-LSTM) forecast directly
on the dashboard instead of only mentioning it in the model-info panel, plus
a "model error" figure from each lead hour's LightGBM-vs-Random Forest
competition shown as a line on the chart; (2) color-code the Intra-day
chart's forecast points by which algorithm actually won each lead hour
(green vs orange), to make the auto-select's adaptiveness visible instead of
just claimed in prose.

- New `MinuteAheadPanel` component (`ForecastPage.tsx`): a small always-
  visible `LineChart` (not gated by the Day-ahead/Intra-day toggle, since
  10-min-resolution points would distort that chart's hourly-bucketed
  x-axis) showing the next 60 minutes in red (`var(--chart-minute)`).
  Fetches via `useForecast(zoneId, 'minute')`/`useAllZonesForecast('minute')`
  the same way the main chart fetches its own horizon, independently of
  `horizonToggle`.
- The main chart's `pred` dots are now a custom `forecastDot()` renderer:
  colored `var(--chart-lgbm)` (green) or `var(--chart-rf)` (orange) by each
  point's `algorithm` field when `horizonToggle === 'hour'`, plain blue
  otherwise (Day-ahead's NeuralProphet doesn't auto-select, so no coloring
  there). A new dashed `error` `Line` ("Model error (RMSE)") appears
  alongside it, hour-ahead only - the winning candidate's own held-out
  validation RMSE per lead hour (see `forecast/README.md`'s matching dated
  entry for where these numbers actually come from - a real measured
  training-time metric, not invented for the chart). A caption below the
  chart explains both, shown only when there's real per-point algorithm data
  to explain (not during the physics-only fallback, which has no algorithm
  at all).
- `types.ts`'s `ForecastPoint` and `chartData.ts`'s `ChartRow` both gained
  `algorithm`/`error` fields; `mergeGeneratedAndForecast` carries them
  through, `sumForecastAcrossZones` sums `error` (same approximate
  treatment as `lower`/`upper`) but drops `algorithm` to `null` for the
  "All" (รวม) aggregate, since each zone can independently pick a different
  winning algorithm - there's no single "the" algorithm to report once
  summed across zones.
- New CSS vars `--chart-lgbm`/`--chart-rf`/`--chart-minute`/`--chart-error`
  (light + dark), matching hex values already used elsewhere (`--ok`,
  `--chart-rainy`, `--danger`) but named for this feature so the chart code
  doesn't read as randomly reusing unrelated tokens.
- Model-info panel's Minute-ahead row updated - no longer says "not shown on
  this page", now points at the red line below the main chart.

**Verified live**: real `uvicorn` + `vite dev` + Playwright, with a genuinely
trained hour-ahead model (not just the physics fallback) so the algorithm
auto-select had something real to show - confirmed the Intra-day chart's
dots visibly alternate green/orange across lead hours (`lightgbm`,
`lightgbm`, `random_forest`, `lightgbm`, `lightgbm`, `random_forest` in the
run screenshotted), the dashed error line and its legend entry render, the
explanatory caption appears only on the Intra-day tab (confirmed absent on
Day-ahead), and the Minute-ahead panel renders a connected red line for all
6 points on every tab.

### Added - Sum-k LSTM as a third dot color on the Intra-day chart (2026-07-16)

Follow-up to the entry above: the backend gained a third Intra-day
candidate, Sum-k LSTM (a shared-backbone, multi-head prediction-interval
architecture from the user's own reference course slides - see
`forecast/README.md`'s matching dated entry for the full architecture and
integration story). `ALGORITHM_DOT_COLOR` gained a `sum_k_lstm` entry
(`var(--chart-sumk)`, a teal distinct from LightGBM's green/Random Forest's
orange/Minute-ahead's red/the error line's gray), the legend caption below
the Intra-day chart now names all three candidates, and the model-info
panel's Intra-day row lists all three too.

### Fixed - three recheck bugs: minute-ahead "All" zone aggregation, UTC-vs-Thai time display, weather-strip hours (2026-07-17)

The user flagged three issues live off two screenshots. All three are
frontend-only fixes; no `api/`/`forecast/`/other backend package changed.

1. **Minute-ahead "All zones" panel showed one dot instead of a connected
   line.** `sumForecastAcrossZones` (`lib/chartData.ts`) bucketed rows by
   `hourKey()` - truncating every timestamp to its containing hour - which is
   correct for the hourly-cadence Day-ahead/Intra-day series but collapses
   the 10-minute-resolution Minute-ahead series down to a single point per
   hour. Fixed by adding `exactTimeKey(iso) => iso` (identity key) and
   widening `sumForecastAcrossZones` to take an optional `keyFn` parameter
   (default `hourKey`, unchanged for the two hourly charts).
   `ForecastPage.tsx`'s minute-ahead "All" aggregation now passes
   `exactTimeKey` explicitly. Verified live: the "All" zones Minute-ahead
   panel now renders a connected 6-point red line matching the per-zone
   (GIS/ISB/Jetty) charts, instead of one dot.
2. **Every time display across the site was UTC, not Thai local time.** The
   user asked for Forecast, Simulation, Financial, 3D View, Energy Report,
   and Irradiance Map to all read in Asia/Bangkok time (UTC+7). Added
   `formatHourIct`/`formatDateHourIct` (`lib/timeScrub.ts`, `timeZone:
   'Asia/Bangkok'` mirrors of the existing UTC formatters) and
   `utcMinutesToIctHhMm` for the two time-scrubber pages. Two different fix
   shapes were needed depending on whether the time value is pure display or
   also drives a backend query:
   - **Pure display** (chart axes/tooltips, weather-strip labels,
     Simulation's chart): swapped the UTC formatter for the ICT one
     directly - `ForecastPage.tsx` (chart x-axis + weather strip, via
     `replace_all`), `SimulationPlaygroundPage.tsx` (both chart usages).
   - **Scrubber value that also builds the backend query** (`Solar3DPage.tsx`,
     `IrradianceMapPage.tsx`): `buildAtIso` stamps the scrubber's
     minutes-of-day as a literal UTC `"Z"` timestamp for the API call, so the
     underlying state had to stay UTC-semantic - converting it to ICT before
     querying would shift the queried instant by 7 hours. Only the
     *displayed* readout was converted (`utcMinutesToIctHhMm`), with the raw
     UTC value kept alongside in a small gray hint (`(HH:MM UTC)`) so the
     two controls stay auditable against each other. Labels changed from
     "Time (UTC)" to "Time (เวลาไทย ICT)" on both pages.
   - Energy Report and Financial pages don't format individual
     timestamps (daily/monthly aggregates and a one-shot analysis form), so
     neither needed a code change for this item.
   Verified live: Forecast page's chart axis and weather strip now read ICT
   (e.g. "17 Jul 17:00"); `/3d` and `/irradiance-map` both show "12:00 (05:00
   UTC)" for their default scrub position.
3. **Weather strip showed ~25°C at Thailand noon.** Not a data-fetch bug -
   `WEATHER_HOURS` (`ForecastPage.tsx`) was still `[6, 9, 12, 15]`, sampling
   those as UTC hours (09:00/12:00/15:00/18:00 ICT is what those actually
   render as pre-fix, but combined with the display formatter still being
   UTC at the time, the strip's *labels* read "06:00/09:00/12:00/15:00" while
   Bangkok's real local time at those instants is 13:00/16:00/19:00/22:00 -
   evening/night temperatures, hence the implausibly low ~25°C reading at
   what the label claimed was midday). Fixed by changing `WEATHER_HOURS` to
   `[0, 3, 6, 9]` (UTC hours that map to ICT 07:00/10:00/13:00/16:00,
   chosen to avoid crossing a UTC day boundary within a single day's 24-point
   hourly array) together with the ICT display fix from item 2. Verified
   live across all,GIS/ISB/Jetty: strip now reads "07:00 (29.4°C), 10:00
   (32.4°C), 13:00 (33.5°C), 16:00 (29.9°C)" - a plausible Thailand midday
   temperature curve.

### Fixed - Generated-power bars showing future data, Prediction interval color clash, and a new layperson guide panel (2026-07-17)

Three more small-but-important fixes to `ForecastPage.tsx`, off a live screenshot:

1. **"Generated power" bars showed data ahead of the actual clock.** The
   underlying `hourly` series (from `/performance`) is a full synthetic
   *today*, covering hours that haven't happened yet as well as ones that
   have (see `mergeGeneratedAndForecast`'s own docstring) - so a chart
   opened at, say, 08:45 already showed bars out to 17:00, making a series
   meant to read as "what was actually produced" look like it was itself a
   forecast. Added `truncateGeneratedToNow()` (`lib/chartData.ts`), which
   nulls `generated` for any row later than the current real time, leaving
   `pred`/`lower`/`upper`/`band` untouched since the Forecast line is
   *supposed* to extend into the future. Wired into `ForecastPage.tsx`'s
   `chartRows` memo - applies uniformly to all/GIS/ISB/Jetty and both
   Day-ahead/Intra-day, since they all flow through the same merge step.
   Verified live: bars now stop right around "now" instead of covering the
   whole first day's generation curve.
2. **Forecast line and Prediction interval band were both blue,** hard to
   tell apart. Added a dedicated `--chart-pi` CSS var (green - `#059669`
   light / `#34d399` dark, distinct from `--chart-forecast`'s blue) and
   pointed the Prediction interval `<Area>`'s fill at it instead of reusing
   `--chart-forecast`. Scoped to `ForecastPage.tsx` only - `--chart-forecast`
   itself is unchanged, so Simulation/Financial/Energy Report (which also
   reference it) are unaffected.
3. **New layperson info guide.** Added `ViewerGuidePanel` - a collapsible
   `<details>` panel (`.viewer-guide-panel`), same open/close pattern as the
   existing technical `.model-info-panel` table, but written for "คนบ้านๆ
   ธรรมดาทั่วไป" (regular non-engineer viewers) per the user's own framing:
   what the Forecast section is for, what each axis/series means (Generated
   power vs Forecast vs Prediction interval vs Model error, and that
   hovering the chart shows a value tooltip), what Day-ahead vs Intra-day
   mean, and a full glossary (name, plain-language principle, why chosen)
   for every model currently in the pipeline - NeuralProphet, LightGBM,
   Random Forest, Sum-k LSTM, CNN-LSTM. **Maintenance instruction left as a
   code comment directly above the component**: any future model added to
   the forecast pipeline (replacement or new competing candidate) must get
   an entry in this same guide in the same pass, not as a follow-up - a
   viewer should never see the app using a model this panel doesn't mention.

Verified live via Playwright across the "All"/GIS zones and both
Day-ahead/Intra-day views; `tsc -b`, `vitest run` (110/110), and `oxlint`
all clean.

### Added - auto-logout on redeploy (2026-07-17)

See "Auth" above for the design (`lib/api.ts`'s 401 handler +
`lib/deployWatch.ts`'s poll-and-diff hook, both routed through
`lib/auth.tsx`'s `forceLogout`). New files: `lib/deployWatch.ts`. Changed:
`lib/api.ts` (`setUnauthorizedHandler`/`getVersion`), `lib/auth.tsx`
(`forceLogout`/`autoLogoutReason`), `components/Layout.tsx` (mounts the
watcher), `components/Login.tsx` + `App.css` (`.login-notice`, shows the
reason).

Verified live end-to-end via Playwright: logged in against a real `uvicorn`
process, restarted that process in place (the same effect on a live token
as a Railway redeploy), waited past `useDeployWatch`'s one-minute poll
interval, and confirmed the browser landed back on the Login screen with
the notice "เว็บไซต์มีการอัปเดตใหม่ กรุณาเข้าสู่ระบบอีกครั้ง" shown - the
same session that was previously on `/forecast` with a valid token. `tsc
-b`, `vitest run` (125/125, 15 new across `lib/__tests__/api.test.ts`,
`lib/__tests__/auth.test.tsx`, `lib/__tests__/deployWatch.test.ts`, and two
more in `components/__tests__/Login.test.tsx`), and `oxlint` all clean.

The frontend-only (Cloudflare-redeploy-via-`index.html`-diff) half of
`useDeployWatch` could **not** be live-verified the same way - there is no
real Cloudflare Pages build happening in this dev sandbox, same category of
"write it carefully, can't verify against blocked/external infra" as
`lib/satelliteTile.ts` and the PVGIS ingestion module earlier in this
project. Its unit tests (`deployWatch.test.ts`) cover the `index.html`-diff
logic in isolation with a mocked `fetch`, but the real Cloudflare deploy
path itself is unverified.

### Fixed - Forecast/Prediction interval disappearing once an hour passed (2026-07-18)

Follow-up to the "Generated-power bars showing future data" fix above: that
fix correctly truncates `generated` to real "now", but the user pointed out
the *opposite* problem existed for the Forecast line and Prediction
interval band - they visibly vanished for any hour once real time moved
past it, because Intra-day/Day-ahead's `/forecast` endpoint is always
computed fresh "as of now" (`forecast/serving.py`'s `issued_at`) and only
ever returns lead hours *forward* from whenever it was called - it was
never a record of what had been predicted for an hour that has since
passed.

New `lib/forecastHistory.ts` (`useForecastHistory`) accumulates every
forecast point ever fetched this session, keyed by target timestamp, so
once an hour has been forecast it stays on the chart even after that hour
is in the past - a newer issuance for the same hour overwrites the older
one. Wired into `ForecastPage.tsx` between the raw per-poll
`latestForecastPoints` and the existing `mergeGeneratedAndForecast` +
`truncateGeneratedToNow` pipeline; resets whenever the viewer switches zone
or horizon (`${zoneId}:${horizon}` as the reset key).

**Bug found and fixed during this same pass**: the first version compared
accumulated points by object identity (`!==`), but `sumForecastAcrossZones`
and the query-derived arrays it consumes have no referential stability
across renders (a fresh array/fresh point objects every render, even when
the underlying values haven't changed) - so every point looked "changed"
on every render, which fed back into the hook's own `setHistory` call and
produced a real `Maximum update depth exceeded` crash, found live testing
this exact fix (not caught by the unit tests, which all passed against
happy-path inputs). Fixed by comparing points field-by-field instead of by
reference; a regression test (`forecastHistory.test.ts`) now locks this in
by asserting a brand-new object with identical field values does not
trigger a state update.

Verified live via Playwright with a mocked `/forecast` route serving two
different lead-hour windows across a real 60-second poll interval: the
chart's Forecast/Prediction-interval line visibly kept the *first* poll's
points after the *second* poll's response had moved on, and hovering a
genuinely past hour's point showed Generated power, Forecast, Model error,
and Prediction interval all together in one tooltip - the user's own
explicit ask. `tsc -b`, `vitest run` (137/137, 5 new in
`forecastHistory.test.ts`), and `oxlint` all clean.

**Follow-up, same day**: this client-side accumulation only helps a tab
that's stayed open across multiple polls - a genuinely fresh page load (or
the deployed prod site opened for the first time) still showed nothing for
the past, because there was nothing yet to accumulate from. The user's own
follow-up screenshot showed exactly that. Closed at the source instead by
persisting forecast issuances server-side - see `forecast/README.md`'s
"Forecast history persistence" entry for the backend half. This
`lib/forecastHistory.ts` client-side accumulator was left in place
regardless (still correct, still harmless, and covers the one gap the
backend's own lookback window doesn't: an hour that ages out of the
server's retention window but was already shown in a tab that's stayed
open longer than that).

**Second follow-up, same day**: even the server-side persistence above had
one more cold-start gap - a genuinely *fresh* deploy/restart starts with an
empty `forecast_history` table, so the first request or two right after
still showed a blank past until enough real polling happened to rebuild it.
Closed by a startup backfill that seeds it immediately on boot - see
`forecast/README.md`'s "Follow-up, same day" entry under "Forecast history
persistence" for the full story, including a real sequencing bug (the new
backfill sat blocked behind slow network-dependent steps) found and fixed
while live-verifying it. Re-verified live after that fix: a brand-new
login on a freshly-booted API immediately showed multiple full day/night
cycles of history on the Day-ahead chart, no gap.

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
