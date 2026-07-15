from __future__ import annotations

import pytest
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_forecast.serving import VALID_HORIZONS
from nongfab_forecast.training import TrainResult

from nongfab_orchestration import retrain_flows


@pytest.mark.slow
def test_retrain_flow_real_hour_ahead_round_trip(tmp_path, monkeypatch):
    """Real end-to-end round trip (no mocking) - trains a real (tiny)
    LightGBM model and registers it with MLflow, same as forecast/'s own
    slow-marked API tests, just entered through the Prefect flow instead of
    the dev API route.
    """
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")

    result = retrain_flows.retrain_flow("GIS", "hour")

    assert result["zone"] == "GIS"
    assert result["horizon"] == "hour"
    assert result["model_version"] == 1
    assert "rmse" in result["metrics"]


def test_retrain_all_flow_isolates_a_single_zone_horizon_failure(monkeypatch):
    def fake_train_now(zone: str, horizon: str) -> TrainResult:
        if (zone, horizon) == ("Jetty", "minute"):
            raise RuntimeError("boom")
        return TrainResult(zone=zone, horizon=horizon, run_id="run-x", model_version=1, metrics={"rmse": 1.0})

    monkeypatch.setattr(retrain_flows, "train_now", fake_train_now)

    results = retrain_flows.retrain_all_flow()

    expected_total = len(nong_fab_zone_capacities_kwp()) * len(VALID_HORIZONS)
    assert len(results) == expected_total

    failed = [r for r in results if "error" in r]
    assert failed == [{"zone": "Jetty", "horizon": "minute", "error": "boom"}]
    assert len(results) - len(failed) == expected_total - 1


async def test_full_pipeline_flow_runs_retrain_even_if_ingestion_fails(monkeypatch):
    async def failing_himawari():
        raise RuntimeError("himawari down")

    failing_himawari.name = "himawari-ingestion"

    async def ok_nwp():
        return {"source": "nwp", "ok": True, "error": None, "fetched_at": "2026-07-15T00:00:00+00:00"}

    ok_nwp.name = "nwp-ingestion"

    retrain_calls = []

    def fake_retrain_all():
        retrain_calls.append(True)
        return [{"zone": "GIS", "horizon": "hour", "run_id": "run-x", "model_version": 1, "metrics": {}}]

    monkeypatch.setattr(retrain_flows, "himawari_ingestion_flow", failing_himawari)
    monkeypatch.setattr(retrain_flows, "nwp_ingestion_flow", ok_nwp)
    monkeypatch.setattr(retrain_flows, "retrain_all_flow", fake_retrain_all)

    result = await retrain_flows.full_pipeline_flow()

    assert retrain_calls == [True]
    assert result["ingestion"][0]["ok"] is False
    assert "himawari down" in result["ingestion"][0]["error"]
    assert result["ingestion"][1]["ok"] is True
    assert result["retrain"] == [{"zone": "GIS", "horizon": "hour", "run_id": "run-x", "model_version": 1, "metrics": {}}]
