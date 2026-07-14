from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nwp_ingestion.schemas import NWPForecastPoint, RawFetchResult


def _valid_point_kwargs(**overrides):
    kwargs = dict(
        issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
        valid_time=datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
        latitude=12.71,
        longitude=101.15,
        ssrd_w_m2=500.0,
        temp2m_c=28.0,
        wind10m_u_ms=2.0,
        wind10m_v_ms=-1.5,
        relative_humidity_pct=70.0,
        source="test-source",
    )
    kwargs.update(overrides)
    return kwargs


def test_nwp_forecast_point_accepts_valid_data():
    point = NWPForecastPoint(**_valid_point_kwargs())
    assert point.ssrd_w_m2 == 500.0
    assert point.issue_time.tzinfo is not None


def test_nwp_forecast_point_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        NWPForecastPoint(**_valid_point_kwargs(issue_time=datetime(2026, 7, 14, 0)))


def test_nwp_forecast_point_normalizes_to_utc():
    from datetime import timedelta

    tz7 = timezone(timedelta(hours=7))
    point = NWPForecastPoint(**_valid_point_kwargs(valid_time=datetime(2026, 7, 14, 8, tzinfo=tz7)))
    assert point.valid_time == datetime(2026, 7, 14, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("ssrd_w_m2", -1.0),
        ("ssrd_w_m2", 2000.0),
        ("temp2m_c", 100.0),
        ("relative_humidity_pct", -5.0),
        ("relative_humidity_pct", 200.0),
        ("latitude", 200.0),
        ("longitude", -400.0),
    ],
)
def test_nwp_forecast_point_rejects_out_of_range_values(field, bad_value):
    with pytest.raises(ValidationError):
        NWPForecastPoint(**_valid_point_kwargs(**{field: bad_value}))


def test_raw_fetch_result_object_key_is_stable_and_namespaced():
    raw = RawFetchResult(
        url="https://example.test/grib",
        fetched_at=datetime(2026, 7, 14, 4, 5, 6, tzinfo=timezone.utc),
        content_type="application/x-grib2",
        body=b"fake-grib-bytes",
        issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
        forecast_hour=3,
    )
    key1 = raw.object_key
    key2 = raw.object_key
    assert key1 == key2  # deterministic (hash-based, not fetched_at-based for the hash part)
    assert key1.startswith("nwp/2026/07/14/00/f003-")
    assert key1.endswith(".grib2")
