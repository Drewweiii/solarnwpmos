# Nong Fab Solar & Energy Management System (EMS)
## Enterprise Architecture Blueprint

**Site**: PTT LNG Terminal 2 Nong Fab, Rayong (12.6500°N, 101.1400°E)
**Purpose**: Multi-horizon solar forecasting + GTG dispatch/unit-commitment + 2D GIS dashboard + 3D simulation
**Stack**: Next.js 14 / FastAPI / TimescaleDB / PyTorch + LightGBM + NeuralProphet / Docker

---

## 0. ⚠️ Data & Capacity Reconciliation (READ FIRST)

The design prompt states **600 kW solar + 20 MW GTG**, but the engineering documents (SLD PPA25.0008)
show only **200.20 kWp installed** and **no GTG**. To avoid building on unverified numbers, all capacities
are **configuration-driven** (`config/plant.yaml`), seeded with verified SLD values:

| Site | Status | DC kWp | AC kW | DC/AC | Source |
|------|--------|--------|-------|-------|--------|
| ISB  | installed | 140.14 | 150 | 0.93 | SLD (verified) |
| GIS  | installed | 60.06 | 50 | 1.20 | SLD (verified — **clips**) |
| Site-3 | designed | TBD | TBD | TBD | to confirm |
| **Total installed** | | **200.20** | | | |
| Build-out target | claim | 600 (?) | | | **confirm** |
| GTG | claim | — | 20,000 (?) | | **confirm — not in SLD** |

> ACTION: replace the `600`/`20MW` placeholders in `config/plant.yaml` once confirmed.
> GIS site clips at 50 kW (DC/AC 1.20) → forecasting must be clip-aware (see §Module 1).

---

## 1. External Data Sources (verified, commercial-safe)

Because this is a commercial PTT system, prefer sources with clear usage rights over the
unverified `himawari.optemis.space`. The ingestion layer abstracts these behind a `Provider` interface.

### Satellite (cloud index / opacity — for minute-ahead)
| Provider | Access | Cadence | License notes |
|----------|--------|---------|---------------|
| **NOAA Open Data on AWS** (`noaa-himawari9`) | S3 (anonymous) | 10 min full-disk | Free & open, attribution required — **recommended default** |
| **JAXA P-Tree** | HTTP/SFTP (account) | 10 min | Commercial use allowed **from 2026-02-01**; earlier data research/edu only; no redistribution |
| **NREL NSRDB Himawari API** | REST CSV/JSON | 10 min (historical 2016–2020) | Great for **training/backtest**, not real-time |

### NWP (SSRD/temp/wind/RH — for hour & day-ahead)
| Provider | Access | Variable of interest | Notes |
|----------|--------|----------------------|-------|
| **NOAA GFS via NOMADS grib-filter** | HTTPS + GRIB2 | **DSWRF** (= SSRD), TMP, UGRD/VGRD, RH | Free; subregion + variable filter; parse with `cfgrib`/`wgrib2`; cycles 00/06/12/18Z |
| **Open-Meteo** | REST JSON | `shortwave_radiation`, `temperature_2m`, `wind_speed_10m`, `relative_humidity_2m` | Easiest integration; good fallback; check commercial terms |
| **ECMWF / commercial NWP** | licensed | SSRD | Higher accuracy for ops; paid |

**Good-practice for any ingestion**: respect `robots.txt`/ToS, cache the `.idx` inventory to fetch only
needed byte-ranges (GFS fast-download), rate-limit, store attribution, and record `issued_at` for every record.

GFS fast-download pattern (subregion around Rayong):
```
https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?
  file=gfs.tHHz.pgrb2.0p25.fFFF
  &var_DSWRF=on&var_TMP=on&var_UGRD=on&var_VGRD=on&var_RH=on
  &lev_surface=on&lev_2_m_above_ground=on&lev_10_m_above_ground=on
  &subregion=&leftlon=100&rightlon=102&toplat=13.5&bottomlat=12
  &dir=/gfs.YYYYMMDD/HH/atmos
```

---

## 2. Directory Structure

```
nongfab-ems/
├── config/
│   ├── plant.yaml                 # site capacities, coords, DC/AC, inverter limits (SEED FROM SLD)
│   └── settings.py                # pydantic-settings: DB URL, Redis, data-source keys
│
├── backend/                       # FastAPI service
│   ├── app/
│   │   ├── main.py                # app factory, CORS, lifespan (DB/Redis)
│   │   ├── api/v1/
│   │   │   ├── forecast.py        # /forecast dynamic router (Module 1)  ← code provided
│   │   │   ├── telemetry.py       # live SCADA/inverter read + ingest
│   │   │   ├── dispatch.py        # GTG net-load / spinning-reserve endpoints
│   │   │   └── evaluation.py      # RMSE/MAE/skill vs baseline (Module 5)
│   │   ├── db/
│   │   │   ├── base.py            # async engine/session
│   │   │   └── models.py          # SQLAlchemy 2.0 + TimescaleDB  ← code provided
│   │   ├── schemas/               # Pydantic v2  ← code provided
│   │   ├── ml/
│   │   │   ├── registry.py        # horizon → model handler map
│   │   │   ├── minute_ahead.py    # neuralforecast CNN-LSTM / DilatedRNN
│   │   │   ├── hour_ahead.py      # LightGBM
│   │   │   ├── day_ahead.py       # NeuralProphet
│   │   │   ├── conversion.py      # I→P (clip-aware for GIS), pvlib physical model
│   │   │   └── intervals.py       # PI: Sum-k LSTM / quantile / conformal
│   │   └── services/
│   │       └── reserve.py         # spinning-reserve & ramp-rate logic
│   └── tests/
│
├── data-pipeline/                 # Celery + Redis ETL (Module 2)
│   ├── providers.py               # Himawari / NWP / Telemetry providers  ← code provided
│   ├── tasks.py                   # celery beat: himawari(10m), nwp(6h), telemetry(1m)
│   └── worker.py
│
├── frontend/                      # Next.js 14 App Router
│   ├── app/
│   │   ├── (dashboard)/
│   │   │   ├── page.tsx           # 2D GIS control room (Module 3)
│   │   │   ├── dispatch/          # GTG net-load + zero-export guard
│   │   │   └── evaluation/        # model metrics + carbon/ROI (Module 5)
│   │   └── (simulation)/
│   │       └── 3d/page.tsx        # React Three Fiber sim (Module 4)
│   ├── components/
│   │   ├── map/GisHeatmap.tsx     # Leaflet/Mapbox + irradiance overlay + time slider
│   │   ├── charts/NetLoadChart.tsx# stacked: load / solar±PI / GTG
│   │   ├── three/SolarScene.tsx   # panels, sun path, dynamic shading
│   │   └── three/SldEditor.tsx    # stringing → downloadable SVG SLD
│   └── lib/api.ts
│
└── docker/
    ├── docker-compose.yml         # timescaledb, redis, backend, worker, frontend
    ├── Dockerfile.backend         # multi-stage py3.11
    └── Dockerfile.frontend        # multi-stage node
```

---

## 3. Module Design Summary

### Module 1 — Multi-Horizon Forecasting + Dynamic Router
- **minute-ahead (<120 min)**: neuralforecast CNN-LSTM/DilatedRNN with Himawari cloud index + motion vectors → feeds spinning-reserve/ramp alarms.
- **hour-ahead (1–6 h)**: LightGBM on NWP (DSWRF/T/wind/RH) + net-load lags → GTG fuel dispatch.
- **day-ahead (1–7 d)**: NeuralProphet (trend/seasonal/AR + future NWP regressors) → unit commitment.
- **Router**: single `/api/v1/forecast`, selects model by `horizon_type`.
- **Prediction Intervals**: p10/p90; sharper PI (Sum-k LSTM) ⇒ smaller reserve buffer ⇒ fuel saving.
- **Clip-aware conversion**: GIS uses `P = min(β·I + β0, inverter_ac_kw)`.

### Module 2 — ETL (Celery/TimescaleDB) — see `data-pipeline/providers.py`.
### Module 3 — 2D GIS + dispatch dashboard (Recharts + Leaflet/Mapbox).
### Module 4 — 3D mobile sim (R3F): sun path, dynamic shading, SLD SVG export.
### Module 5 — Evaluation + carbon/ROI (RMSE/MAE/skill vs persistence & linear; tCO2e; THB fuel saved).

### Evaluation rules (from CU case study — enforce in code)
- daytime only (solar zenith 0–85°); normalize by p5–p95 range, **not** installed capacity (degradation-safe);
- report per-hour and per-lead-time; probabilistic → PICP (coverage) + PINAW (width) + Winkler.
