# Module 3 — Feature Store & Preprocessing

Pure, DB-independent pandas feature-engineering functions: clear-sky model +
solar position (pvlib), lag/EMA/future-regressor features, curtailment/
degradation QC, daytime filtering, and multi-step training-frame assembly.
Deliberately decoupled from any specific data source (Module 1's `cloud_obs`,
a future Module 2's `nwp_forecast`, actual generation-meter data — none of
which has enough history yet to build a real end-to-end demo against) so
every piece is independently unit-tested now and wireable to real tables once
that data exists.

## Pipeline

```
nong_fab_site_location()                          # (lat, lon) from config/assets.yaml
        │
        ▼
compute_clearsky_and_position(index, lat, lon)   # pvlib Ineichen model + solar position
        │
        ▼
clear_sky_index(ghi_measured, ghi_clearsky)       # CSI = measured / clear-sky
        │
        ▼
filter_daytime(df, max_zenith_deg=85)             # drop night rows before anything else
        │
        ▼
add_auto_lags(df, [I, P], lags)                   # I/P history
add_ema(df, [I], spans)                           # smoothed irradiance
add_future_regressors(df, [I_clr, I_nwp], horizons)  # values already known ahead of time
flag_curtailment_or_degradation(df, I, P)         # QC flag column
        │
        ▼
build_training_frame(df, target_col=P, horizon=H) # y(t+1..t+H) targets, drop NaN
        │
        ▼
chronological_split(df, train_frac, val_frac)     # NOT shuffled - avoids time-series leakage
```

Verified as a whole (not just piece by piece) against 10 days of synthetic
10-min-cadence data in the module's own smoke check — every stage's output
feeds cleanly into the next, ending in a leak-free chronological split.

## Curtailment/degradation QC — two signals, not one

The paper's warning is that P can decouple from I (grid curtailment, inverter
fault, degradation). A single rolling correlation misses the most common real
case: a **hard curtailment cap** flatlines power to a constant while
irradiance keeps varying, and Pearson correlation against a zero-variance
series is mathematically undefined (`NaN`), not "low" — a naive
`corr < threshold` check silently lets exactly this case through. Fixed by
also checking for a flatlined power signal (near-zero rolling std) against
still-varying irradiance, and flagging on either signal. Both paths have
dedicated tests (`test_quality_control.py`).

## Panel geometry & shading (Module 7's 3D view, added later)

`panel_geometry.py`/`shading.py` weren't part of the original forecasting
pipeline above - they were added to back Module 7's Feature B/C (3D panel-
level shading/solar-access view + sun-path sweep), reusing this module's
existing `compute_clearsky_and_position()` for solar position rather than
duplicating it. Kept in `features/` (not `api/`) because they're the same
kind of thing as everything else here: pure, DB-independent geometry/physics
functions, unit-tested on their own, that a caller (Module 6's API) wires up.

```
generate_zone_layout(zone_id)                     # config/assets.yaml -> per-panel (east_m, north_m, tilt, azimuth)
        │
        ▼
zone_solar_access(layout, sun_elevation, sun_azimuth)   # per-panel row-shading fraction -> solar access %
```

- `panel_geometry.py`: converts each zone's surveyed corners into a local
  (east, north) meter grid, then places panels. Only Jetty (`sub_arrays` in
  config/assets.yaml) has a real per-string layout; GIS/ISB are a
  visualization-approximation rectangular block sized to `module_count`.
  `tilt_deg`/`azimuth_deg` are unmeasured for every zone (see `Zone`'s own
  docstring) - `DEFAULT_TILT_DEG`/`DEFAULT_AZIMUTH_DEG` are literature-typical
  assumptions for this latitude, documented inline, not measurements. Jetty
  gets its own azimuth default (`JETTY_DEFAULT_AZIMUTH_DEG`, east/west-
  facing) rather than GIS/ISB's south-facing default - its ~1.25km
  north-south trestle physically requires facing across its own width, not
  along its length (a south-facing default would swing each string ~48m off
  the side of the catwalk - see the constant's own comment for the full
  derivation).
- `shading.py`: standard fixed-tilt row-to-row self-shading (front row
  shades the row behind it once the sun is roughly aligned with the array's
  own facing azimuth) - inter-row self-shading only, no obstacle survey
  (trees/structures) exists in config/assets.yaml so that's out of scope,
  not fabricated. A 2D cross-section approximation, visualization-grade, not
  a bankable energy-yield calculation.
  - `string_power_balance()` (added for a Feature B spec gap closure): per-
    string estimated power grouped by `(block_id, row)`, flagged against a
    zone's `design_constraints.string_power_balance_max_kw` (Jetty's own
    2kW). Only meaningful where `row` really is a string index -
    `panel_geometry.py`'s `_jetty_layout()` lays out exactly one row per
    real electrical string (`sub_array.strings`), but GIS/ISB's
    rectangular-block layout doesn't, so callers (Module 6's `/geometry/
    {zone}`) only compute this for Jetty - see the function's own
    docstring.

## SLD topology & irradiance grid (Module 7's Energy Report + map, STEP 8C)

`sld.py`/`irradiance_map.py` back Module 7's Feature D (Energy Report's
"Auto-SLD viewer") and Feature E (MapLibre irradiance map), the same "pure,
DB-independent, unit-tested here, wired up by Module 6's API" pattern as
everything else in this file.

- `sld.py`: `build_sld(zone)` turns a zone's real equipment fields
  (`module_detail`/`optimizer`/`inverter_detail`/`strings`/`mppt_count`/
  `sub_arrays`) into a module -> string -> inverter -> AC topology, the same
  underlying data already transcribed from the plant's real Single Line
  Diagrams (config/assets.yaml's own header comment) - not a scanned image
  of the original PDF (none is bundled in this repo). Only Jetty
  (`sub_arrays`) has a real per-string module count; GIS/ISB have no
  per-string survey, so their strings get `module_count` split as evenly as
  possible across (inverter x string) slots - flagged via
  `approximate_string_distribution`, same spirit as `panel_geometry.py`'s
  own GIS/ISB visualization approximation. Jetty's blocks use the sub-
  array's own real id (e.g. `"01A.L"`) rather than an assumed `"INV-N"`
  label, since config/assets.yaml doesn't record which physical inverter
  each sub-array is wired to.
- `irradiance_map.py`: `irradiance_grid()` builds a plant-wide lat/lon grid
  (`grid_points()`, spanning the same `target_bbox()` Module 1's cloud-tile
  fetch targets) and applies a cloud-attenuation factor to one shared clear-
  sky GHI value. Solar position/clear-sky GHI are computed ONCE at the
  plant's nominal center by the caller (reusing `clearsky.
  compute_clearsky_and_position()`, not duplicated here) rather than per
  grid point - a deliberate simplification, not a shortcut, since the 3
  zones span under ~2km and solar geometry is effectively identical across
  that distance (the same assumption `/sun-path/{zone}` already relies on).
  `cloud_factor` is a **documented synthetic placeholder** (deterministic
  sine-wave field seeded by grid position + timestamp, NOT a real Himawari
  sample) since no live cloud-tile store exists in this dev environment yet
  (Module 1's own "Known gaps" - MinIO/TimescaleDB rasters aren't
  accumulated/queryable here) - same convention as `nongfab_simulation.
  dev_data.synthetic_day_irradiance_temp()`. Swapping in a real
  - `cloud_factor_at(lat, lon, epoch_seconds)` (public, added for a spec
    gap closure) and `irradiance_at_point(...)`: the same model evaluated
    at one arbitrary point instead of a whole grid - Module 6's
    `/performance/{zone}` (Feature A's per-zone cloud-factor readout) and
    `/irradiance-map` (Feature E's zone-pin `ghi_w_m2`/`cloud_factor`, more
    accurate at a zone's own centroid than its nearest generic grid cell)
    both call these instead of duplicating the formula or re-deriving a
    nearest-grid-point lookup.
  `himawari_ingestion.sampling.sample_cloud_at()` call per grid point is a
  follow-up once Module 1 has a live raster store, not a redesign of this
  module's shape.

## Lunar position (Module 7's 3D view Moon marker, 2026-07-18)

`moon.py`'s `moon_position(when, latitude, longitude) -> (azimuth_deg,
elevation_deg)` - added for Solar3DPage's "Moon rises to replace the Sun
after sunset" feature (user request: "ตรง 3D ให้ทำดวงจันทร์เพิ่ม...มาขึ้นแทน
ดวงอาทิตย์ เมื่อดวงอาทิตย์ตกดินไปเเล้ว"). `clearsky.py` (this module's own
solar-position source) only computes solar position - there's no lunar
equivalent anywhere already installed in this project (checked: no
`ephem`/`skyfield`/`astropy` dependency exists). Rather than add a new
heavyweight ephemeris dependency for a decorative visual (`skyfield` needs
a downloaded JPL kernel file; `pyephem` is a C extension), this implements
Paul Schlyter's well-known compact algorithm ("How to Compute Planetary
Positions") directly in pure Python - geocentric ecliptic orbital
elements, the dominant ~13 solar-perturbation correction terms, then the
standard ecliptic → equatorial → topocentric-horizontal rotation chain
(the same final rotation step `clearsky.py` relies on pvlib for, on the
Sun's side).

**Honesty caveat, stated plainly in the module's own docstring**: this is
a low/medium-precision approximation (typically within roughly one degree
for the terms used here), not the same precision-audited pipeline pvlib
provides for the Sun. Sufficient for this scene's own decorative purpose
(a moon that visibly rises, arcs, and sets in roughly the right place) -
NOT meant to support anything needing arcminute-grade lunar accuracy
(eclipse/occultation timing, etc.). A real ephemeris library should
replace this, not extend it, if such a need ever arises.

Same `(azimuth_deg, elevation_deg)` convention as `clearsky.
compute_clearsky_and_position`'s solar position (azimuth clockwise from
North, elevation positive above horizon), so `api/routes_solar3d.py` and
the frontend can treat sun and moon positions identically. See
`api/README.md`'s and `web/README.md`'s matching dated entries for the
`/moon-path/{zone}` endpoint and the animated `MoonMarker` this feeds.

**Tested**: 5 invariant-based tests in `test_moon.py` (not
golden-value tests, since there's no independent reference ephemeris
available in this environment to compare against) - valid azimuth/
elevation ranges, naive-datetime-treated-as-UTC, smooth motion over 24h of
10-minute steps (catches a sign-flip/wraparound bug in the topocentric
rotation math), crosses the horizon within a 30h window from a
below-horizon start (proves it isn't returning a static reading), and
differs across a 7-day span (proves `when` isn't silently ignored). Manual
sanity check: a 48-hour print at Nong Fab's own coordinates showed
physically plausible moonrise (~03:00-04:00 UTC), a near-zenith transit
(~79-80° elevation around 09:00 UTC), moonset (~15:00-16:00 UTC), and the
correct ~1-hour daily lag shift on day 2 - consistent with real lunar
motion.

## Layout

```
src/nongfab_features/
  clearsky.py         compute_clearsky_and_position(), clear_sky_index()
  daytime_filter.py    filter_daytime()
  lag_features.py       add_auto_lags(), add_ema(), add_future_regressors()
  quality_control.py    flag_curtailment_or_degradation(), rolling_power_irradiance_correlation()
  framing.py             make_multistep_targets(), build_training_frame(), chronological_split()
  panel_geometry.py      generate_zone_layout() - per-zone 3D panel positions (Module 7 Feature B/C)
  shading.py              row_shaded_fraction(), zone_solar_access() - analytical row self-shading
  sld.py                    build_sld() - real-equipment-derived SLD topology (Module 7 Feature D)
  irradiance_map.py        grid_points(), irradiance_grid() - plant-wide irradiance grid (Module 7 Feature E)
  moon.py                   moon_position() - lunar azimuth/elevation for the 3D view's Moon marker
tests/                pytest suite, no external services or network needed
```

## Run locally

Depends on `nongfab-common` for `clearsky.nong_fab_site_location()` (the
plant's nominal center from `config/assets.yaml`, so callers don't hardcode
lat/lon themselves):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../libs/nongfab_common
pip install -e ".[dev]"
pytest -v
```

## Known gaps / next steps

- Not wired to a real data source yet — Module 1 (`cloud_obs`) only just
  started collecting live history, and Module 2 (NWP) isn't built. Once
  either has enough rows, a thin loader (query TimescaleDB → pandas
  DataFrame with the column names these functions expect) is the natural
  next step, not a redesign of this module.
- No persisted "feature store" table yet (the architecture doc mentions Feast
  or custom TimescaleDB tables as an option) — out of scope for this step,
  which was the pandas-level feature engineering pipeline specifically.
- `shading.py` models inter-row self-shading only - no obstacle survey
  (trees/structures) exists in `config/assets.yaml`, so external shading
  isn't modeled (not fabricated as zero, simply out of scope until a survey
  exists). `panel_geometry.py`'s GIS/ISB block layout is a visualization
  approximation (near-square factorization of `module_count`), not a claim
  about real physical string boundaries - only Jetty's layout is real.
