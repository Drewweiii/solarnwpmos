"""Prefect flows wrapping Module 4's training.train_now() - the same
function the dev API's POST /train-now/{zone}/{horizon} route
(forecast/src/nongfab_forecast/api.py) calls, so this flow and that route
never drift apart in behavior.

`full_pipeline_flow` is the "orchestrate the ingestion -> forecast pipeline"
piece STEP 10 asked for: it runs Module 1/2's ingestion flows, then
retrains every zone x horizon combination. There's no separate "features"
step here since Module 3 (features/) is a shared library Module 4's
training functions already call internally, not an independently
schedulable job of its own.
"""

from __future__ import annotations

from typing import Any

from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_forecast.serving import VALID_HORIZONS
from nongfab_forecast.training import train_now
from prefect import flow, get_run_logger

from .ingestion_flows import himawari_ingestion_flow, nwp_ingestion_flow


@flow(name="retrain-zone-horizon")
def retrain_flow(zone: str, horizon: str) -> dict[str, Any]:
    logger = get_run_logger()
    result = train_now(zone, horizon)
    logger.info("retrained %s/%s -> version %d (run_id=%s)", result.zone, result.horizon, result.model_version, result.run_id)
    return {
        "zone": result.zone, "horizon": result.horizon, "run_id": result.run_id,
        "model_version": result.model_version, "metrics": result.metrics,
    }


@flow(name="retrain-all")
def retrain_all_flow() -> list[dict[str, Any]]:
    """Retrains every (zone, horizon) combination. Failures are isolated per
    combination - one zone/horizon's training failure doesn't block the
    other 8 (mirrors IngestionJob.run_once()'s own "a scheduled job must
    never crash the process" philosophy).
    """
    logger = get_run_logger()
    results = []
    for zone in sorted(nong_fab_zone_capacities_kwp()):
        for horizon in VALID_HORIZONS:
            try:
                results.append(retrain_flow(zone, horizon))
            except Exception as exc:  # noqa: BLE001 - one bad zone/horizon must not abort the rest
                logger.error("retrain failed for %s/%s: %s", zone, horizon, exc)
                results.append({"zone": zone, "horizon": horizon, "error": str(exc)})
    return results


@flow(name="full-pipeline")
async def full_pipeline_flow() -> dict[str, Any]:
    """Orchestrates the ingestion (Module 1/2) -> retrain (Module 4)
    pipeline end to end: fetch the latest cloud observation + NWP forecast,
    then retrain every zone/horizon model. Ingestion failures are logged but
    don't block retraining - the forecast models train against synthetic
    data regardless (see training.py's own "no real accumulated history
    yet" caveat), so a bad ingestion cycle shouldn't also block retraining.
    """
    logger = get_run_logger()
    ingestion_results = []
    for ingestion_flow in (himawari_ingestion_flow, nwp_ingestion_flow):
        try:
            ingestion_results.append(await ingestion_flow())
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.error("ingestion flow %s failed: %s", ingestion_flow.name, exc)
            ingestion_results.append({"source": ingestion_flow.name, "ok": False, "error": str(exc)})

    retrain_results = retrain_all_flow()
    return {"ingestion": ingestion_results, "retrain": retrain_results}
