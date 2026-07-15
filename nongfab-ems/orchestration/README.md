# Cross-cutting — Prefect Orchestration

STEP 10. Prefect flows that orchestrate the ingestion (Module 1/2) ->
retrain (Module 4) pipeline. This package doesn't reimplement any fetching
or training logic - every flow is a thin wrapper that constructs the same
objects each module's own `main.py` does and calls the same functions
(`IngestionJob.run_once()`, `nongfab_forecast.training.train_now()`), so
behavior can never drift between "run via a module's own daemon" and "run
via a Prefect flow."

## Why this exists alongside each module's own scheduler

Module 1 (`ingestion/himawari`) and Module 2 (`ingestion/nwp`) already have
their own standalone scheduling: `main.py` starts an `AsyncIOScheduler`
(APScheduler) that calls `IngestionJob.run_once()` on a cron trigger,
forever, in-process. That still works unchanged and is the simplest way to
run either module standalone (see each module's own README).

What that setup *can't* do is coordinate across modules: there's no
existing "ingestion finished, now retrain" link anywhere in the codebase.
`full_pipeline_flow()` (`retrain_flows.py`) is that link - it runs both
ingestion flows, then retrains every zone/horizon model, with per-step
failure isolation (one bad zone/horizon or a down data source doesn't
block the rest). There's no separate "features" flow: Module 3
(`features/`) is a shared library Module 4's training functions already
call internally, not an independently schedulable job.

## Layout

- `ingestion_flows.py` - `himawari_ingestion_flow()`, `nwp_ingestion_flow()`.
  Each builds an `httpx.AsyncClient` + async SQLAlchemy engine + the same
  `RateLimiter`/datasource/`RawObjectStorage`/`TimescaleWriter`/
  `IngestionJob` wiring as that module's own `main.py`, calls
  `job.run_once()` exactly once, and translates `job.last_error` into
  either a raised exception (so Prefect marks the flow run Failed) or a
  clean result dict.
- `retrain_flows.py` - `retrain_flow(zone, horizon)` wraps
  `nongfab_forecast.training.train_now()`; `retrain_all_flow()` calls it
  for every zone x horizon combination (isolating failures per
  combination); `full_pipeline_flow()` chains ingestion -> retrain.
- `deploy.py` - `nongfab-orchestration-serve` console script. Registers all
  three flows as long-lived Prefect deployments via `serve()`, each on a
  schedule derived from the *same* settings each module's own scheduler
  reads (`himawari_ingestion`'s `poll_interval_minutes`,
  `nwp_ingestion`'s `gfs_cycles`/`publish_latency_minutes`) - not
  hardcoded/duplicated cron strings that could drift from those modules'
  own defaults.

## Run locally

```bash
cd orchestration
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v                          # -m "not slow" to skip the real training round trip
```

Ad hoc, one-off flow runs (no server, no deployment/schedule needed):

```python
import asyncio
from nongfab_orchestration import himawari_ingestion_flow, retrain_flow

asyncio.run(himawari_ingestion_flow())
retrain_flow("GIS", "hour")
```

Long-lived, scheduled (an alternative to each ingestion module's own
`python -m himawari_ingestion.main` / `python -m nwp_ingestion.main`):

```bash
nongfab-orchestration-serve
```

This needs a Prefect API to report to. With no `PREFECT_API_URL` configured,
Prefect runs a local ephemeral server automatically (SQLite-backed, no
extra setup) - fine for dev/demo. A real deployment should point
`PREFECT_API_URL` at a real Prefect server/Prefect Cloud instead so flow
runs survive a container restart and are visible outside this one process.

## A real packaging bug this module caught

Building this module's test venv (`pip install ./libs/nongfab_common
./ingestion/himawari ./ingestion/nwp ./orchestration`, all non-editable, to
avoid re-installing forecast/'s already-installed heavy ML stack) silently
**broke** `forecast/`'s own already-passing test suite: 10 tests started
failing with `FileNotFoundError: config/assets.yaml`.

Cause: `nongfab_common.assets.load_assets()`'s fallback path is
`Path(__file__).resolve().parents[4] / "config" / "assets.yaml"` - correct
for an *editable* install (where `__file__` still points at the real
source tree), but wrong once a regular `pip install .` copies the package
into `site-packages` at a different depth. Reinstalling `nongfab-common`
non-editably into `forecast/.venv` (a venv that already had a working
editable install of it) silently downgraded that resolution for every
other package sharing the same venv - not just the newly-added ones.

Fixed by reinstalling `nongfab-common` back into `forecast/.venv` with
`pip install -e`, and by setting `NONGFAB_ASSETS_PATH` explicitly in this
package's own `tests/conftest.py` (`os.environ.setdefault(...)`, so a real
`.env`/CI setting always wins) so this module's own tests don't depend on
every dependency being editable-installed in whatever venv runs them. This
is the same env var `api/Dockerfile` already sets for the same underlying
reason (a non-editable production install can't rely on `__file__` depth).
**Lesson for future changes to this repo**: installing one module's
sibling dependency non-editably into a venv that other modules also use
can silently break those other modules' path-resolution fallbacks - prefer
a dedicated venv per module (as the rest of this repo already does) over
sharing one across modules for convenience.

## Known gaps

- No Docker daemon in the sandbox that built this, so `full_pipeline_flow()`
  is verified against fakes/mocks for the ingestion half (real MinIO/
  TimescaleDB connections aren't available here) plus one real end-to-end
  run for the retrain half (`retrain_flow("GIS", "hour")`, marked `slow`,
  same convention as `forecast/`'s own slow tests) - see `tests/`.
- `deploy.py`'s `serve()` itself (the long-lived scheduled-deployment path)
  isn't live-verified for the same reason - the flow *functions* it wires
  up are (see above).
- No orchestration-level retry/backoff policy configured yet beyond what
  each flow's own try/except already does - Prefect supports per-task/flow
  retries (`@flow(retries=...)`) if a real deployment needs them; not added
  speculatively here.
