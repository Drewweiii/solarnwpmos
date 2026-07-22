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

### Added - Per-model error lines + Model Competition panel + RMSE guide (2026-07-18)

The single gray dashed "Model error (RMSE)" line on the main Forecast chart
only ever showed the *winning* candidate's own held-out validation RMSE -
the user asked to see all three (LightGBM/Random Forest/Sum-k LSTM) side by
side, distinctly colored so it's clear which line belongs to which model,
plus a brand-new dashboard panel dedicated to the model competition
(separate from the main chart), plus an explanation of what RMSE even is in
the existing viewer guide.

- **`lib/types.ts`**: `ForecastPoint` gained `candidate_errors: Record<
  string, number> | null` - see `forecast/README.md`'s "Per-candidate model
  error exposed" entry for the backend half.
- **`lib/chartData.ts`**: `ChartRow` gained `errorLightgbm`/
  `errorRandomForest`/`errorSumKLstm` (flattened out of `candidate_errors`
  for Recharts `<Line dataKey=...>`), populated in
  `mergeGeneratedAndForecast`; `sumForecastAcrossZones` now also sums
  `candidate_errors` per algorithm across zones for the "All" (รวม)
  aggregate, same "roughly extensive" spirit as the existing `error` sum.
  New `buildCompetitionRows(points, nowIso?)` builds the Model Competition
  panel's rows straight from hour-ahead `ForecastPoint`s: one row per live
  lead hour (`+1h`..`+6h`, filtered to points at/after `now` and capped at
  6), each candidate's own RMSE, the winner (`algorithm`), and a `spread`
  (max - min across whichever candidates competed) - see below.
- **`lib/forecastHistory.ts`**: `pointsEqual`'s field comparison now also
  compares `candidate_errors` (shallow key/value check) - without this, a
  point accumulated before a model had trained (empty `candidate_errors`)
  would never get updated once real values arrived, since every *other*
  field could already match.
- **`pages/ForecastPage.tsx`**:
  - Main chart: the single winner-only error `<Line>` replaced with three -
    `errorLightgbm`/`errorRandomForest`/`errorSumKLstm` - reusing the
    existing `--chart-lgbm`/`--chart-rf`/`--chart-sumk` colors (same colors
    already used for the per-point forecast-dot coloring, so a color means
    the same model everywhere on this page), dashed, shown only when
    `horizonToggle === 'hour'`.
  - New `ModelCompetitionPanel` component/section: always-visible
    regardless of the Day-ahead/Intra-day toggle (same pattern as the
    existing Minute-ahead panel - a dedicated `useForecast(zoneId, 'hour')`/
    `useAllZonesForecast('hour')` fetch, deduplicated against the main
    toggle's own fetch by react-query's shared `['forecast', zone, 'hour']`
    cache key when they coincide). Grouped `<BarChart>`, one group per lead
    hour, all three candidates' RMSE side by side; the actual winner's bar
    is full opacity, the two losing candidates are dimmed (`fillOpacity`
    `1` vs `0.3`, applied per-bar via `<Cell>` - verified by inspecting the
    rendered SVG's `fill-opacity` attributes directly in a live Playwright
    session, not just visually). Hovering shows the winner and the
    `spread` value in the tooltip label.
  - `ViewerGuidePanel`: new "ค่าความคลาดเคลื่อน (RMSE) คืออะไร และทำไมถึงสำคัญ"
    section explaining what RMSE is, why it's the selection criterion, that
    it's *held-out validation* RMSE specifically (not training RMSE), why
    RMSE over MAE for this use case, and how the main chart's 3 lines relate
    to the competition panel's bars - the user's explicit ask ("บอกว่า error
    คืออะไร สำคัญยังไง แล้วเราใช้แบบไหน เพราะอะไร"). Also documents `spread` and
    explicitly notes it is a *validation-time* comparison, not a live
    prediction-disagreement/ensemble-spread metric (see below).
- **Proposed but not built**: the user explicitly invited a proposal for an
  alternative inter-model comparison metric ("ระหว่างโมเดลกันเอง"). The
  `spread` value above (max-min of validation RMSE) was cheap to add since
  every input it needs was already flowing through `candidate_errors`. A
  richer *live* version - standard deviation across the three candidates'
  *current* predictions, a classic ensemble-uncertainty signal that's
  available even for a still-future point with no ground truth yet, unlike
  RMSE - was assessed and explained to the user as a real follow-up
  candidate, not implemented here: it needs every losing candidate's
  trained model object kept around for inference at serving time (today
  `HourAheadKStepModel.models_by_lead_hour` only retains the *winner*'s
  model per lead; a losing candidate's trained object is discarded right
  after `training.py`'s `min()` selection, only its RMSE score survives) -
  a materially bigger storage/compute change than this pass's other
  additions.

**Live-verified end to end via Playwright**, not just `vitest run` (177/177,
7 new in `chartData.test.ts`, 2 new in `ForecastPage.test.tsx`) and `tsc
-b` (clean): booted a real `uvicorn` (production `api/`, file-backed SQLite)
plus this module's own dev API sharing the same MLflow tracking store,
trained a real k-step model, then loaded the dashboard in a real browser
and confirmed (a) the main chart's 3 colored dashed error lines and their
legend entries, (b) a combined tooltip showing Generated power, Forecast,
all three per-model RMSE values, and Prediction interval together at one
hovered point - the original ask - (c) the Model Competition panel's bars
with the winner's `fill-opacity: 1` vs losers' `0.3` confirmed directly
against the rendered SVG, and (d) the expanded guide panel's new RMSE
section rendering correctly.

### Added - Actual/generated power split into 3 recency-colored lines, multi-day history (2026-07-18)

The main chart's "Generated power" was a single purple `<Bar>`, only ever
showing *today* (`/performance`'s `hourly` field has no persistence, see
`forecast/README.md`'s matching entry for the backend half). The user asked
for two things: (1) extend it backward across multiple days like the
Forecast/PI line already does, and (2) since one flat color would be hard
to read against the blue Forecast line, split it into 3 recency-colored
tiers instead of one.

- **`lib/types.ts`**: new `GeneratedPowerPoint {timestamp, ac_kw}`;
  `PerformanceResponse` gained `history: GeneratedPowerPoint[]`.
- **`lib/timeScrub.ts`**: new `ictDateKey(iso)` - YYYY-MM-DD in Thai local
  time (`en-CA` locale formatting happens to be ISO-shaped), needed because
  "is this today?" must follow this project's Thailand-first display
  convention (root `CLAUDE.md`), not a UTC calendar-day slice - ICT's early
  morning hours (00:00-06:59 ICT) fall on the *previous* UTC calendar date.
- **`lib/chartData.ts`**: `ChartRow`'s single `generated` field replaced
  with `actualPast`/`actualToday`/`actualNow` (previous days / today-but-
  already-past / the single most-recent already-happened reading).
  `mergeGeneratedAndForecast()` gained `history`/`nowIso` parameters and
  now outer-joins 3 sources (today's `hourly`, persisted `history`,
  `forecastPoints`) instead of 2; `truncateGeneratedToNow()` nulls all 3
  tiers instead of one. New `sumGeneratedPowerHistoryAcrossZones()` (same
  "All" zone aggregation pattern as `sumHourlyAcrossZones`) and
  `filterToRecentPast()` (bounds `useForecastHistory`'s otherwise-unbounded
  accumulation to a trailing window - used by the Minute-ahead panel below).
- **`index.css`**: 2 new chart color variables, `--chart-actual-today` and
  `--chart-actual-past` (the "now" tier keeps `--accent`, unchanged - same
  purple the old single bar always used). **Found live-testing**: the
  first choice for `--chart-actual-past` was an indigo (`#4338ca`) - it
  read as visually near-identical to `--chart-forecast`'s blue once both
  were rendered together, defeating the whole point of this feature (the
  user's own original complaint was exactly this "hard to tell apart"
  problem). Switched to a warm brown/gold (`#92400e` light / `#d97706`
  dark) - the only hue family not already claimed by another `--chart-*`
  variable on this same chart (blue/green/orange/teal/red/purple/pink are
  all taken).
- **`pages/ForecastPage.tsx`**: main chart's `<Bar dataKey="generated">`
  replaced with 3 `<Line>`s (`actualPast`/`actualToday`/`actualNow`); new
  caption below the chart explaining the 3 tiers; `ViewerGuidePanel`'s
  "Generated power" bullet rewritten to describe the 3-color line instead.
  `MinuteAheadPanel` gained two additions per the user's explicit request:
  (1) its own forecast line now looks ~30 min *backward* too, not just
  forward - `useForecastHistory` (the same client-side accumulator the
  main chart already used) wired to `minutePoints` for the first time,
  filtered to a trailing 30-min window via the new `filterToRecentPast()`;
  minute-ahead has no server-side persistence (`forecast/serving.py`'s
  `FORECAST_HISTORY_LOOKBACK_HOURS` excludes it on purpose), so this
  client-side accumulation is the only source for that. (2) the same
  3-tier actual-power lines now overlay the Minute-ahead panel too, reusing
  `chartRows` (hourly resolution - there is no minute-resolution actual-
  power source anywhere in this system) narrowed to a ±90 min window via
  each `<Line>`'s own `data` prop (Recharts supports per-series `data`
  distinct from the parent chart's, so no merge into one unified row array
  was needed for this).

**Live-verified end to end via Playwright**, not just `vitest run`
(204/204, several new in `chartData.test.ts`/`timeScrub.test.ts`/
`ForecastPage.test.tsx`) and `tsc -b` (clean): booted a real `uvicorn`
(file-backed SQLite) and confirmed a fresh boot's `/performance/GIS`
already returned 72 backfilled `history` rows immediately (no cold-start
gap), then loaded the dashboard in a real browser and confirmed (a) the
legend and caption for all 3 tiers, (b) a hovered "before today" point's
tooltip correctly labeled and valued, (c) the indigo-vs-blue color clash
found and fixed as described above (screenshots before/after), (d) dark
mode, and (e) the Minute-ahead panel's backward window and actual-power
overlay rendering alongside its own forecast line and the main chart's
per-model error lines simultaneously with no visual collision.

### Added - guided Q&A categories for น้อง Solar + fixed the "can only ask once" chat bug (2026-07-18)

User report: "ถามน้อง Solar ได้แค่ 1 ครั้ง แล้วต้องปิดเปิด tab มาถามใหม่." Root
cause: `.assistant-panel` used a fixed `bottom: 140px` offset with no
awareness of a mobile on-screen keyboard - once the visual viewport shrinks
for the keyboard, that fixed offset can leave the input row (and the "ส่ง"
button) hidden behind the keyboard after the first answer, with no obvious
way back to it short of closing and reopening. Not reproducible on desktop
(confirmed: 3 questions in a row worked fine there), consistent with a
keyboard-covers-input failure mode.

- **Fix**: `AssistantPanel.tsx` now listens to `window.visualViewport`'s
  `resize`/`scroll` events while open and writes the current keyboard inset
  to a `--assistant-keyboard-inset` CSS custom property on the panel;
  `AssistantPanel.css`'s `bottom`/`max-height` both add that variable so the
  panel (and its input) rides up above the keyboard instead of behind it.

Separately, the user asked for a whole guided Q&A layer so a total
non-technical visitor ("คนธรรมดาโง่ๆ") can explore topics by tapping instead
of having to already know what to type, with keyword detection (e.g. typing
just "inverter" offers a menu of specific inverter questions instead of
guessing which one was meant):

- **`lib/assistantTopics.ts`** (new): the menu structure only - 3 top-level
  categories (`system` "ความรู้เรื่องระบบ Solar", `energy` "ความรู้เรื่องระบบ
  พลังงาน", `website` "การใช้เว็บไซต์นี้"), each with topic groups, each with
  concrete sub-questions. `findClarifyGroup(text)` matches a bare keyword to
  its group; `findCategoryById`/`findGroupById`/`findGroupBySubQuestionId`
  are the other lookups `AssistantPanel.tsx` needs for navigation.
- **`lib/assistantContent.ts`** (new): the actual answer text, keyed by
  sub-question id - kept in its own file specifically because this is the
  part expected to keep growing over many future sessions (per the user:
  "เราจะทำกันนานเลย คอย update plan อยู่ตลอด"). Adding a topic later is: one
  entry in `assistantTopics.ts` + one answer here, nothing else to touch.
  Current content covers system/design topics (Solar cell, panels, Inverter,
  Optimizer, Vdrop/Vrise, standards, marine corrosion resistance, mounting
  design - grounded in this project's real equipment from `config/
  assets.yaml`: Trina Vertex N TSM-NEG21C.20 715W modules, Huawei
  SUN2000-50KTL-M3 inverters, Huawei MERC-1300W-P 2:1 optimizers), energy
  topics (electricity billing, why solar matters, EF, Carbon Credit, Carbon
  Footprint, Net Zero), and one sub-question per dashboard page explaining
  what it's for in plain language.
- **`lib/assistant.ts`**: `TOPIC_INTENTS` generated from `TOPIC_CATEGORIES`
  (one `AssistantIntent` per sub-question) and appended to the existing
  hand-written intents. Matching changed from first-match-in-array to
  **longest-keyword-match-wins** (`bestMatchingIntent()`) - required because
  a menu button's full question text (e.g. "หน้า Forecast ในเว็บนี้ใช้ดูอะไร
  ได้บ้าง") can contain an existing short intent's bare keyword ('forecast')
  as a substring; without longest-match, clicking that button would
  incorrectly trigger a live forecast data fetch instead of the intended
  "how to use this page" explanation. New `AssistantReply.options` field
  (`AssistantOption[]`) attaches follow-up buttons to every reply: sibling
  sub-questions from the same group after a topic answer, the 3 top-level
  categories after any hand-written-intent answer or an unrecognized
  question (so a "sorry, didn't understand" never dead-ends), and a
  clarifying sub-menu when a bare keyword matches a group but no specific
  question.
- **`components/AssistantPanel.tsx`**: renders the last message's `options`
  as tappable chips (reusing the existing quick-reply button style);
  clicking a `question` option sends it through the normal pipeline exactly
  like typing it, while `category`/`group`/`categories` options are pure
  client-side menu navigation (no network round-trip). New 📚 header button
  reopens the top-level category menu at any point in the conversation.

**Tested**: `assistantTopics.test.ts` (new) guards the exact failure mode
this content will hit repeatedly as it grows - every sub-question has a
matching answer and vice versa, ids are unique, every answer stays in
character (ผม/ครับ). `assistant.test.ts` covers longest-match-wins,
clarify-menu-from-bare-keyword, sibling suggestions, and that fallback/error
paths still offer a next step. Full suite 218/218, `tsc` clean. **Live-
verified via Playwright** (light + dark, 420px mobile viewport): asked 3
questions back-to-back without closing the panel, typed the bare keyword
"inverter" and got the clarifying menu, drilled through 📚 → category →
group → sub-question, confirmed every answer plus its follow-up chips
rendered correctly with no layout collisions.

### Added - post-login profile gate, bigger chat/assistant panels, chat stickers with Thai TTS (2026-07-18, Track 2)

Three more user-requested changes to the visitor-network side, same session
as the guided Q&A work above:

- **`ChatProfileSetup.tsx`** (new): the name/avatar picker form extracted
  out of `VisitorNetwork.tsx` (was a private `ProfileSetup` function there)
  so it can be reused by a second call site. `VisitorNetwork.css`'s
  `.visitor-profile-*`/`.visitor-avatar-*` rules moved into a new
  self-contained `ChatProfileSetup.css` (renamed `.chat-profile-setup-*`) -
  no shared-class coupling between the two files.
- **`Layout.tsx`**: gained a `chatProfile` check that, if no profile is
  saved yet, renders `ChatProfileSetup` full-screen and returns early -
  nothing else in the authenticated app (nav, `<Outlet/>`, the mascot,
  everything) renders until it's saved. Per the user's explicit request:
  this used to only surface once someone happened to open the chat panel,
  which most visitors never did - now it happens right after login, before
  the dashboard is reachable at all. `VisitorNetwork.tsx` keeps its own
  fallback check unchanged as defense-in-depth (e.g. localStorage cleared
  mid-session).
- **Enlarged both floating panels** per direct feedback that they read as
  too small: `.visitor-panel` 320×460 → min(420, ...)×min(620, ...),
  `.assistant-panel` 340×480 → min(440, ...)×min(640, ...) (both still
  clamped to the viewport on small screens).
- **`lib/stickers.ts`** (new): a small catalog of original emoji+Thai-
  caption stickers (สวัสดี/ขอบคุณ/สู้ๆ/รักนะ/แย่จัง/ฮ่าๆ/ยินดีด้วย/โอเค) -
  deliberately not a reproduction of any licensed sticker set (the
  reference image the user shared was LINE's own copyrighted character
  art, which this project has no rights to redistribute). A sticker message
  is just a specially-prefixed string (`::sticker::<id>`) sent through the
  exact same `text` field/WebSocket path as a normal chat message - **no
  backend/schema change needed at all**, ws_chat.py stores/broadcasts it as
  opaque text same as always. `ChatBubble` in `VisitorNetwork.tsx` detects
  the prefix and renders a big emoji + caption instead of raw text;
  `useChatSocket.ts` gained an optional `onLiveMessage` callback that fires
  only for messages arriving via a live `message` event (never bulk
  `history` replay) - VisitorNetwork.tsx uses it to call `speakSticker()`
  (the browser's free, built-in `speechSynthesis` API, `lang: 'th-TH'`) so
  a sticker's caption is spoken aloud exactly once, right when it actually
  arrives, not replayed for every old sticker on every history load/scroll-
  back. Zero-cost, consistent with this project's no-paid-API rule - quality
  depends entirely on whatever Thai voice (if any) the visitor's own
  browser/OS ships, which client-side JS can't control or guarantee.
- The user also asked (as a question, not a request to build it yet)
  whether a *cloned* voice based on their own voice sample is something
  this project could do later - answered directly in chat, not implemented:
  real voice cloning needs either a paid third-party API (this project's
  standing zero-cost-API rule blocks that outright) or a self-hosted voice
  model, which is a much bigger undertaking (real audio samples, training/
  inference infrastructure, consent handling for cloning a real identifiable
  person's voice) than anything shipped so far - flagged as a distinct
  future decision for the user to weigh in on, not started.

**Tested**: `Layout.test.tsx` (new) covers the gate blocking/revealing the
dashboard and skipping entirely on a repeat visit; `stickers.test.ts` (new)
covers encode/decode round-tripping and `speakSticker`; `VisitorNetwork.
test.tsx` gained sticker-send, sticker-render, and history-vs-live-speech
tests. Full suite 228/228, `tsc` clean. **Live-verified via Playwright**
(light + dark): confirmed the dashboard is fully absent until the gate's
form is submitted, then appears with no reload; sent a sticker and
confirmed both the enlarged panel and the big-emoji-plus-caption rendering
(not raw `::sticker::` text); confirmed `speakSticker` fires exactly once
per live-arriving sticker (patched `SpeechSynthesis.prototype.speak` to
observe it, since the `window.speechSynthesis` accessor itself can't be
reassigned directly in a real browser - a test-script-only wrinkle, not an
app bug).

### Fixed - Model Competition chart rendering empty, x-axis now absolute time, bar value labels; 3D sun marker too small to read (2026-07-18, Track 1)

User report (screenshot): the "การแข่งขันของโมเดล (Model Competition) — Intra-
day, +1h ถึง +6h" panel rendered axis + legend but **zero visible bars**.
Also asked: change that panel's x-axis from relative "+1h".."+6h" labels to
absolute reference time, make the chart easier to read, recheck that it and
the Minute-ahead panel genuinely split by zone (All/GIS/ISB/Jetty) rather
than "showing the All view on every tab" as it looked live, recheck a report
of generated-power appearing at future timestamps on Intra-day, recheck why
Day-ahead sometimes doesn't reach the full 72h/3-day horizon, and fix the 3D
view's sun marker being "too small to make sense of."

**Root cause (empty Model Competition chart), found by fetching the live
`/forecast/{zone}/hour` response directly rather than guessing from the
screenshot**: `chartData.ts`'s `buildCompetitionRows()` filtered points with
`timestamp >= nowMs - 60 * 60 * 1000` - a 1-hour grace window that
contradicted its own docstring ("only points at/after `nowIso`"). An hour
that has *just* passed ages out of the live k-step forecast's forward
window and reverts to persisted-history defaults (`algorithm: null`,
`candidate_errors: {}` - see `forecast/serving.py`'s
`_persist_and_merge_history`) but still falls inside that 1h grace window,
so it sorted ahead of the real +1h..+6h race, got mislabeled "+1h" with
every candidate null (hence the empty first bar group), and bumped the
genuine +6h point out of `.slice(0, 6)` entirely. **Fix**: strict `>=
nowMs`, matching the docstring. New regression test in
`chartData.test.ts` constructs exactly this scenario (a point one hour
before `nowIso` with no candidate data, plus 6 real forward points) and
asserts all 6 rows come back real and correctly labeled +1h..+6h.

**X-axis + readability**: `ModelCompetitionPanel`'s `<XAxis>` now uses
`dataKey="timestamp"` with `formatDateHourIct` (same absolute-time
formatter every other chart on this page already uses) instead of
`leadLabel`, angled -30° so the longer date+hour ticks don't overlap; the
tooltip still shows the lead-hour offset (`row.leadLabel`) alongside the
formatted time. Added `<LabelList>` value labels on top of every bar (one
decimal place) so exact RMSE is readable without hovering. Chart height
220px -> 260px with a taller bottom margin to fit the angled labels.

**Zone-split**: not a bug - confirmed directly via `/forecast/GIS|ISB|Jetty/
hour`, `/forecast/.../day` that `pred`/`candidate_errors` genuinely differ
per zone, and confirmed live via Playwright that the Model Competition
panel's bars visibly change value when switching zone tabs post-fix. The
"looks stuck on All" impression was almost certainly the empty-chart bug
above making every tab look identically blank - nothing to distinguish
between tabs when all of them render nothing.

**Generated-power-at-future-timestamps**: not reproducible against current
code - `truncateGeneratedToNow()` (added 2026-07-17, reused by the 3-tier
refactor 2026-07-18) already nulls `actualPast`/`actualToday`/`actualNow`
for any row later than "now". Verified live across All/GIS/ISB/Jetty on
both Day-ahead and Intra-day: no actual-power point ever appears past the
current time. The user's screenshot showing a single purple "Generated
power" bar/legend (rather than the 3 recency-tiered lines) predates that
refactor, so it was almost certainly a stale screenshot or an unrefreshed
tab, not a live reproduction.

**Day-ahead not reaching the full 72h/3 days**: architecturally correct -
`serving.py`'s synthetic fallback path always produces exactly
`MAX_DAY_AHEAD_HOURS=72` future hours (confirmed live: 144 total points =
72 persisted-history + 72 future, when real future NWP data is thin enough
to trigger the fallback), and the real-data path
(`real_data.real_future_regressors`) has no artificial cap either - it
returns however many real future hours the live NWP poller
(`api/ingestion_scheduler.py`'s `_poll_nwp_forever`) has actually
accumulated, capped only by `[:MAX_DAY_AHEAD_HOURS]` from above, never
padded. So the *code path* supports 72h; how far it actually reaches live
depends on how much real future GFS data has accumulated, which can
legitimately be less than 72h (a specific far-out forecast hour's GRIB2
file simply not being published/reachable yet). Found one real, if
tangential, staleness bug while tracing this: `ingestion/nwp_ingestion`'s
own `Settings._default_forecast_hours()` (a *different* config class than
`api/config.py`'s `_default_nwp_poll_forecast_hours`, used by that package's
own separate-deploy path) was still capped at 48h with a comment claiming
day-ahead didn't need further - stale since day-ahead was extended to 72h;
brought in line with `api/config.py`'s already-72h-reaching list. This
doesn't change the *live* API's own poller (it already passed its own
72h-reaching list as a parameter, unaffected by this default), so it isn't
the root cause of a short-horizon day-ahead chart, just a real inconsistency
worth fixing for whoever relies on that package's own default next. No
further change made here - deliberately not building a real+padded-
synthetic hybrid Day-ahead without checking first; flagged to the user as
an optional follow-up instead.

**3D sun marker too small**: `Solar3DScene.tsx` used a fixed
`SUN_MARKER_RADIUS_M = 40` (orbit distance) and a fixed `sphereGeometry`
radius of 2m regardless of zone - fine for whichever scale it happened to
be tuned against, illegible at others (Jetty's sub-arrays are spread across
a ~1.25km trestle; ISB/GIS blocks are tens of meters). Fixed: orbit radius
now scales with the zone's own `bounds.focus.span` (`SUN_MARKER_RADIUS_
FLOOR_M = 40` kept only as a floor for small scenes), the sun ball's own
radius and a new semi-transparent glow-halo sphere both scale off that same
orbit radius (`SUN_RADIUS_FRACTION`/`SUN_GLOW_RADIUS_FRACTION`). Verified
live via Playwright + pixel-color scanning (`#fde047` in the rendered PNG):
at the *default* camera angle the sun marker is frequently just outside the
frustum entirely regardless of size (confirmed this is pre-existing, not
introduced here - the same angular math against the old fixed-40 value
lands just outside the frustum too, for the same sun position); rotating
the view (normal `OrbitControls` use, same as any user dragging to look
around) brings it clearly into frame with the new size/glow, unmistakably
legible where the old 2m ball was a barely-visible speck. Making the
*default* camera always include the current sun position (an auto-
following camera, touching the same position/target logic the "reset
camera" icon-rail button relies on) would be a materially bigger change -
not built here, flagged to the user as a separate possible follow-up.

**Tested**: `chartData.test.ts` - new regression test for the grace-window
fix, all 39 tests in that file passing. Full web suite 219/219, `tsc`
clean, `oxlint` clean. `ingestion/nwp` suite 41 passed/5 skipped after the
`_default_forecast_hours()` correction, `ruff check` clean. `api` suite 142
passed (unaffected, no api/ changes this round). **Live-verified** via a
local `uvicorn` + `vite dev` (not the deployed site - see root `CLAUDE.md`'s
Railway manual-deploy note): logged in as `pttlng` (viewer), screenshotted
Model Competition on GIS/ISB/Jetty (bars now render with distinct real
values and angled absolute-time labels on all three), screenshotted the
main chart confirming truncation, and screenshotted `/3d` for GIS/ISB/Jetty
including a rotated-camera shot showing the new sun marker clearly.

### Added - hide Simulation/Financial from viewer role (2026-07-18, Track 1)

Per the user's explicit instruction this round: originally scoped as a
Track 2 (UI/nav) task per the root `CLAUDE.md` two-track split and drafted
as a handoff prompt, but the user then said directly to just do it here and
tell Track 2 afterward so their own picture stays in sync (see this file's
own Handoff Report in `HANDOFF.md` for that note) - a one-time cross-track
exception per the user's own call, not a change to the standing policy.

- **`App.tsx`**: new exported `RequireOperator` component, same shape as
  the existing (unexported) `RequireAdmin` used for `/admin/feedback` -
  redirects to `/forecast` unless `role !== 'viewer'`. Wraps the
  `/simulation` and `/financial` routes, so a viewer can't reach either
  page by direct URL/bookmark, not just by clicking a hidden nav link.
  Mirrors access control the backend already enforces server-side
  (`require_role("operator")` on `POST /simulate/{zone}` and
  `POST /financial` - see `routes_simulate.py`/`routes_financial.py`) -
  this is a UX improvement (a viewer no longer lands on a page whose only
  actions already 403 for them), not a new security boundary.
- **`Layout.tsx`**: the Simulation/Financial `<NavLink>`s are now wrapped in
  `role !== 'viewer' &&`, same conditional-rendering shape as the existing
  admin-only Feedback link a few lines below.

**Tested**: `Layout.test.tsx` gained 3 tests (viewer sees neither link,
operator/admin see both). `App.test.tsx` gained 3 tests for `RequireOperator`
directly (viewer redirected to `/forecast`, operator/admin render the
guarded page) - `MemoryRouter` + a real `AuthProvider` seeded with a decoded-
role JWT, same harness shape `Layout.test.tsx` already used. Full suite
235/235, `tsc` clean, `oxlint` clean. **Live-verified** via local `uvicorn` +
`vite dev`: logged in as `pttlng` (viewer) - nav bar shows only Forecast/3D
View/Energy Report/Irradiance Map, and navigating straight to `/financial`
in the URL bar bounces back to `/forecast`; logged in as `admin` - both
links present and `/financial` loads normally.

### Added/Fixed - 3D View: sunrise default, ultra-smooth sun, cloud layer, irradiance/angle readouts (2026-07-18, Track 1)

A large batch of `/3d` (Solar3DPage/Solar3DScene) requests from one session,
including a screen recording showing the sun jumping in visible steps
rather than gliding:

**1. Control rail explained** (answered in chat, no code): the 5 icons are
Solar access view (color panels by output level) / String view (color by
electrical string) / Play-Pause (time-of-day animation) / Reset camera /
Grid-vs-satellite ground toggle. The top-right red-green bar is the Solar
Access Gauge; the dial readout is the sun Compass.

**2. Sunrise default + ultra-smooth animation** - two related fixes:

- `Solar3DPage.tsx` now defaults the time slider to the day's actual
  sunrise (`sunPath.data.points[0]` - `/sun-path` is already filtered to
  daylight only, `elevation_deg > 0`, so the first point *is* sunrise at
  15-minute resolution), re-defaulted once per `date` change, instead of a
  fixed placeholder hour.
- **Root cause of the laggy animation**: auto-play was a `setInterval`
  jumping `timeOfDayMinutes` by a fixed 15 minutes every 400ms - each tick
  re-triggered `useGeometry`'s network fetch and re-rendered the position
  from whatever that fetch returned, so the sun visibly teleported between
  snapshots rather than gliding. **Fix**: `Solar3DScene.tsx` gained a new
  `SunMarker` sub-component that animates entirely inside react-three-
  fiber's own `useFrame` render loop (imperative ref mutation, zero React
  re-renders per frame, zero extra network calls) - it linearly interpolates
  the sun's azimuth/elevation between the day's already-loaded 15-minute
  `sunPathPoints` samples (new `interpolateSunPosition()` in `lib/solar3d.ts`,
  returns `null` - not a clamped sunrise/sunset value - for an instant
  outside the covered daylight range, so a caller can't mistake "no data
  past sunset" for "the sun is still up"), true 60fps. A throttled
  (`onAnimatedTimeChange`, every 200ms, not every frame) callback bridges
  back to the page's own slider/readouts/panel-color fetch, which stays at
  its own coarser cadence deliberately - the visual glide and the data
  fetch rate are now fully decoupled.

**3. Prominent irradiance readout**: new card-styled `.solar3d-irradiance-card`
showing `GET /irradiance-map`'s `clearsky_ghi_w_m2` at the current scrubbed
instant (same value `IrradianceMapPage` already shows, so the two pages
agree) - previously not shown on this page at all.

**4. Simulated date/time caption + live angles + zone lat/lon**: a
`.solar3d-sim-clock` line ("กำลังจำลอง (Simulating) 18 กรกฎาคม 2569 - 07:00
น. (ICT)") mirrors ForecastPage's clock convention but for the *simulated*
instant, not real wall-clock time. New Zenith readout (`zenithAngleDeg()` =
90 - elevation, `lib/solar3d.ts`) next to the existing azimuth/elevation
Compass. New zone lat/lon readout using the selected zone's own real
surveyed centroid (`config/assets.yaml` via `/assets` - not the shared
nominal site location `/geometry`'s own sun-position calc uses; both are
shown, correctly attributed to what each actually is).

**5. Date-range scope + calendar picker**: the date `<input type="date">`
already opens a native calendar picker (no change needed there - confirmed,
not assumed). Added an honest scope caption instead of an arbitrary
min/max: the sun-path/shading simulation is pure astronomical calculation
(pvlib via `nongfab_features.clearsky`) valid for *any* date, but
Forecast/Actual readouts only have real data within `REAL_DATA_WINDOW_DAYS`
(3) of today - a warning line appears when the selected date falls outside
that window, rather than silently showing blank numbers with no
explanation.

**5 (continued) - panel color now blends actual + forecast**: `zoneOutputRatio`
(drives panel color-by-output in "Solar access" mode) previously used only
`actualAtScrub?.ac_kw`, which is `undefined` for any date/time outside
today (`/performance`'s `hourly` field only ever covers "today") - every
panel silently rendered as 0% output for a future scrub or any other date,
even though a real forecast number was already fetched and shown as text a
few lines above. Now falls back to `forecastAtScrub?.pred` whenever no
actual reading exists.

**5.1 - drifting cloud layer, from real data**: the user asked why every
panel seems to react to the sun in lockstep, and asked for real cloud data
(from the Thai Meteorological Department / Himawari feed this project
already ingests) shown as an animation. New `GET /weather/clouds` (see
`api/README.md`'s matching entry) exposes the latest real Himawari reading
- opacity % + motion vector - the same `cloud_history` table Module 4's
Sum-k LSTM cloud-index feature already reads. New `CloudLayer` component in
`Solar3DScene.tsx`: several overlapping soft spheres per "puff" (a cheap,
common cloud-silhouette technique), density from the real opacity %,
drifting via `useFrame` at a direction/speed derived from the real motion
vector, wrapping seamlessly within a field sized to each zone's own scene
scale. **Honesty caveat, kept explicit in the component's own docstring and
worth repeating here**: `cloud_history` only ever stores one site-wide
opacity scalar + a motion vector, not a spatial raster (the raw per-pixel
tile arrays live in MinIO, a separate heavier fetch not wired up here) - so
this shows "X% cloud cover, drifting this way" honestly; it does not claim
to show real cloud shapes or which specific panel is shaded at this
instant, since no data source in this app currently supports that claim.

**Found and fixed a real bug while building the cloud endpoint**: seeding a
manually-inserted cloud reading (`datetime.now()`, carrying microseconds)
alongside real rows (no microseconds) 500'd `GET /weather/clouds` -
`forecast/local_store.py`'s `cloud_history_df()` used
`pd.to_datetime(..., utc=True)` with no explicit `format=`, which infers
one fixed precision from the first row and rejects any other row that
doesn't match exactly (`nwp_history_df()` shared the same latent bug, fixed
alongside it). See `forecast/README.md`'s matching dated entry.

**Not built this round - real precipitation data doesn't exist anywhere in
this project yet** (checked directly: `ingestion/nwp` only ever extracts
SSRD/temp2m from the GFS GRIB2 files it fetches, never APCP, despite APCP
being present in the same raw index the project already pulls). Building a
"real rain animation" honestly would mean a new ingestion pipeline first
(most likely extending the existing GFS fetch to also decode APCP, the
smallest real path forward, rather than a wholly separate Thai
Meteorological Department integration) - not started without checking with
the user first, flagged as a live question instead of either silently
faking a seasonal-probability rain effect (violates this project's real-
data-or-honestly-labeled-estimate convention) or silently taking on a new
multi-day ingestion module unprompted. **Built later the same day - see the
next dated entry below.**

**Tested**: `lib/solar3d.ts` - `interpolateSunPosition()` (exact-sample,
midpoint interpolation, null before/after the covered range, empty/single-
point edge cases) and `zenithAngleDeg()`, `solar3d.test.ts`. `Solar3DPage.test.tsx`
gained tests for the sunrise default, the irradiance readout, zenith/lat-lon
readouts, the actual-to-forecast fallback, and the out-of-range date
warning. `api`'s `test_routes_weather.py` gained 4 tests for
`GET /weather/clouds`. `forecast`'s `test_local_store.py` gained a
regression test for the mixed-timestamp-precision bug. Full web suite
248/248, `tsc` clean, `oxlint` clean; `api` 146 passed; `forecast` 141
passed. **Live-verified** via local `uvicorn` + `vite dev`, a real seeded
cloud reading (confirmed the 500 before the `local_store.py` fix, and the
correct reading after it), and Playwright screenshots at sunrise (orange/
red panels, low irradiance, sun marker faint near the horizon) and midday
with the camera rotated to frame the sun (green panels, 925 W/m² clear-sky
GHI, the sun marker clearly visible with its glow, and the cloud layer -
several soft gray puffs partially over the panel rows, visibly drifted
between two screenshots taken a few seconds apart during Play) - zero
browser console errors/warnings across the whole run.

### Added - real rain animation for `/3d`, plus FusionSolar's priority-list status closed for good (2026-07-18, Track 1)

The user came back later the same day and explicitly greenlit the rain
feature the entry above had deliberately paused on ("เราจะเอาเรื่องฝนมาเป็น
อีกหนึ่งลูกเล่นของเว็บด้วย"), in the same message that also declared
FusionSolar access permanently unobtainable, not just pending ("ทิ้งไปเลย
ขอไม่ได้เเล้วจริงๆ") - see `forecast/README.md`'s matching dated entry for
that half (item 3 of the user's own priority list, real bias-correction
validation, is now permanently closed rather than blocked-pending).

Built the real path identified but not started in the entry above:
`ingestion/nwp` now decodes GFS's APCP field into `NWPForecastPoint.precip_mm`
(see `ingestion/nwp/README.md`'s matching entry for the full GRIB-decode
story, including a real duplicate-idx-entry GFS quirk caught live), stored
in a new `nwp_history.precip_mm` column (`forecast/README.md`'s entry), and
exposed via a new `GET /weather/precipitation` (`api/README.md`'s entry) -
the same "site-wide, near-term, `available: false` over a fabricated
reading" pattern `/weather/clouds` already established.

**Frontend**: new `RainLayer` component in `Solar3DScene.tsx`, same
"individual meshes, not InstancedMesh" style `CloudLayer` already uses -
falling particle count scales with the WMO intensity band from the API
(`light`/`moderate`/`heavy`, 60/120/200 particles), animated via `useFrame`
(each drop's own ref, y-position ticked down every frame and wrapped back
to the top) rather than React state, matching this file's existing
"animation lives inside r3f's own render loop" convention. Renders nothing
at all - not an empty group - when there's no real reading or intensity is
`"none"`, same honest-absence pattern as the cloud layer. **Deliberately
no snow effect** - the user was explicit Thailand has none
("ส่วนหิมะไทยไม่มีหิมะเเน่ๆไม่ต้องทำหิมะมานะ"), so this was never built, not an
oversight.

`Solar3DPage.tsx` gained `usePrecipitationConditions()` (new hook in
`lib/queries.ts`, same polling cadence as `useCloudConditions`) and threads
`precipMm`/`precipIntensity` down to the scene the same way cloud data
already flows through. No new text readout was added (matching how the
cloud layer also has none) - the 3D animation itself is the feature the
user asked for.

**Tested**: `nwp -v` 43 passed (5 skipped, live-network-gated, unrelated) -
`var_APCP` in the filter URL, `precip_mm is None` on the real APCP-less
fixture, the duplicate-idx-entry resolution, and both the success and
defensive-failure paths through the S3 backfill decode. `forecast -v` -
roundtrip, `None`-not-`0.0`, no-attribute tolerance, and the pre-existing-
table migration scenario. `api`'s `test_routes_weather.py` gained 6 tests
for `GET /weather/precipitation` (auth, empty store, no-row-carries-precip,
near-term-wins-over-far-future, and a parametrized intensity-band sweep) -
full suite green. `Solar3DPage.test.tsx` gained 2 tests (the live reading
reaches the scene; an unavailable reading passes through as `null`/`null`,
not a fabricated value) - full web suite green, `tsc` clean.

**Live-verified**: booted `uvicorn` + `vite dev`, logged in via
`/auth/token`, confirmed `GET /weather/precipitation` returned
`{"available": false, ...}` against an empty store, seeded a real
`precip_mm=6.2` row via `RealDataStore.insert_nwp_points`, confirmed the
endpoint then returned `{"available": true, "precip_mm": 6.2, "intensity":
"moderate"}`. Loaded `/3d` in a real browser (Playwright): the network
response carried the real seeded value through to the frontend (inspected
directly, not inferred), and the rendered scene showed clearly visible
falling rain streaks scattered across the panel view - confirmed both by
eye (screenshot) and by a pixel-diff between two frames 400ms apart during
Play (~93k of ~1.87M pixels changed, consistent with the animation still
running) - zero browser console errors/warnings.

### Added/Fixed - avatar picker bug, viewer-aware น้อง Solar content, Forecasting Q&A category (2026-07-18)

Re-surveyed the repo via `HANDOFF.md` before starting (per the user's
explicit instruction, since Track 1 had shipped several rounds of work -
Model Competition fixes, the viewer nav-hiding above, 3D sun sizing - since
this account's last turn). Confirmed the Simulation/Financial nav-hiding
the user described was already done by Track 1 directly (see the entry just
above this one) - not re-implemented here. Three separate fixes/additions:

- **Fixed the avatar picker**: (1) one avatar (`koala` 🐨 on a `#94A3B8`
  grey circle) rendered as an apparently-blank circle - the emoji's own
  grey/white fur tones sit too close to its own background color to read
  clearly, and it also sat next to `panda`'s similarly-grey circle, making
  both hard to tell apart. Replaced with `hamster` 🐹 on a warm, clearly-
  contrasting tan (`#D97706`) background (`lib/chatProfile.ts`). (2)
  `ChatProfileSetup.tsx` now shows the visitor's actually-selected avatar
  big in the preview slot the moment they pick one (or immediately when
  editing an existing profile) - it used to always show น้อง Solar's static
  mascot face regardless of what was picked, so there was no visual
  confirmation of your choice.
- **Made น้อง Solar's content viewer-aware**, since it was still advertising
  Simulation/Financial (operator-and-up only as of the entry above) as if
  every visitor could reach them: `LoginWelcome.tsx`'s feature-tour list no
  longer mentions either (that popup specifically hands out the public
  *viewer* login in the same breath, so it must only list what a viewer can
  actually open). `lib/assistant.ts`'s `AssistantContext` gained an optional
  `role` field; the `help_navigation` and `financial_info` intents now
  branch on `role === 'viewer'` - the page list drops those two bullets
  (with a one-line note explaining why, not just silently fewer pages), and
  asking about Financial tells a viewer plainly it's operator-and-up instead
  of walking them through a page they can't open. `assistantTopics.ts`
  gained a `viewerHidden` flag (set on the `page_simulation`/`page_financial`
  groups) and a `groupsForRole()` helper - `AssistantPanel.tsx`'s "การใช้
  เว็บนี้" category browser uses it so those two menu buttons don't even
  appear for a viewer. The underlying answers themselves also gained an
  access-restriction note, as defense-in-depth for anyone who reaches them
  a different way (e.g. typing the exact question text).
- **Added a 4th guided-Q&A category, "หลักการพยากรณ์การผลิตไฟ"** (📈), per
  the user's explicit request to explain how forecasting works, why 3
  horizons, which model per horizon and why, where data comes from, and
  more - with the sub-questions chosen by this account, not dictated. Two
  groups: "ภาพรวมระบบพยากรณ์" (how it works overall, why 3 horizons, which
  model per horizon + why, data sources) and "รายละเอียดเชิงลึก" (Model
  Competition, prediction interval reliability, physics-baseline fallback,
  retrain cadence, how accuracy is actually measured). Content is grounded
  in the real current forecast module - not invented - researched fresh
  from `forecast/README.md`, `api/README.md`, and recent `HANDOFF.md`/`web/
  README.md` entries: the real model names (CNN-LSTM for minute-ahead,
  LightGBM/Random Forest/Sum-k LSTM competing for hour-ahead, NeuralProphet
  for day-ahead), the real data sources (Himawari cloud imagery, GFS/NWP,
  PVGIS historical weather), and the same honesty this project keeps
  throughout - RMSE is currently measured against a physics-model estimate,
  not real SCADA telemetry, because none exists yet, and the guide says so
  plainly rather than implying otherwise.

**Tested**: `ChatProfileSetup.test.tsx` (new) covers the live-preview
swap behavior; `assistant.test.ts`/`assistantTopics.test.ts` gained
role-aware-answer tests and Forecasting-category tests (model names appear
in the "which model per horizon" answer, the accuracy answer stays honest
about physics-vs-telemetry, `groupsForRole` drops the right two groups for
viewer and nothing for anyone else). Full suite 249/249, `tsc` clean.
**Live-verified via Playwright**: picked the hamster avatar and confirmed
the live preview updates to show it; logged in as `pttlng` (viewer) and
confirmed the login-welcome feature list, the nav bar, the assistant's page-
listing answer, and the "การใช้เว็บนี้" category browser all agree in
excluding Simulation/Financial; browsed into the new Forecasting category
end-to-end (📚 → category → group → Model Competition question) and
confirmed the real answer renders with follow-up chips.

**Still outstanding, not done this turn**: merging the Irradiance Map and
3D View tabs into one - the user described this as already requested of
Track 2 (confirmed in `HANDOFF.md`: still unclaimed as of Track 1's last
entry) but the explicit numbered task list for this session's turn didn't
include it, so it wasn't started without confirming first.

### Added - "เล่นกับน้อง Solar" play interactions (2026-07-18)

A standalone playful feature the user asked to sit alongside the site's
engineering content as its own highlight: from right inside the AI
assistant panel (no separate tab/page), a 🎮 toggle reveals a dozen cute,
harmless things a visitor can do to the mascot - pet his head, poke his
cheek, hold hands, tickle him, rain on him, hug him, feed him ice cream,
cheer for him, jump-scare him, pinch his cheek, give him a flower, high-
five him. Each one gives น้อง Solar a distinct facial reaction plus a short
line of dialogue in a speech bubble next to the floating mascot, both
fading back to his default idle look ~5 seconds later.

- **`lib/useMascotReaction.ts`** (new): the shared `{ mood, speech,
  trigger() }` state AIAssistant.tsx now owns instead of a bare `useState`.
  The critical property, per the user's explicit request ("กดหลายๆ ครั้ง
  ห้าม stack นะ เช่นลูบหัว 10 ครั้ง ห้ามกลายเป็นรอ 50 วินาที"): `trigger()`
  imperatively clears and restarts its own timer on *every* call via a ref,
  not through a `useEffect(() => {...}, [mood])` dependency - the latter
  would silently fail to reset when the same mood/text repeats (React bails
  out of re-running an effect when setState is called with an unchanged
  value), which is exactly the case a rapid burst of identical clicks hits.
  Verified live: 6 rapid pet-head clicks 200ms apart still clear the bubble
  ~5.3s after the *last* click, not 30s later. This also fixed a latent
  version of the same bug in the pre-existing answer-driven happy/sad mood,
  which used to be a plain `useEffect`.
- **`components/MascotFace.tsx`**: `MascotMood` grew from 3 values (idle/
  happy/sad) to 10 - added blush, hurt, laugh, wet, love, surprised,
  excited. Built from small reusable pieces (`EYE_STYLE`/`MOUTH_PATH` lookup
  tables, an `EyePair` sub-component with 6 eye shapes: normal/closed/
  squint/wide/heart/star) rather than one-off SVG per mood, plus mood-
  specific decorations (floating hearts, falling raindrops, an impact
  burst, joy-tears, a motion burst) with their own CSS animations in
  `Mascot.css` (all included in the existing `prefers-reduced-motion`
  opt-out).
- **`lib/mascotInteractions.ts`** (new): the catalog of 12 interactions
  (id/label/mood/speech), kept deliberately generous rather than 2-3 token
  options per the user's explicit "ขอเยอะๆ เลยนะ".
- **`components/Mascot.tsx`**: gained a `speech` prop and a
  `.mascot-speech-bubble` rendered next to the floating character (not
  inside the chat panel) so the reaction is visible on the mascot itself.
  **Found and fixed a real layout bug live**: the bubble initially rendered
  only a few characters wide, wrapping "ขอบคุณค้าบบ~" across 4+ lines -
  root cause was `width` shrink-to-fit sizing against the wrong available
  width for an absolutely positioned element offset only by `right` (no
  `left`) inside a narrow (~108px, sized to the mascot button) positioned
  ancestor; fixed with `width: max-content` to force sizing purely off the
  bubble's own content.
- **`components/AssistantPanel.tsx`**: new 🎮 header toggle reveals
  `.assistant-play-panel`, a grid of interaction buttons styled like the
  existing sticker picker (`VisitorNetwork.tsx`) for visual consistency.
  Clicking an interaction calls `onInteract` (threaded from AIAssistant.tsx)
  - purely a mascot-side effect, never added as a chat message - and the
  panel deliberately stays open afterward so rapid repeated play never
  requires reopening it.

**Tested**: `useMascotReaction.test.ts` (new, fake timers) proves the no-
stack guarantee directly - 10 rapid identical triggers, a trigger arriving
while another is already pending, mood-only triggers with no bubble.
`mascotInteractions.test.ts` (new) guards catalog invariants (unique ids,
non-empty in-character speech, always a non-idle mood). `AIAssistant.
test.tsx` gained an integration suite covering the toggle, a real face
change + bubble text per interaction, that nothing is added to the chat
log, and that the panel stays open across repeated plays. Full suite
265/265, `tsc` clean. **Live-verified via Playwright** (light + dark):
screenshotted the play grid and 5 distinct mood reactions (blush/hurt/wet/
love/surprised), found and fixed the speech-bubble width bug above, then
proved the no-stack behavior with real elapsed-time measurements (6 rapid
clicks, bubble confirmed gone ~5.3s after the last one).

### Fixed/Added - 9-item bug/feature round: chart aggregation bugs, chart scrolling, 3D View + Irradiance Map merge, Moon, sun-angle diagram (2026-07-18, Track 1)

User report with 4 screenshots, 9 numbered items. Item 3 (merge Irradiance
Map into 3D View) was flagged in `HANDOFF.md` as "already requested of
Track 2" in a prior entry but is explicitly Track 1's own scope per root
`CLAUDE.md` (3D View is listed under Track 1, and Track 1 owns "whatever
frontend pages exist purely to present that content's data" - Irradiance
Map is exactly that), so it's done here rather than deferred again. Items 7
and 8 read as contradictory (7: Minute-ahead/Model Competition are missing
Actual-power lines; 8: don't show them on the Intra-day tab at all) - asked
the user via `AskUserQuestion`; they chose "fix the bugs, keep both panels
always-visible as before" (not relocate/hide).

**1 & 7 - Model Competition rendered nothing at all; Minute-ahead/Model
Competition were missing all 3 Actual-power lines.** Root cause, found by
comparing the live `/forecast/{zone}/hour` response against what the chart
actually rendered: `sumForecastAcrossZones`/`sumHourlyAcrossZones`/
`sumGeneratedPowerHistoryAcrossZones` in `chartData.ts` all required
`entry.n === perZone.length` (every zone must report the exact same hour)
before showing *any* row for that hour. Each zone's `/forecast/{zone}/hour`
(or `/performance/{zone}`) is a separate network call computing its own
"ceil to next hour" anchor server-side (`forecast/serving.py`'s
`_ceil_to`) - a request landing on the other side of an hour boundary from
the others silently blanked the *entire* summed chart, not just that
zone's contribution. Fixed by dropping the `n === perZone.length`
requirement: all 3 functions now return whatever they've accumulated,
summing partial zone coverage rather than hiding the row - "a partial sum
that's honestly labeled as coming from whichever zones reported" beats "a
blank chart with real underlying data." This alone explains both item 1
(the Model Competition panel summing `sumForecastAcrossZones`'s output)
and half of item 7 (the Minute-ahead panel's actual-power overlay reading
`sumHourlyAcrossZones`).

The other half of item 7 - a genuinely out-of-order x-axis (screenshot
showed ticks going ...20:00, 20:50, then jumping back to 19:00) - was a
Recharts footgun: a categorical `<XAxis>` builds its tick domain as the
union of every `<Line data=...>` series' own category values in
first-encountered order, not re-sorted by value. The Minute-ahead panel
rendered the forecast line and the (wider) actual-power line as two
separate `<Line data={...}>` series, so a timestamp only present in the
wider actual-power window landed at the *end* of the domain regardless of
its real time. Fixed with a new `mergeMinuteAheadRows(minutePoints,
actualRows)` (`chartData.ts`) that merges both sources into one
time-sorted array before rendering, matching the pattern the main chart's
own `mergeGeneratedAndForecast` already used - `MinuteAheadPanel` now reads
every `<Line>` off one shared `<LineChart data={rows}>` instead of
per-series `data` overrides.

**2 - Requested horizontal scroll on all 3 chart sections** ("เลื่อนได้
พอประมาณเพื่อไปดูอดีตที่ผ่านมา และอนาคตนิดหน่อยตามความสามารถโมเดลนั้นๆ" -
scroll enough to see some history and a bit of future, per that model's own
capability). Rather than building windowing/pagination, each chart's
already-fetched data now renders at a real pixel width proportional to its
point count (`scrollableChartWidthPx(pointCount, pxPerPoint)`, floored at
`CHART_MIN_WIDTH_PX = 600`) inside a `overflow-x: auto` wrapper
(`.forecast-chart-scroll`) - panning is native browser scroll over content
that's honestly present, not fabricated. Model Competition's own wrapper
uses a deliberately high `pxPerPoint = 100` since its 6-bar (+1h..+6h) cap
*is* that model's real capability boundary, not a bug - "little to scroll
into" there is correct behavior, matching the user's own "ตามความสามารถ
โมเดลนั้นๆ" wording.

**3 - Merged Irradiance Map into 3D View** (`ดึง irradiance map มารวมกับ
3d view แล้วมาทำให้เด่น`) rather than just linking the two pages.
`Solar3DPage.tsx` already had `useIrradianceMap(atIso)` wired in from an
earlier round (only used for a small GHI readout card) - the merge reuses
that *same* query result to also render the full `<IrradianceMapView>`
MapLibre heatmap in a new `.solar3d-irradiance-map-section`, with its own
3 layer toggles (irradiance overlay / zone pins / zone boundary, defaults
matching the old standalone page) - no new network call. Deleted
`IrradianceMapPage.tsx`/`.css`/its test file and the nav bar's separate
"Irradiance Map" link; the old `/irradiance-map` route now
`<Navigate to="/3d" replace />` instead of falling through to the generic
404 catch-all, so old bookmarks still land somewhere real.

**4 - Added a Moon** that rises to replace the Sun once it sets, moving
just as smoothly as the Sun already does. Backend: see `features/README.md`'s
and `api/README.md`'s matching dated entries for the lunar-position math
and the new `/moon-path/{zone}` endpoint. Frontend, `Solar3DScene.tsx`:

- **`MoonMarker`** mirrors `SunMarker`'s own "imperative `useFrame` clock,
  no React re-render per frame" structure, but reads off `moonPathPoints`
  (the full unfiltered 24h day, unlike the Sun's daylight-only
  `sunPathPoints`) via the same `interpolateSunPosition` helper (generic
  over any `{time, azimuth_deg, elevation_deg}[]`, reused as-is rather than
  writing a near-duplicate). Visible only when *both* the Moon's own
  elevation is genuinely positive *and* the Sun's is genuinely non-positive
  (`interpolateSunPosition(sunPathPoints, ...)` returning `null` already
  means "sun is down", since `sunPathPoints` only ever covers daylight) -
  a deliberate "one or the other, not both" scene convention matching the
  literal request ("replace the sun"), not a claim that the real sun and
  moon are never in the sky together.
- **Found and fixed a real design gap while wiring this up**: `SunMarker`'s
  own Play-mode animation clock only ever looped within `sunPathPoints`'
  daylight-only span (wrapping straight from sunset back to sunrise) - by
  design, before the Moon existed, since there was nothing to show at
  night. Left as-is, the Moon would never appear during Play at all. Fixed
  by extracting the wrap-around arithmetic into a new pure, unit-tested
  helper, `advanceSimClockMs(currentMs, deltaSeconds,
  simMinutesPerRealSecond, wrapStartMs, wrapEndMs)` (`lib/solar3d.ts`), and
  widening both `SunMarker`'s and `MoonMarker`'s wrap window from the Sun's
  daylight-only span to the Moon's own full-24h `moonPathPoints` span - both
  markers now share the exact same wrap bounds and per-frame `delta`, so
  they advance in provable lockstep (covered directly by a unit test, since
  `useFrame` itself isn't testable in jsdom).
- A thin pale-blue-white path line (`moonPathLine`, filtered to the
  above-horizon stretch only, matching the Sun's own line's source data)
  traces the Moon's arc the same way the amber Sun-path line already does.

**5 - Azimuth/altitude/zenith-angle diagram, Sun only** (explicitly not the
Moon, per the user's own instruction). Two parts:
- **Explicit labeled text readouts**: the existing `Compass` component
  already showed a numeric azimuth ("288° W") and a small "Alt: -17°", but
  neither was labeled with the word "Azimuth"/"Altitude" the way the
  existing Zenith readout was - read as "missing" to the user even though
  the number was technically there. `Solar3DPage.tsx` now shows explicit
  "Azimuth"/"Altitude"/"Zenith" readouts side by side, same styling.
- **In-scene 3D angle-measurement protractor** (the "สำคัญมาก" part):
  new `SunAngleDiagram` component in `Solar3DScene.tsx`, matching the
  standard solar-position diagram convention (e.g. Duffie & Beckman's
  *Solar Engineering of Thermal Processes*) - a cyan ground-plane arc from
  North to the Sun's azimuth bearing, a green vertical-plane arc from the
  horizon up to the Sun (altitude), and a violet vertical-plane arc from
  directly overhead down to the Sun (zenith angle, complementary to
  altitude - they always sum to 90° and share the Sun as one endpoint),
  plus 4 subtle reference rays (North, zenith, the Sun's ground projection,
  the Sun itself) anchoring the arcs, and 3 `<Html>`-rendered degree labels
  (real DOM text anchored to a 3D point, via `@react-three/drei`, not
  canvas-drawn text). New pure helper `angleArcPoints(azFromDeg, azToDeg,
  elFromDeg, elToDeg, radius, segments)` (`lib/solar3d.ts`) generates each
  arc's point array, linearly sweeping az/el together - a plain sweep, not
  a true spherical geodesic, indistinguishable at the ≤90° sweeps these
  diagrams use. Deliberately prop-driven (not a `useFrame` clock like
  SunMarker/MoonMarker) - it updates at the same cadence as every other
  non-animated scene element (panels, buildings), and hides entirely below
  the horizon, since an angle-to-the-sun diagram for a sun that isn't up
  doesn't mean anything.

**6 - "Actual power (before today)" looked identical to "Forecast" for the
same hour.** See `forecast/README.md`'s and `api/README.md`'s matching
dated entries for the root cause (both backfill paths call the identical
physics-baseline estimator) and the new provenance marker. Frontend half:
`ChartRow` gained an `actualEstimated: boolean` field, carried through
`mergeGeneratedAndForecast()`; `sumGeneratedPowerHistoryAcrossZones` ORs it
across zones (any estimated component marks the whole summed row
estimated). The main chart's tooltip now appends " (estimated)" to the 3
actual-power series names for a row where `actualEstimated` is true
(`actualPowerTooltipName()`), so a backfilled physics approximation reads
honestly instead of implying confirmed telemetry.

**9 - Split the 3 RMSE error lines into their own chart.** They previously
rendered as 3 additional `<Line>`s on the main Intra-day chart, competing
visually with the power/forecast lines the user actually cares about most.
New `ErrorChartPanel` component (gated the same way the old inline lines
were - `horizonToggle === 'hour'` only), same horizontal-scroll treatment
as item 2's other charts; the 3 error `<Line>`s were removed from the main
chart entirely, not duplicated.

**Tested**: `chartData.test.ts` - the 3 "drops X not reported by every
zone" tests rewritten to "keeps X reported by only some zones, summing
whatever is there", new `describe('mergeMinuteAheadRows', ...)` (3 tests,
including a regression test for the exact out-of-order-x-axis scenario),
new `estimated`-flag propagation tests. `solar3d.test.ts` - 5 new tests for
`advanceSimClockMs` (including the lockstep-across-two-markers case) and 5
for `angleArcPoints`. `Solar3DPage.test.tsx`/`Layout.test.tsx` gained tests
for the merged irradiance map section, its layer toggles, and the removed
nav entry. `ForecastPage.test.tsx` gained tests for the new error-chart
panel's Day-ahead/Intra-day visibility gating. Full web suite 294/294,
`tsc -p tsconfig.app.json` clean.

**Live-verified via Playwright** (local `uvicorn` + `vite dev`, see root
`CLAUDE.md`'s Railway manual-deploy note - `api/routes_performance.py` and
`api/routes_solar3d.py` both changed this round): Model Competition went
from 0 visible bars to 18 real bars across zones; Minute-ahead panel showed
real actual-power dots with a genuine "Actual power (earlier today): 83.4"
tooltip and correctly time-ordered x-axis ticks; `/3d` screenshot confirmed
the merged Irradiance Map section (MapLibre canvas, real zone pins,
working layer toggles, color legend) with zero console errors and the old
`/irradiance-map` URL redirecting correctly; scrubbed to a real
night-instant on 2026-07-18 (confirmed via direct `/sun-path`/`/moon-path`
curl calls first) and screenshotted the Moon rendering with its glow and
path line while the Sun readout showed `Alt: -17°`/`Night - no
irradiance`, then confirmed continued smooth motion across two Play-mode
frames 3s apart; scrubbed to a real daylight instant and confirmed the
Azimuth/Altitude/Zenith text readouts (`288°`/`51°`/`39°`) and all 3
in-scene protractor labels (queried directly from the DOM: `"Azimuth 288°"`,
`"Altitude 51°"`, `"Zenith 39°"`) matched. Zero browser console errors
across every screenshot.

### Fixed - visitor chat rebuilt as private 1:1 messaging, not a public room (2026-07-18, Track 2)

The user flagged, in strong terms, that the previous chat was a real
privacy bug: it broadcast every message to every connected visitor
("openchat" style) with no way to pick who you were talking to -
"ต้องทำเพราะมันจำเป็น" (must fix, it's necessary), twice, across two
separate messages. Client-side filtering would not have actually fixed
this (every browser would still receive every message over the wire), so
this is a genuine server-side routing change - see `ws_chat.py`'s module
docstring on the API side.

- **`lib/useChatSocket.ts`** (rewritten): no more single flat `messages`/
  `onlineCount`. Now exposes `contacts` (who you can start/resume a
  conversation with - online visitors from the server's `online_users`
  push, plus previously-chatted people who've since gone offline,
  remembered locally so a conversation doesn't vanish from the list just
  because the other person closed their tab) and `conversations` (messages/
  unread/pagination keyed by peer `client_id`). `openConversation(peerId)`
  fetches that pair's history via `GET /chat/history?my_client_id=&peer_
  client_id=`; `sendMessage(peerId, text)` addresses the WS payload with
  `recipient_client_id`. There is no more bulk `history` WS push on connect
  - only `online_users` and per-recipient `message` events.
- **`components/VisitorNetwork.tsx`**: the chat tab now defaults to a
  contact list (`ContactRow` per visitor, 🟢ออนไลน์/ออฟไลน์ status, per-
  contact unread badge) - clicking someone opens a `ThreadView` (back
  button, scoped message list/input/stickers, `key={peerClientId}` so
  switching threads resets scroll state cleanly). The toggle button's
  unread badge is now a sum across every open conversation.
- **`types.ts`**/**`api.ts`**: `ChatMessage` gained `recipient_client_id`;
  `ChatPresence`/`ChatHistory` replaced by `OnlineUser`/`ChatOnlineUsers`;
  `chatSocketUrl()` now sends `client_id`/`display_name`/`avatar` as
  connect-time query params (the server needs identity before any message
  is ever sent, to populate the online list); `getChatHistory()` now takes
  both ends of the pair.

Also answers the user's other two questions this same message raised: (1)
avatar/name persistence across a re-login on the same browser was already
true before this change (`chatProfile.ts`'s `localStorage`-based profile is
independent of the JWT/login state) and still is - verified live below,
along with the existing "✏️ edit profile" flow still working, now synced
live to what other people see via a `type: "update_profile"` WS message
instead of requiring a reconnect.

**Tested**: `useChatSocket.test.tsx` and `VisitorNetwork.test.tsx` fully
rewritten (12 + 15 tests) for the new contact-list/thread model, including
a component-level proof that a message from one peer never renders inside
a different peer's thread. Full suite 284/284, `tsc` clean. **Live-
verified via Playwright** with three real signed-in visitors (viewer/
operator/admin, each through the real login + post-login profile gate):
the contact list showed the other two online (admin's name correctly
prefixed "admin "); a private message from one to another arrived only for
its recipient - the third visitor's page never showed it, live-proving the
same privacy property the old public room violated; a reply flowed back;
and reloading the sender's page kept its saved name/avatar with no
re-prompt, with the edit-profile button still present and working.

### Fixed - dark-theme logo white boxes, mobile page overflow, site renamed (2026-07-18)

- **`public/logos/pe-lng.png` / `chula-university.png`**: both had a baked-
  in opaque white background (not real transparency), showing as a visible
  white rectangle in dark mode. Chroma-keyed to genuine transparency
  (flood-fill from the border on near-white pixels + a slight Gaussian
  blur on the resulting alpha for a clean edge, not a naive global-
  threshold key - an earlier attempt at that left visible grey speckle
  noise from the source PNGs' own compression fuzz). Verified pixel-
  identical to the original when composited back onto a white background,
  and clean (no white box, no speckling) composited onto the dark theme's
  `--bg`.
- **Site renamed** "Nong Fab Solar EMS" → "PTT LNG Terminal 2 Nong Fab
  Solar Forecasting" everywhere it's visible: `Login.tsx`'s `<h1>` (own
  smaller font-size, now 26px not 34px, to fit the longer name inside
  `.login-form`'s 460px width), `Layout.tsx`'s header brand, `index.html`'s
  `<title>`, `OrgLogos.tsx`'s site-logo alt text. Left the site-logo.svg
  mark's own embedded wordmark artwork untouched (a bigger redesign task on
  its own, not requested).
- **Fixed a second, previously-undiagnosed cause of the same "mascot
  invisible until you pinch-zoom out on mobile" bug** (`App.css`'s header
  wrap fix above resolved the first cause): `OrgLogos.css`'s
  `.org-logos-footer` combines `width: 100%` with left/right padding under
  the CSS default *content-box* sizing, which computes total rendered
  width as 100% of the parent **plus** the padding - exactly the 40px
  overflow measured live. Added a universal `*, *::before, *::after {
  box-sizing: border-box }` reset to `index.css` (defense in depth against
  this whole bug class recurring anywhere else, not just this one
  component) rather than patching just this one selector.
- **`ForecastPage.tsx`**'s collapsible "Forecast models used here" table
  (4 columns of real prose) also doesn't fit a narrow phone - wrapped it in
  a new `.model-info-table-scroll` div with its own `overflow-x: auto`
  (same principle as `VisitorNetwork.css`'s chat scroll containers).
  **Caught and reverted a self-introduced regression before shipping it**:
  the first attempt put `display: block` directly on `.model-info-table`
  to make `overflow-x` actually take effect (a `<table>`'s native `display:
  table` doesn't reliably respect `overflow` cross-browser) - but that
  author-stylesheet rule overrode the browser's native `details:not([open])
  > *:not(summary) { display: none }` collapse behavior, so the table
  stayed laid out (and overflowing) even while the panel was visually
  closed. Moving `overflow-x: auto` onto a dedicated wrapper `<div>`
  instead - leaving the `<table>` element itself untouched - fixed the
  overflow without fighting `<details>`'s own collapse mechanism.

**Tested**: `App.test.tsx`, `Layout.test.tsx`, `OrgLogos.test.tsx` updated
for the new brand text. Full suite 289/289, `tsc` clean. **Live-verified
via Playwright**: composited both logos onto light/dark backgrounds before
touching the real files; screenshotted the real login page in both color
schemes (logos clean, title wraps to 2 lines and reads correctly); at a
375px mobile viewport, walked through login → post-login profile gate →
dashboard and confirmed `document.body.scrollWidth` now exactly equals
`window.innerWidth` (was 415 vs 375 before the box-sizing fix) - the
mascot and chat toggle are visible in the initial viewport with no zoom
needed, and the collapsed model-info table stays genuinely hidden (visible
screenshot: just the collapsed "▶" summary rows, no leaked table content).

### Added - subtle solar-system decoration on the login screen (2026-07-18)

The user asked for the empty left/right margins on a wide login screen to
be decorated in a solar-system theme, explicitly "ทำพอดีๆ" (tastefully, not
cluttered) - so this is deliberately restrained: `LoginSolarDecor.tsx`
renders a small glowing sun + two thin orbit rings (one small dot each,
`--accent` purple and a light blue) per side, plus 3 faint twinkling stars,
all `aria-hidden`/`pointer-events: none` (carries no information) at ~40%
opacity so it never competes with the actual sign-in form. `position:
fixed` at `z-index: -1` so it can never sit above the form or the
`LoginWelcome` modal regardless of DOM order. Orbits rotate slowly (34s/
64s, opposite directions) via CSS `@keyframes`, respecting
`prefers-reduced-motion`. Hidden entirely below a 1020px viewport - no
spare margin to decorate there, and it must never become a third source of
the mobile horizontal-overflow bug fixed just above in this same entry.

**Tested**: `LoginSolarDecor.test.tsx` (new) - renders without crashing,
`aria-hidden`, no interactive elements. Full suite 290/290, `tsc` clean.
**Live-verified via Playwright** at a 1600px viewport in both color
schemes (screenshots) and confirmed `display: none` actually applies at
900px width (below the breakpoint).

### Added - a voice for น้อง Solar (2026-07-18)

The user asked to give the AI assistant a voice, and after presenting
options (via `AskUserQuestion` - dynamic TTS of every real reply vs. only
pre-scripted phrases; auto-speak vs. a manual button) picked: **speak
every dynamic reply, triggered by a per-message button** (not auto-play).

- **`lib/tts.ts`** (new): extracted `speakText(text)` - the same
  zero-cost, no-API-key `window.speechSynthesis` mechanism the sticker
  system already used, now shared. Calls `synth.cancel()` before every
  `synth.speak()` so rapid repeated clicks can never queue up a stacking
  backlog of utterances - same no-stack principle as this session's other
  rapid-click fixes (`useMascotReaction.ts`, the AssistantPanel category
  menu above). `stickers.ts`'s `speakSticker()` now just calls this.
- **`AssistantPanel.tsx`**: every assistant reply (not the visitor's own
  echoed messages) gets a small 🔊 button under its bubble
  (`aria-label="ฟังเสียงข้อความนี้"`) that speaks that exact reply text
  aloud on click.

Quality depends entirely on whichever Thai system voice (if any) the
visitor's own browser/OS ships - same honest caveat as the existing
sticker TTS, since there's no way to guarantee a specific voice from
client-side JS without a paid TTS API (out of scope per this project's
zero-cost rule).

**Tested**: `tts.test.ts` (new) covers speaking, the cancel-before-speak
no-stack behavior, and the no-`speechSynthesis` no-op case.
`AIAssistant.test.tsx` gained tests for the button appearing on every
assistant reply (not the user's own), and that clicking it calls
`speechSynthesis.speak` with `lang: "th-TH"`. Full suite 295/295, `tsc`
clean. **Live-verified via Playwright**: opened the assistant panel and
confirmed the 🔊 button renders under the greeting bubble.

### Fixed - `npm run build` failing in CI, the actual reason Cloudflare had zero of today's commits live (2026-07-18, Track 2)

The user reported the live site (Cloudflare) still showed old branding/bugs
despite many commits pushed today, and separately asked to check GitHub
Actions for anything failing on the way into the API. Checking the CI run
for the most recent commit (`Auto-migrate chat_messages...`) found **every
CI run since early today has been red**, and one of the three failing jobs
is this package's own `lint+test+build - web/` job: `tsc -b` failed on
`src/lib/__tests__/useChatSocket.test.tsx(162,30)` with `Type 'string' is
not assignable to type 'null'`. Root cause: `renderHook(..., {
initialProps: { active: false, peer: null } })` let TypeScript infer
`peer`'s type from the literal `null` instead of the callback param's own
`string | null` annotation, so the later `rerender({ ..., peer: PEER })`
(a real string) failed to typecheck. Fixed by annotating the literal:
`peer: null as string | null`.

Cloudflare Pages builds from `npm run build` on push - with that step
throwing on every commit today, there was never a successful build to
deploy, which is why the live site stayed frozen on old code all day
regardless of how many commits landed. This was not a Cloudflare
configuration problem at all.

While in the same CI run, also fixed two more trivial lint-only failures
blocking the same run (flagged here since they're outside this package,
not touched otherwise this session): `api/tests/test_ingestion_scheduler.py`
had an unsorted import block (`ruff check --fix`), and
`forecast/tests/test_local_store.py` had two lines over the 150-char limit
(wrapped the `record_forecast_points(...)` calls across multiple lines).

**Tested**: `tsc -b` clean, full web suite 295/295, `npm run build`
succeeds locally. `ruff check` clean on both other files; their own test
suites still pass (28/28 combined). Once this lands on `main`/the working
branch and Cloudflare's next build runs, today's actual UI changes should
finally go live.

### Added - Energy Report: full Thai month names + Thai loss-breakdown labels (2026-07-18, Track 1)

Per the user's own request: `EnergyReportPage.tsx`'s Monthly generation
chart used single-letter English month labels (`J`, `F`, `M`, ...); replaced
with `MONTH_LABELS`, the 12 full Thai month names (`มกราคม`, `กุมภาพันธ์`,
... `ธันวาคม`). The Losses breakdown section's component labels
(`temperature_pct`, `soiling_pct`, etc.) were English keys shown almost
verbatim; `LOSS_LABELS` now maps each to a Thai description (`อุณหภูมิ`,
`ฝุ่น/คราบสกปรกบนแผง`, `เงาบัง`, ...). Neither change touches the underlying
numeric values - both are still the same PVWatts-literature defaults
documented in `simulation/README.md`'s "Loss model assumptions" section
(see that file's own 2026-07-18 entry for the accompanying Thailand/marine
literature search this same request prompted).

**Tested**: `EnergyReportPage.test.tsx`'s losses-breakdown test updated to
assert the new Thai labels (`อุณหภูมิ`, `ฝุ่น/คราบสกปรกบนแผง`) instead of the
old English ones; all 7 tests in the file pass.

### Added/Fixed - Forecast scroll centering + dashed lines, sun-angle diagram reaching the sun, Irradiance Map merged into the 3D scene, 9-variable Songsiri table + grouped graphs (2026-07-19, Track 1)

A large follow-up round, mostly reacting to the user's own report that
several items from the *previous* 9-item round (2026-07-18, see above)
weren't actually satisfying what was asked, plus new requests confirmed via
`AskUserQuestion` earlier in the same session.

**Forecast chart scroll now defaults centered on "now", not the left edge.**
The earlier native-overflow-scroll implementation technically panned, but
always opened scrolled all the way left (oldest data), so "now" - the whole
point of scrolling - started off-screen, and the native scrollbar itself was
easy to miss (auto-hiding on trackpad/touch). Fixed with a new
`useCenterChartOnce` hook (`ForecastPage.tsx`) that finds the row nearest
"now" (`indexNearestToTimestamp`, new in `chartData.ts`) and sets the
scroll container's `scrollLeft` to center it - once per zone/horizon combo,
so it doesn't fight a viewer who's since panned elsewhere. Also added a
`ScrollHint` caption above each scrollable chart and made the scrollbar
itself always-visible/styled (`scrollbar-width`/`::-webkit-scrollbar`
rules in `ForecastPage.css`) instead of relying on the OS's own hidden
scrollbar.

**Overlapping chart lines now use dashed/dotted strokes, not just color.**
The main chart's "Forecast" line and the Minute-ahead panel's forecast line
both got `strokeDasharray` (dashed) so they read apart from the solid
actual-power lines even where they cross closely. The 3 per-model RMSE
error lines (previously all the same `"4 4"` dash) now use 3 distinct
patterns (dash / dot / dash-dot) so two close-together model error lines
stay tellable apart by shape, not just hue.

**`SunAngleDiagram`'s azimuth/altitude/zenith arcs now reach the actual sun
marker**, not a small fixed-radius protractor near the scene origin -
`ANGLE_DIAGRAM_RADIUS_FRACTION` (`Solar3DScene.tsx`) changed from 0.3 to
1.0 (the sun's own orbit radius), so every reference ray and arc literally
terminates at the sun's rendered position. Per the user's explicit
follow-up that the earlier round's compact protractor "wasn't reaching the
sun."

**Irradiance Map merged a second time - now literally INTO the 3D scene**,
not just onto the same page. The earlier round already pulled the separate
MapLibre page onto `/3d`, but as its own section below the canvas; this
round replaces that with a new `IrradianceGroundOverlay` component
(`Solar3DScene.tsx`) that renders the plant-wide irradiance grid
(GET `/irradiance-map`'s `grid`) as colored circles directly on the WebGL
ground plane, using the same 4-stop blue→amber→red ramp the old MapLibre
layer used (`irradianceGhiColor`, new in `lib/solar3d.ts`). Each grid
point's real (lat, lon) is projected into the currently-viewed zone's own
local (east, north) meter frame via a new `latLonToLocalMeters` function -
anchored at the SAME centroid `nongfab_features.panel_geometry` already
uses as a zone's local origin, so a grid point and a panel share one
coordinate system with no extra conversion. `IrradianceMapView.tsx` (the
MapLibre component) and the `maplibre-gl` dependency were deleted entirely
- nothing else used them. `Solar3DPage.tsx`'s 3 old layer-toggle checkboxes
(overlay/zone-pins/boundary) collapsed to one ("Irradiance ground overlay")
plus a small legend, since zone pins/boundary added nothing a single-zone
3D view didn't already show (centroid lat/lon readout, panels' own real
footprint).

**New 3x3 live variable table + grouped graphs for all 9 Jitkomut Songsiri
reference-deck input variables** (I, RH, T, UV, WS, I_clr, cosθ, k̂, I_wrf) -
per the user's own confirmed design ("ทำครบ 9 ตัว ระบุ UV เป็นรายวัน" / "เห็นด้วยตามที่เสนอ"
grouping) from the same session's earlier `AskUserQuestion` round. Backend
work (`GET /weather/conditions`, extended `GET /weather/strip`) was already
built in that earlier round; this round is purely the frontend:
- `SolarVariablesTable` (`ForecastPage.tsx`) - a live 3x3 grid reading the
  same order as the Songsiri reference image, backed by `useCurrentConditions()`.
- `SolarVariablesGraphs` - grouped time-series charts: the irradiance trio
  (I/I_clr/I_wrf) share one chart, k̂+cosθ share one chart (comparable
  0-1-ish scale), T/RH/WS each get their own. **UV gets no chart at all** -
  NASA POWER is daily-cadence only, never a time series anywhere in this
  system, and the user was explicit that a variable with no real time
  series should never have one faked to fill a slot - it gets an honest
  caption instead, pointing back at the table above.
- The irradiance chart's own honesty split: `buildIrradianceRows` puts
  past/now points in `iActual` and future points in `iForecast` (I_wrf)
  ONLY when the underlying `/weather/strip` response is `data_source:
  "real"` - in `"synthetic"` mode every point goes into a third
  `iSynthetic` field instead, specifically so a physics-baseline fallback
  curve never gets mislabeled as either a real reading or a real NWP
  forecast (a direct instance of the user's own "don't fake a forecast
  that doesn't exist" instruction). RH/WS charts render a "no data"
  caption instead of an empty chart when the strip has no real coverage
  (synthetic mode never models humidity/wind).
- New CSS chart-color variables (`--chart-irradiance`, `--chart-clearsky`,
  `--chart-temp`, `--chart-rh`, `--chart-wind`, `--chart-cosz`,
  `--chart-khat`) in `index.css`, picked to stay visually distinct from
  every hue this page's other charts already use.

**Tested**: 320/320 frontend tests passing (35 files, up from 309), `tsc -b`
clean, `oxlint` clean (2 pre-existing Track 2 warnings, untouched).
New/updated tests: `lib/__tests__/solar3d.test.ts` (`latLonToLocalMeters`,
`irradianceGhiColor`), `pages/__tests__/Solar3DPage.test.tsx` (irradiance
grid piped into the mocked scene, single overlay toggle), `pages/__tests__/
ForecastPage.test.tsx` (9-variable table live values + UV-unavailable
placeholder, grouped-graphs subsections, RH/WS "no data" fallback caption
in synthetic mode). Backend: full `api` suite re-run clean (174 passed,
unchanged from the earlier round that built `/weather/conditions`/extended
`/weather/strip` - no backend code touched this round). **Verified live**:
booted a real `uvicorn` (fresh file-backed SQLite, short-lived so ingestion
had little real data - `data_source: synthetic` for most of this check) +
`vite dev` pair, headless Chromium, logged in as `admin`, screenshotted
`/forecast` (9-variable table + grouped graphs rendering with correct
synthetic-fallback captions, no fabricated I_wrf/RH/WS) and `/3d` (irradiance
overlay toggle + legend rendering, no console errors; the sun-angle
diagram's cyan azimuth arc and yellow sun-ray visibly now reach all the
way to the sun marker, confirming the `ANGLE_DIAGRAM_RADIUS_FRACTION` fix).

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

### Fixed - AI assistant menu stacking, take two: bouncing between two menu buttons still stacked (2026-07-18, Track 2)

The user's first stacking report (earlier same-day entry above) was fixed
for the case of the *same* button tapped repeatedly - a stable id on the
category-menu message let repeated 📚 taps no-op once it was already the
last message. But the user then sent a screen recording showing it was
still happening: repeatedly tapping "📚 ดูหมวดคำถามอื่น" and then re-picking
the *same* category kept appending a fresh pair of menu bubbles forever.
Root cause the first fix missed: `groupMenuMessage`/`subQuestionMenuMessage`
had no dedup guard at all and used non-deterministic `Date.now()`-based ids,
so alternating between two different menu-producing buttons always looked
like "a new last message" to the old single-id check even though nothing
new was actually being asked.

Fixed properly this time with a general rule instead of a per-button
patch: every menu-level message (category/group/sub-question) now gets a
stable, content-derived id (`grp-${categoryId}`, `sub-${groupId}`), and
`pushOrReplaceMenu()` checks whether the *trailing* message is *any* kind
of menu (`isMenuMessageId`) - if so it's replaced in place instead of
appended, regardless of which specific menu it was. Only a real question/
answer (or the very first menu shown right after one) still starts a new
bubble. Net effect: however many times a visitor bounces around the menu
tree without asking an actual question, only one menu bubble ever sits at
the bottom of the chat log, updating in place.

**Tested**: new regression test reproduces the exact click sequence from
the recording (pick category → back → pick same category, four times) and
asserts zero duplicate category-menu bubbles and exactly one trailing
group-menu bubble. Full suite 310/310, `tsc` clean. **Live-verified via
Playwright** against a real dev server + API (not just the test harness):
scripted the identical bounce sequence in a real browser session and
confirmed only one menu bubble remains on screen afterward (screenshot
matches the assertion).

### Fixed - Energy Report's monthly chart used single-letter English month labels (2026-07-18, Track 1 work, done by Track 2 with permission)

The user asked for full (not abbreviated) Thai month names on the Monthly
generation chart - it previously read `MONTH_LABELS = ['J', 'F', 'M', ...]`,
a single English letter per bar. Replaced with the full spelled-out Thai
names (มกราคม, กุมภาพันธ์, ... ธันวาคม), which are long enough that the
X-axis ticks needed angling (`angle={-40}`, `textAnchor="end"`, extra
`height`/`tickMargin`/bottom margin) to avoid overlapping across 12 bars -
same pattern ForecastPage.tsx already established for its own long-label
axis. `MONTH_LABELS` is now exported (not module-private) since recharts'
`<ResponsiveContainer>` never renders real tick text under jsdom (reports
zero measured width/height), so the only reliable way to test this is
asserting on the array the chart's `tickFormatter`/`labelFormatter` both
read from, not by querying rendered SVG text.

**Tested**: new test asserts all 12 entries, first/last values, and that
none are single-character abbreviations. Full suite 311/311, `tsc` clean.
**Live-verified via Playwright**: logged in, navigated to Energy Report,
screenshotted the rendered chart - all 12 full Thai names render angled,
legible, with no overlap or clipping.

### Fixed - Forecast page's overlapping chart lines were hard to tell apart even with different colors (2026-07-18, Track 1 work, done by Track 2 with permission)

The Day-ahead/Intra-day power chart and the Minute-ahead chart both plot
4 lines over the same time axis (`actualPast`, `actualToday`, `actualNow`,
`pred`/Forecast) - each already its own color, but at every point two of
them cross or run close together, color alone wasn't enough to tell which
was which at a glance. Gave the two most-likely-to-overlap lines their own
stroke style instead of just color: `pred` (Forecast, the one every other
line gets compared against) is now dotted - a very short dash
(`strokeDasharray="1 6"`) with `strokeLinecap="round"` so each dash
renders as a small round dot rather than a rectangular dash, per the
user's explicit preference for "เส้นประแบบจุดแทนขีด" (dot-style, not
dash-style) - and `actualToday` gets a regular dash (`"6 3"`) since it
sits directly between `actualPast` and `actualNow` and is the one most
often sandwiched between two solid lines. `actualPast` and `actualNow`
stay solid as the two "anchor" reference lines.

**Tested**: `ForecastPage.test.tsx` full suite still passes unchanged
(12/12) - this is a pure presentation change, no data/behavior shift.
`tsc` clean. **Live-verified via Playwright**: logged in, screenshotted
the rendered Day-ahead chart - confirmed the dotted Forecast line is
visually distinct from the solid Actual-power line at every point they
cross, including where the two directly overlap.

### Added - explicit chart-panning slider on Forecast, "now" centered by default (2026-07-18, Track 1 work, done by Track 2 with permission)

The main power chart (Day-ahead/Intra-day) was already rendered at a real
pixel width wider than its container, panned via native `overflow-x: auto`
scroll - but there was no visible control hinting that there was anything
*to* scroll to, and the default scroll position was wherever the browser
happened to land (effectively the left/oldest edge), not "now". User
report: "ยังไม่ทำแถบเลื่อนในกราฟ...ช่วงเส้นกราฟของวันนี้ให้ตั้งไว้ตรงกลางกรอบ".

Added an explicit `<input type="range">` synced bidirectionally with the
scroll container (dragging it scrolls the chart; native touch/trackpad
scroll updates it back), and a one-time auto-center on "now" the first
time real data lands for a given zone/horizon selection - deliberately
*not* on every background poll refresh, which would otherwise yank a user
who's scrolled away back to "now" every time the data refetches. The
centering math itself (`centeredScrollPosition` in `lib/chartData.ts`) is
a pure function taking rows/now/pxPerPoint/widths and returning
`{scrollLeft, max}` - kept separate from the DOM-wiring `useEffect` so
it's directly unit-testable, since jsdom never runs real layout and
`scrollWidth`/`clientWidth` are always 0 there (the same constraint that
already forced Energy Report's month-label test into the same pattern,
see that entry above).

**A real, pre-existing bug found and fixed along the way**: building this
revealed `.forecast-chart-section` (a flex item, `flex: 3 1 480px`) was
never actually shrinking to fit its row - flex items default to
`min-width: auto`, meaning "never shrink below your content's own
intrinsic width," and this section's content includes a fixed ~4000px-wide
scroll track. Without `min-width: 0`, the *section itself* ballooned out
to ~4000px instead of the scrollable child ever getting a chance to clip
anything - confirmed live by reading `scrollWidth`/`clientWidth` off the
real DOM node and finding them identical (no overflow ever existed). This
means the chart's native scroll-to-see-history feature, despite being
built and documented earlier the same day, may never have actually worked
in the first place at typical viewport widths - not a regression from
today's change, a latent bug this work happened to surface.

**Tested**: 5 new `centeredScrollPosition` unit tests in
`chartData.test.ts` (centers correctly, clamps at both edges, no-op when
content already fits, handles an empty series) - 316/316 full suite,
`tsc` clean, production build succeeds. **Live-verified via Playwright**
against a real dev server + API: confirmed `.forecast-chart-section`'s
measured width now matches its row (no more blowout), the slider renders
with a real min/max/value once there's genuine overflow, dragging it
actually moves `scrollLeft`, and the initial position lands centered on
"now" rather than 0 - screenshotted before and after the CSS fix to
confirm the before-state reproduced the bug exactly as diagnosed.

### In progress - the 9-variable dashboard, part 1: types + backend wiring (2026-07-18, Track 1 work, done by Track 2 with permission)

First checkpoint of a larger feature (3x3 real-time table + grouped graphs
for jitkomut's 9 reference-paper variables), landed separately from the UI
itself per this session's "commit after each real chunk" policy. The
9-variable audit locked in earlier the same day (from a since-lost prior
session - see `HANDOFF.md`/this session's own notes): **5 already used**
- I (`ssrd_w_m2`), T (`temp_c`), I_clr, k-hat (as `cloud_index`), I_wrf
(the same `ssrd_w_m2` field's future-forecast portion, split client-side
by timestamp vs. now - see ForecastPage's existing actualPast/pred split,
which this mirrors rather than inventing a new distinction). **4 newly
surfaced**: RH and wind speed were collected into `nwp_history` but never
read anywhere; UV index exists only as daily-resolution NASA POWER data;
zenith angle was computed elsewhere (Solar3DPage) but never exposed via
any weather endpoint.

`lib/types.ts`'s `WeatherStripPoint`/`WeatherStripResponse` now match the
extended `GET /weather/strip` response (see `api/README.md`'s matching
entry for the backend side) - `ghi_clearsky_w_m2`, `cos_zenith`,
`cloud_index`, `relative_humidity_pct`, `wind_speed_ms` per point, plus a
separate `uv_daily` list. Planned graph grouping (already agreed, not yet
built): I/I_clr/I_wrf together (same W/m² unit, all have actual+forecast),
T alone (has its own NWP forecast), k-hat + cos(zenith) together (both
unitless ~0-1, no forecast - derived-from-now only), RH/wind/UV each on
their own graph (different units, genuinely no forecast model for any of
them - not fabricating one).

**Tested**: existing `weatherStrip.test.ts`/`assistant.test.ts`/
`ForecastPage.test.tsx` mocks updated for the new required fields (a
`point()` test factory added to `weatherStrip.test.ts` so each case only
spells out what it actually varies). Full suite 316/316, `tsc` clean - no
UI changes yet, so nothing new to live-verify at this checkpoint.

### Fixed - private chat message-loss race, mascot's 4 starter questions vanishing for good, plus a "someone messaged you" notification (2026-07-18, Track 2)

Reported live via screen recording: typing and sending a message in the
private visitor chat visibly cleared the input (confirming the send fired)
but the message never appeared, and reopening the same thread later still
didn't show it. Root cause: `useChatSocket.ts`'s `openConversation` fires
`GET /chat/history` the moment a thread is opened, and separately, the
visitor's own send gets WS-echoed back almost immediately (same open
connection, no HTTP/auth/DB round trip) - if that still-in-flight history
fetch resolves *after* the echo already appended the new message to state,
its old `messages: [...history]` overwrite silently wiped the just-sent
message back out. Fixed by merging the fetched history with whatever's
already in state (deduped by the DB's own globally-monotonic message id)
instead of replacing it outright - new `mergeMessagesById()`. Verified two
ways: a new unit test that reproduces the exact ordering (live WS message
arrives before a deliberately-delayed `getChatHistory` mock resolves), and
a live two-browser-context Playwright run (two real logins, one client
firing 3 rapid sends) confirming all 3 survive both the initial send and a
full close/reopen of the thread.

Also fixed, reported in the same message: น้อง Solar's 4 starter quick-reply
chips (ตอนนี้ผลิตไฟเท่าไหร่ / พยากรณ์พรุ่งนี้เป็นยังไง / หน้านี้ใช้งานยังไง /
kWp คืออะไร) only ever rendered on the greeting message, and
`AssistantPanel.tsx` only renders a message's `options` when it's the
*trailing* message in the chat log (an intentional rule from the earlier
menu-stacking fix) - so the moment a visitor asked anything or picked any
menu button, those 4 chips were gone for the rest of the session with no
way back short of closing and reopening the whole panel. Fixed by folding
them into `categoryMenuMessage()` too (new shared `starterOptions()`), so
they're reachable any time via the 📚 button, not just once at the very
start.

New, not just fixed: an incoming-message toast (`VisitorNetwork.tsx`'s
`NotificationToast`) - requested alongside the bug report ("ทำระบบแจ้งเตือน
ด้วยว่าใครแชทหรือทักมา"). Anchored above the chat toggle so it's visible
whether the widget is open or fully collapsed (the badge count alone
required reopening the panel just to see who messaged), shows the sender's
avatar/name and a text preview (or a sticker-specific "ส่งสติกเกอร์ 🎉 ..."
line, not the raw encoded string), auto-dismisses after 6s or on its own ×
button, and clicking it opens straight into that thread. Suppressed for a
thread already on screen (the bubble itself is enough) and for the
visitor's own outgoing messages. Opening a peer's thread directly from the
contact list also clears any of that peer's still-showing toast, so it
never lingers pointing at a conversation already open.

**Tested**: `useChatSocket.test.tsx` (+1 race-condition regression test),
`AIAssistant.test.tsx` (+1 starter-questions-reachable-via-📚 test),
`VisitorNetwork.test.tsx` (+5 notification-toast tests, +2 existing tests
adjusted to scope their queries now that a toast can legitimately show a
message preview elsewhere on screen at the same time). Full suite 323/323,
`tsc` clean. Live-verified end to end with two separate logged-in browser
contexts (Playwright, real API+WS, not mocked): rapid-fire sends, thread
reopen persistence, the toast appearing/opening/clearing, and the mascot's
quick-reply chips reappearing via 📚.

### Fixed - น้อง Solar's voice reads mixed Thai/English text clearly instead of mangling whichever language isn't `th-TH` (2026-07-18, Track 2)

Reported live: "อยากแก้ระบบเสียงน้อง solar ปรับปรุงเสียงการอ่านภาษาไทย ภาษาอังกฤษ
อยากให้ชัดเจนมากขึ้นอีกเยอะๆ". Every 🔊 reply here is naturally mixed-language
(น้อง Solar's own canned answers mix Thai sentences with English technical
terms - "kWp", "GIS", "Forecast", "NPV/IRR/LCOE") - `tts.ts` previously
forced the *entire* utterance through a single hardcoded `lang: 'th-TH'`,
so a Thai voice engine mangled every English word it hit (and would equally
mangle Thai text if the lang were flipped to English). Fixed with a new
`segmentByLanguage()`: splits the reply into consecutive same-script runs
(Thai Unicode block vs. Latin letters; digits/punctuation stay attached to
whichever run they're already inside rather than fragmenting it), and
`speakText()` now queues one utterance per run with its own matching
`lang` - the Web Speech API plays queued `speak()` calls back to back in
order, so no manual chaining via `onend` was needed. Also slowed the
default `rate` from 1.0 to 0.92 (a small, still-natural-sounding change -
most Thai TTS voices read noticeably rushed at "normal" speed), and added
voice selection: `speechSynthesis.getVoices()` is cached per-language (a
`WeakMap` keyed on the `SpeechSynthesis` instance, handling the
`voiceschanged` async-load quirk Chrome has), preferring a voice whose name
mentions "Google" when more than one matches - on Chrome those are the
higher-quality network-backed voices, the clearest win available here
without shipping/calling a paid TTS API (out of scope per this project's
zero-cost-API rule).

**Tested**: `tts.test.ts` rewritten (15 tests: `segmentByLanguage` unit
tests for pure-Thai/pure-English/mixed/digit-folding/empty-input cases,
plus `speakText` tests for per-segment queuing, the slowed rate, voice
preference, and the pre-existing cancel/unavailable-synth behavior).
Existing `speechSynthesis` stubs in `AIAssistant.test.tsx`,
`VisitorNetwork.test.tsx`, and `stickers.test.ts` were missing
`getVoices`/`addEventListener` (real browsers always expose both) - added
so they don't throw now that `tts.ts` actually calls them; one AIAssistant
test's exact-one-utterance assertion loosened to match the new
multi-utterance-per-mixed-reply reality (asserts at least one call and
that the reply opens in Thai, not a fixed call count). Full suite
335/335, `tsc` clean. Live-verified in a real Chromium tab (Playwright,
`speechSynthesis`/`SpeechSynthesisUtterance` instrumented via
`Object.defineProperty` to capture actual queued utterances - a plain
`window.speechSynthesis = ...` reassignment is a silent no-op in Chromium,
a real getter-only accessor on `Window.prototype`): the greeting's ☀️
"น้อง Solar" / "AI" mix produced 5 correctly-alternating th-TH/en-US
utterances, all at the slowed 0.92 rate.

### Added - more emoji throughout น้อง Solar's replies, doubled the "เล่นกับน้อง Solar" play catalog (2026-07-18, Track 2)

Reported live alongside the TTS clarity fix: "เพิ่มอิโมจิ และการเล่นกับน้อง
solar". Two separate, purely additive content changes, no logic touched:

1. **Emoji pass** - `assistant.ts`'s 11 hand-written canned replies (help
   navigation, kWp/irradiance/plant-factor/forecast-horizon definitions,
   current-power/today-energy/forecast/capacity/weather/financial live-data
   answers) and `AssistantPanel.tsx`'s 3 menu messages (category/group/sub-
   question prompts) each got one fitting leading emoji. `assistantContent.ts`'s
   all 34 guided-topic answers got the same treatment via a small one-off
   script (topic-appropriate emoji per entry - ☀️ for what a solar cell is,
   🔌 for what an inverter is, 💰 for the electricity-bill breakdown, etc.)
   rather than 34 manual edits. Every emoji was placed as a prefix/suffix
   around the factual content, never inside a substring any existing test
   asserts on (numbers+units, exact page names, etc.) - confirmed by the
   full suite still passing unchanged except for the handful of exact-string
   menu/interaction-speech assertions that intentionally now include the
   added emoji.
2. **Play catalog doubled** - `mascotInteractions.ts`'s "เล่นกับน้อง Solar"
   catalog grew from 12 to 24 (sing, dance, wink, selfie, give a star, fist-
   bump, sunbathe, tell a secret, compliment, fake-sneeze, lullaby, sunglasses
   pose), all reusing the 10 existing `MascotFace` moods rather than inventing
   new ones - a new mood needs real face SVG art, which is design work, not a
   data-only change, so this stayed a safe, purely additive catalog expansion.

**Tested**: `mascotInteractions.test.ts`'s "generous number" threshold
bumped from ≥10 to ≥20 to reflect the real growth, plus a new test asserting
every interaction's label contains at least one emoji (`\p{Extended_Pictographic}`).
`AIAssistant.test.tsx`'s handful of exact-string menu/interaction-speech
assertions updated to include the now-present emoji. Full suite 336/336,
`tsc` clean. Live-verified in a real browser (Playwright): the greeting,
category-menu chips, and a kWp knowledge answer all render their new
leading emoji correctly; the play panel shows all 24 buttons in its grid;
clicking the new "💃 ชวนเต้น" button visibly changes the mascot's face and
shows its speech bubble, same as every pre-existing interaction.

### Fixed - Model Competition panel silently showed 0 bars instead of saying why (2026-07-19, Track 1)

Reported live with a screenshot: the "การแข่งขันของโมเดล (Model Competition)"
panel rendered its axis and legend correctly but every bar was 0. Root-caused
via a local Postgres + fresh API instance (this exact branch's code, not
production): `/forecast/{zone}/hour`'s `candidate_errors` is populated
unconditionally by `training.py` for every real `model_type: "ml"` point -
the only way it comes back empty is the zone's hour-ahead model still being
the physics-only fallback (not enough real NWP history accumulated yet for
that specific zone), which legitimately has no per-candidate RMSE to report.
`ForecastPage.tsx`'s `ModelCompetitionPanel` used to only gate its "no data"
message on `rows.length === 0` - but `buildCompetitionRows` still produces
real rows (just with null candidate values) once any hour-ahead points
exist, so this case fell through to the chart-render branch and showed an
axis/legend with nothing to plot instead of an honest status message.

Added `competitionIsPhysicsBaseline` (same `model_type === 'physics_baseline'`
check `isPhysicsBaseline`/`minuteIsPhysicsBaseline` already use for the main
chart and Minute-ahead panel, applied to the hour-ahead queries specifically
since Model Competition always shows the intra-day race regardless of the
Day-ahead/Intra-day toggle) - when true, the panel now shows "โซนนี้ยังไม่มี
ข้อมูลจริงสะสมมากพอที่จะฝึกโมเดล ML แข่งกัน...ยังไม่มีผลการแข่งขันโมเดลให้แสดง"
instead of rendering the misleading empty chart.

**Not a code bug in the everyday sense** - if this is what's showing in
production, the fix isn't more frontend code, it's confirming the zone has
accumulated enough real NWP ingestion history to leave the physics-baseline
fallback (or checking `api`'s own logs for `retrain failed for zone/horizon`
warnings, which would point at a real training exception instead).

**Tested**: new `ForecastPage.test.tsx` case mocks `model_type:
'physics_baseline'` on the hour horizon and asserts the honest caption
renders instead of the chart. Full suite 350/350, `tsc` clean.

### Fixed - 3D View: Sun kept drifting after sunset and Moon never rose to replace it (2026-07-19, Track 1)

Reported live: "ดวงจันทร์ไม่ยอมขึ้นมาตอนพระอาทิตย์ตกดิน และดวงอาทิตย์ไหลใน
ระนาบพื้นหลังจากตกดินซึ่งมันควรจะหายไปให้ดวงจันทร์ขึ้นมาแทน". Root-caused via
a local API + Postgres instance and Playwright scrubbing the time slider past
real sunset: `/sun-path` returns only `elevation_deg > 0` samples (see that
route's own docstring) at a nominal 15-minute cadence over one UTC calendar
day - but because Thailand's real sunrise (~00:00 UTC) sits close to UTC
midnight, the *kept* samples routinely jump straight from today's last
pre-sunset point to the next day's first post-sunrise point, both landing
inside the same 00:00-23:45Z window. `interpolateSunPosition` (`solar3d.ts`)
only checked whether a target time fell within the array's overall first/
last bounds before searching for a bracketing pair - a target time in that
removed overnight gap still passed that check, and the search then happily
linearly-interpolated across the two far-apart samples bracketing sunset and
next sunrise (many hours apart), producing a fictional small *positive*
elevation for the entire night. That kept `SunMarker`'s `visible = elevationDeg
> 0` gate open long after real sunset (the reported "drifting" - its position
was actually crawling between the two interpolation endpoints, not frozen),
and kept `MoonMarker`'s `sunIsDown` check from ever turning true.

Fixed by adding `MAX_ADJACENT_SAMPLE_GAP_MS` (20 minutes - safely above the
real ~15-minute sample cadence, safely below any real overnight gap): if the
two samples bracketing a target time are farther apart than that, treat it
the same as "outside the covered range" (`null`) rather than interpolating
across it. Live-verified via Playwright against a local API+Postgres
instance: scrubbing to 19:30 ICT (well past today's real ~18:45 ICT sunset)
now correctly hides the Sun marker, and `MoonMarker`'s own computed
visibility (checked via temporary debug logging, removed before commit)
correctly turns `true` once React's geometry-query fallback catches up
(within roughly one network round-trip - not a persistent bug, just normal
async settling).

**Tested**: two new `solar3d.test.ts` cases - a target time inside a
constructed overnight gap returns `null`, and a target time between two
genuinely-adjacent 15-minute samples near the edge of that same gap still
interpolates normally. Full suite 350/350, `tsc` clean.

### Changed - 3D View: collapsed "Solar access" / "String view" into one always-on sun-reactive panel gradient (2026-07-19, Track 1)

Reported live as confusing rather than useful: "ตรง string view กับ solar
access เพื่อกันความงง เราจะยุบให้เหลืออันเดียว...โดยไล่เฉดสี เขียว เหลือง ส้ม
แดง โดยไล่เฉดแบบ ultrasmooth เหมือนดวงอาทิตย์ และระวังดีๆตอนกลางคืนห้ามเอาแสง
จันทน์มาผลิต". Removed the icon-rail toggle and `viewMode` state/prop
entirely (`Solar3DIconRail.tsx`, `Solar3DPage.tsx`, `Solar3DScene.tsx`) -
the Sun icon button that used to switch to "access" mode is now a fixed,
non-interactive legend hint (`.solar3d-icon-btn-static`), and `stringColor`
(the old per-block-id static hue) is deleted. Every panel now always colors
via the existing `solarAccessColor` red→yellow→green hue ramp (continuous
0-120° hue sweep, which visually already passes through orange between red
and yellow - matches the requested เขียว/เหลือง/ส้ม/แดง gradient without a
formula change) applied to `panel.solar_access_pct * zoneOutputRatio`, the
same real-output-blended value the old "access" mode already used.

**Night-safety clamp**, the explicit second half of the request: panel color
now computes as `solarAccessColor(sunElevationDeg > 0 ? panel.solar_access_pct
* zoneOutputRatio : 0)` - forcing every panel to the gradient's red/0% end
the instant the sun's elevation is at or below the horizon, regardless of
what `zoneOutputRatio`'s own real-power lookup produced. This is a
deliberate belt-and-suspenders guard, not just trusting that lookup to
always land on a genuine zero - `zoneOutputRatio` falls back to the
*nearest* `performance.data.hourly`/`forecast.data` reading with no maximum
time-distance cutoff (see that variable's own docstring in
`Solar3DPage.tsx`), so a sparse night with no real telemetry rows could in
principle pick up a stale earlier-in-the-day positive reading - exactly the
"panels shouldn't read as producing off moonlight" failure mode the user
explicitly flagged. The elevation gate uses the same `sunElevationDeg` prop
already driving `SunMarker`'s own visibility, so panels and the Sun marker
go dark in lockstep.

Smoothness note: panel color updates on the same cadence as the Sun's own
readouts (a live React re-render per `sunElevationDeg`/`zoneOutputRatio`
change, throttled during Play via `SYNC_CALLBACK_INTERVAL_MS` like every
other scene readout) rather than a new per-frame WebGL material update - the
existing cadence was already tuned for "smooth" elsewhere on this page, and
introducing a second, independent per-frame color-interpolation path felt
like a materially bigger, harder-to-verify change for uncertain visual gain
under Playwright (which can't judge animation smoothness, only take
snapshots). Flagging this so a future session knows it was a deliberate
scope call, not an oversight, if truer 60fps color interpolation is wanted.

**Tested**: `Solar3DPage.test.tsx`'s old view-mode-toggle test replaced with
one asserting no "String view"/"Solar access" tab exists anymore. Full suite
350/350, `tsc` clean. Live-verified via Playwright: the icon rail now shows
4 icons (static Sun legend, play, camera reset, satellite/ground toggle)
with no toggle group; panels render the red/orange gradient correctly at low
sun elevation (07:00 ICT, altitude 13°).

### Added - 3D View: Play resets a stale simulated date back to today (2026-07-19, Track 1)

Per the user's own request ("เมื่อ sim ใหม่ก็ให้ดวงอาทิตย์ขึ้นมาใหม่ โดยวันใน
การ sim ให้อัปเดตเลือกอัตโนมัติตามวันเวลาจริงๆ"): `date` state only ever
defaulted to `todayIso()` once, at initial mount - a tab left open across a
midnight, or a manually-picked past/future date, used to keep replaying that
same stale day's sun/moon arc indefinitely with no way back to "today" short
of a full page reload. `Solar3DPage.tsx`'s new `handlePlayToggle` snaps
`date` back to `todayIso()` the moment Play is pressed from paused, if it
isn't already today - the existing per-date sunrise-default effect then
re-seeds `timeOfDayMinutes` for that date the same way a manual date-picker
change already does. Only fires on Play, not every render, so a
manually-picked past/future date still holds correctly while paused for
inspection.

### Added - login screen's left side: น้อง Solar/moon/cloud react to the username/password fields (2026-07-18, Track 2)

Requested after the user shared a reference clip of a login page whose
character illustration watches the email field while typing and looks away
(closed eyes) for the password field. Approved live with a specific scope:
replace the login screen's left-side decoration only (previously a mirror
of the right side's solar-system motif, `LoginSolarDecor.tsx`) - the right
side keeps that motif unchanged, and the centered login form is untouched.
Built with our own characters (น้อง Solar the sun, plus a new moon and
cloud) rather than the clip's generic shapes, and with the exact approach
the user specified: plain React state (`onFocus`/`onBlur`, lifted in
`Login.tsx` as `focusedField`) + CSS/SVG transforms, no physics engine.

New `LoginMascotDecor.tsx` renders all three characters, mood-mapped from
`focusedField` (`moodFor()`, unit-tested directly): `'surprised'`
(wide, alert eyes) while the username field is focused, `'blush'` (closed
eyes - reuses the exact same closed-eye artwork the "เล่นกับน้อง Solar" pet-
head interaction already uses) while the password field is focused, and
`'idle'` otherwise. A CSS state class per case additionally leans the whole
character cluster toward the form (watching) or away from it (shy), and
idle gets a continuous gentle per-character wobble - `--wobble-*` CSS
custom properties randomized once on mount (`Math.random()`, not re-rolled
per render) so each character sways at a slightly different angle/rate.
This is the "หลอกตา" (fake it) interpretation of the reference clip's more
dramatic "knocked into a pile" easter egg the user also approved: cheap
CSS keyframes with randomized parameters, not an actual physics
simulation, since a literal topple-and-reset animation would need a real
trigger design and risks looking janky without real physics - explicitly
the complexity being avoided here.

`MoonFace.tsx`/`CloudFace.tsx` are new, minimal sibling characters to
`MascotFace.tsx`'s sun - simpler than the sun (no rays/rotation/sparkle
overlays), but share its exact eye/mouth SVG system (`EyePair`,
`MOUTH_PATH`, both newly exported from `MascotFace.tsx` for reuse) by
drawing on the same 0-0-120-120 viewBox with the face in the same
x=44-76/y=54-66 region, so no per-character offset math was needed.
`LoginSolarDecor.tsx` trimmed to its right-side markup only (the left-side
block and its now-unused `.login-solar-decor-left` CSS rule removed) -
its own test still passes unchanged (only checked the root wrapper's
`aria-hidden`/no-interactive-content, not which side).

**Tested**: `LoginMascotDecor.test.tsx` (new - `moodFor()` unit tests plus
render/state-class checks), `Login.test.tsx` (+3 tests: watching class on
username focus, shy class on password focus, back to idle on blur). Full
suite 347/347. **Also caught and fixed a CI build gap this session**: `tsc
--noEmit -p .` and `vitest run` both stayed clean while `npm run build`
(the actual CI step, `tsc -b` in project-reference build mode) failed on
two real type errors elsewhere in the test suite (`VisitorNetwork.test.tsx`
passing a `querySelector()`-returned `Element` to `within()`, which expects
`HTMLElement`; a `tts.test.ts` `mock.calls.map()` callback with a tuple
parameter type TS rejected against the inferred `any[][]` call-args type) -
both fixed, and `npm run build` is now the local pre-push check instead of
the incomplete `tsc --noEmit` substitute. Live-verified in a real browser
(Playwright): idle shows all three characters clustered and clearly
separated (not stacked/hidden behind each other); focusing username adds
the watching state (wide eyes, leaned toward the form) and clears on blur;
focusing password adds the shy state (closed eyes, leaned away) and clears
on blur; the right-side solar decoration and the login form's centering
(`form center X` measured equal to `viewport center X`) are both
unaffected; both decorations correctly disappear below the existing
1020px breakpoint.

### Changed/Added - Model Competition hidden from viewer role, UV gets a real daily bar chart (2026-07-19, Track 1)

Two more items from the same round as the entries just above.

**Model Competition hidden from viewer**: per the user's own call ("ไม่น่าจะ
สำคัญเเล้ว ปิดไม่ให้ user เห็น" - "probably not important anymore, turn it
off so users can't see it") - a step further than the "honest empty state"
fix two entries up, which only stopped the panel from *misleading* a
viewer; this stops it from *reaching* one at all. `ForecastPage.tsx` now
reads `role` from `useAuth()` and wraps `<ModelCompetitionPanel>` in
`{role !== 'viewer' && (...)}` - the same "hide from viewer, keep for
admin/operator" precedent `App.tsx`'s `RequireOperator` already set for
Financial/Simulation, just scoped to one panel inside a page instead of a
whole route (the rest of ForecastPage stays visible to viewer).

**UV daily bar chart**: the grouped-graphs section previously showed UV as
a caption-only "no chart, daily data only" placeholder (2026-07-18 entry
above) - the user asked for an actual chart despite the coarse cadence.
New `GET /weather/uv-history` (`api/routes_weather.py`) returns every real
`uv_history` row this deployment has accumulated, oldest first (no faked
interpolation - see that route's own docstring). Frontend: `useUvHistory()`
(30-min `staleTime`, not the 60s live-dashboard cadence - UV cannot change
within a day) feeds a new Recharts `BarChart` in `SolarVariablesGraphs`,
one real bar per day, with an honest "not enough days accumulated yet"
caption when `points` is empty rather than blocking on it. New
`--chart-uv` CSS variable (violet, distinct from every existing chart
color). Deliberately still *not* an hourly/interpolated curve - the
previous session's explicit reasoning against faking one stands, this just
answers "yes, chart it" with the granularity that's actually real.

Also flagged, not touched (Track 2 territory): `assistantTopics.ts` still
offers "Model Competition คืออะไร" as a suggested AI-assistant question to
every role, including viewer, who can no longer see the panel it explains
- worth a look next time Track 2 is in `web/src/lib/assistant*`.

**Tested**: `api/tests/test_routes_weather.py` +3 (auth-required, empty
store, multi-day sorted response). `forecast/tests` untouched by this half
(no backend model change - `uv_history` already existed). `web/src/pages/
__tests__/ForecastPage.test.tsx` +3 (viewer-hides-Model-Competition,
UV-chart-renders-with-data, UV-chart-honest-empty-state) and 2 existing
cases updated for the new UV chart title/copy. Full suite 364/364. `npm
run build` (`tsc -b` + `vite build`) clean too.

### 2026-07-22 - UV chart upgraded to a real hourly curve (roadmap item 5)

The ForecastPage UV chart was a one-bar-per-day daily chart. It now shows the
real **hourly** UV line (Open-Meteo `hourly=uv_index`, rendered in ICT) when
hourly data has accumulated, automatically falling back to the daily bar chart
when only daily data exists, and to the honest-empty state when neither does.
New `useUvHourlyHistory` query + `getUvHourlyHistory` client +
`UvHourlyHistoryPoint`/`UvHourlyHistoryResponse` types hit the new backend
`GET /weather/uv-hourly-history`. Tested: `ForecastPage.test.tsx` +1 (hourly
line renders + title switches to "รายชั่วโมง" when hourly data exists); full
web suite (374) + `tsc` + build pass.

### 2026-07-22 - Illustrative site environment in the 3D View

Added a `SiteEnvironment` layer to `Solar3DScene`: trees, houses, a taller
building, and equipment cabinets arranged in a deterministic ring just outside
the framed array block, so the 3D scene reads as a real site at human scale
instead of panels on an empty plane (user request). A page checkbox
"แสดงสภาพแวดล้อมจำลอง" (default on) toggles it, with a caption stating plainly it
is illustrative for scale/orientation only - NOT a surveyed obstacle layout and
NOT an input to the irradiance/shading calculation (same honesty bar as the
external-shading known gap). Objects are absolute human-scale meters (a ~5 m
tree beside the ~2 m panels), positioned by a seeded RNG so they never jitter.
Tested: `Solar3DPage.test.tsx` +1 (toggle on/off); live-verified in Chromium at
13:00 ICT. `tsc` + full web suite (375) pass, `oxlint` clean.
