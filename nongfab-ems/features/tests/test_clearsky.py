import numpy as np
import pandas as pd
import pytest

from nongfab_features.clearsky import clear_sky_index, compute_clearsky_and_position, nong_fab_site_location

NONG_FAB_LAT = 12.71
NONG_FAB_LON = 101.15


def _day_index():
    return pd.date_range("2026-07-14 00:00", periods=24 * 6, freq="10min", tz="UTC")


def test_nong_fab_site_location_matches_config_assets_yaml():
    lat, lon = nong_fab_site_location()
    assert lat == pytest.approx(NONG_FAB_LAT)
    assert lon == pytest.approx(NONG_FAB_LON)


def test_compute_clearsky_and_position_returns_expected_columns():
    idx = _day_index()
    result = compute_clearsky_and_position(idx, NONG_FAB_LAT, NONG_FAB_LON)

    assert list(result.columns) == ["ghi_clearsky", "dni_clearsky", "dhi_clearsky", "zenith_deg", "elevation_deg", "azimuth_deg"]
    assert len(result) == len(idx)
    assert (result["ghi_clearsky"] >= 0).all()


def test_compute_clearsky_and_position_requires_tz_aware_index():
    naive_idx = pd.date_range("2026-07-14 00:00", periods=10, freq="10min")
    with pytest.raises(ValueError):
        compute_clearsky_and_position(naive_idx, NONG_FAB_LAT, NONG_FAB_LON)


def test_clearsky_ghi_is_zero_at_night_and_positive_at_midday():
    idx = _day_index()
    result = compute_clearsky_and_position(idx, NONG_FAB_LAT, NONG_FAB_LON)

    night_utc = result.loc["2026-07-14 18:00", "ghi_clearsky"]  # ~01:00 local (UTC+7) - the middle of the night
    midday_utc = result.loc["2026-07-14 06:00", "ghi_clearsky"]  # ~13:00 local - full sun

    assert night_utc == pytest.approx(0, abs=1.0)
    assert midday_utc > 500


def test_clear_sky_index_is_about_one_under_clear_conditions():
    ghi_clearsky = pd.Series([0.0, 200.0, 800.0, 900.0])
    ghi_measured = ghi_clearsky.copy()  # perfectly clear
    csi = clear_sky_index(ghi_measured, ghi_clearsky)

    assert np.isnan(csi.iloc[0])  # night (clearsky ~0) -> NaN, not divide-by-zero garbage
    assert csi.iloc[1:].apply(lambda v: v == pytest.approx(1.0)).all()


def test_clear_sky_index_reflects_cloud_attenuation_and_clips():
    ghi_clearsky = pd.Series([900.0, 900.0])
    ghi_measured = pd.Series([450.0, 2000.0])  # 50% cloud attenuation, then an outlier spike
    csi = clear_sky_index(ghi_measured, ghi_clearsky, clip_max=2.0)

    assert csi.iloc[0] == pytest.approx(0.5)
    assert csi.iloc[1] == pytest.approx(2.0)  # clipped, not left at ~2.22
