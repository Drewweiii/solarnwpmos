import pytest

from nongfab_forecast.serving import (
    FALLBACK_PI_HALF_WIDTH_PCT,
    ModelNotTrainedError,
    UnknownHorizonError,
    UnknownZoneError,
    get_forecast_with_fallback,
    get_latest_forecast,
    validate_horizon,
    validate_zone,
)


def test_validate_zone_accepts_known_zones():
    for zone in ("GIS", "ISB", "Jetty"):
        assert validate_zone(zone) == zone


def test_validate_zone_rejects_unknown_zone():
    with pytest.raises(UnknownZoneError):
        validate_zone("Nowhere")


def test_validate_horizon_accepts_known_horizons():
    for horizon in ("minute", "hour", "day"):
        assert validate_horizon(horizon) == horizon


def test_validate_horizon_rejects_unknown_horizon():
    with pytest.raises(UnknownHorizonError):
        validate_horizon("century")


def test_get_latest_forecast_raises_model_not_trained_when_none_registered(tmp_path, monkeypatch):
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    with pytest.raises(ModelNotTrainedError):
        get_latest_forecast("GIS", "hour")


def test_get_latest_forecast_validates_before_touching_mlflow():
    # unknown zone/horizon should raise immediately, without needing a valid
    # MLflow tracking URI configured at all
    with pytest.raises(UnknownZoneError):
        get_latest_forecast("Nowhere", "hour")
    with pytest.raises(UnknownHorizonError):
        get_latest_forecast("GIS", "century")


def test_get_forecast_with_fallback_gives_the_physics_baseline_a_bounded_pi(tmp_path, monkeypatch):
    """2026-07-16: the user asked for *some* prediction-interval band on the
    dashboard even while running the no-ML physics fallback (previously
    lower/upper were always None here - see FALLBACK_PI_HALF_WIDTH_PCT's own
    docstring for why this is a fixed approximation, not a real PI)."""
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    result = get_forecast_with_fallback("GIS", "hour")
    assert result.model_type == "physics_baseline"
    for point in result.points:
        assert point.lower is not None
        assert point.upper is not None
        assert point.lower <= point.pred <= point.upper
        assert point.lower == pytest.approx(max(0.0, point.pred * (1 - FALLBACK_PI_HALF_WIDTH_PCT)))
        assert point.upper == pytest.approx(point.pred * (1 + FALLBACK_PI_HALF_WIDTH_PCT))
