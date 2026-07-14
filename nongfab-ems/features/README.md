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
