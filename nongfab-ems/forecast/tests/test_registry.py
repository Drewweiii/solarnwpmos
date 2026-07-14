from dataclasses import dataclass

import pytest

from nongfab_forecast import registry


@dataclass
class _DummyModel:
    """Stands in for HourAheadModel/MinuteAheadModel/DayAheadModel - registry.py
    is deliberately structure-agnostic (cloudpickles whatever's passed in), so a
    plain dataclass is enough to exercise it without training a real model.
    """

    coefficient: float
    label: str


@pytest.fixture(autouse=True)
def isolated_tracking_uri(tmp_path, monkeypatch):
    """Every test gets its own sqlite file - registrations from one test must
    never leak into another (registered_model_name is shared across a whole
    test session's -horizon-zone- combination otherwise).
    """
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")


def test_log_run_registers_first_version_as_1():
    model = _DummyModel(coefficient=0.5, label="v1")
    run_id, version = registry.log_run("hour", "GIS", model, params={"num_leaves": 16}, metrics={"rmse": 4.2})

    assert version == 1
    assert run_id


def test_log_run_increments_version_on_second_call():
    registry.log_run("hour", "ISB", _DummyModel(0.1, "v1"), params={}, metrics={"rmse": 5.0})
    _run_id, version2 = registry.log_run("hour", "ISB", _DummyModel(0.2, "v2"), params={}, metrics={"rmse": 4.0})

    assert version2 == 2


def test_load_model_latest_returns_most_recently_logged_object():
    registry.log_run("day", "Jetty", _DummyModel(1.0, "first"), params={}, metrics={"mae": 10.0})
    registry.log_run("day", "Jetty", _DummyModel(2.0, "second"), params={}, metrics={"mae": 8.0})

    loaded = registry.load_model("day", "Jetty", version="latest")
    assert loaded.label == "second"
    assert loaded.coefficient == 2.0


def test_load_model_specific_version():
    registry.log_run("minute", "GIS", _DummyModel(1.0, "first"), params={}, metrics={})
    registry.log_run("minute", "GIS", _DummyModel(2.0, "second"), params={}, metrics={})

    loaded_v1 = registry.load_model("minute", "GIS", version=1)
    assert loaded_v1.label == "first"


def test_load_model_raises_for_unknown_registration():
    with pytest.raises(ValueError):
        registry.load_model("hour", "NoSuchZone", version="latest")


def test_compare_versions_returns_one_row_per_version_with_metrics():
    registry.log_run("hour", "Jetty", _DummyModel(0.1, "a"), params={}, metrics={"rmse": 5.0, "mae": 3.0})
    registry.log_run("hour", "Jetty", _DummyModel(0.2, "b"), params={}, metrics={"rmse": 4.0, "mae": 2.5})

    table = registry.compare_versions("hour", "Jetty")

    assert list(table.index) == [1, 2]
    assert table.loc[1, "rmse"] == pytest.approx(5.0)
    assert table.loc[2, "rmse"] == pytest.approx(4.0)
    assert table.loc[2, "rmse"] < table.loc[1, "rmse"]  # the newer version is the better one here


def test_compare_versions_raises_for_unknown_registration():
    with pytest.raises(ValueError):
        registry.compare_versions("day", "NoSuchZone")
