import numpy as np
import pandas as pd

from nongfab_features.quality_control import flag_curtailment_or_degradation, rolling_power_irradiance_correlation


def _healthy_series(n=200, seed=0):
    rng = np.random.default_rng(seed)
    irradiance = np.clip(rng.normal(500, 200, n), 0, 1000)
    power = irradiance * 0.1 + rng.normal(0, 2, n)  # P tracks I closely
    return pd.DataFrame({"irradiance": irradiance, "power": power})


def test_healthy_plant_is_not_flagged():
    df = _healthy_series()
    flags = flag_curtailment_or_degradation(df, "irradiance", "power", window=50, min_periods=20)

    # allow a few false positives at the very start where the rolling window is thin,
    # but the plant should be overwhelmingly "not flagged" once warmed up
    assert flags.iloc[50:].mean() < 0.05


def test_decoupled_but_still_varying_power_gets_flagged_via_low_correlation():
    df = _healthy_series(n=300)
    rng = np.random.default_rng(1)
    # power stops tracking irradiance but keeps varying (e.g. an intermittent fault),
    # not a hard flatline - exercises the correlation path specifically
    df.loc[150:250, "power"] = rng.normal(50, 10, 101)

    flags = flag_curtailment_or_degradation(df, "irradiance", "power", window=50, min_periods=20, corr_threshold=0.5)

    assert flags.iloc[220:250].mean() > 0.5  # solidly inside the decoupled window, well warmed up


def test_flatlined_power_gets_flagged_despite_undefined_correlation():
    df = _healthy_series(n=300)
    # hard curtailment cap: power pinned constant while irradiance keeps varying -
    # correlation is undefined (zero variance), must still be flagged
    df.loc[150:250, "power"] = 5.0

    flags = flag_curtailment_or_degradation(df, "irradiance", "power", window=50, min_periods=20, corr_threshold=0.5)

    assert flags.iloc[220:250].mean() > 0.5  # solidly inside the flatlined window, well warmed up


def test_rolling_correlation_is_nan_before_min_periods():
    df = _healthy_series(n=10)
    corr = rolling_power_irradiance_correlation(df, "irradiance", "power", window=50, min_periods=20)
    assert corr.isna().all()


def test_flag_treats_insufficient_history_as_not_flagged():
    df = _healthy_series(n=10)
    flags = flag_curtailment_or_degradation(df, "irradiance", "power", window=50, min_periods=20)
    assert not flags.any()
