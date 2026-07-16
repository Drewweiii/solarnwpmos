from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pvgis_ingestion.schemas import PVGISHourlyPoint


def _valid_kwargs(**overrides) -> dict:
    kwargs = dict(
        valid_time=datetime(2020, 1, 1, 0, 30, tzinfo=timezone.utc),
        issue_time=datetime(2020, 1, 1, 0, 30, tzinfo=timezone.utc),
        latitude=12.6834,
        longitude=101.1199,
        ssrd_w_m2=122.75,
        temp2m_c=24.79,
        wind10m_u_ms=4.0,
        wind10m_v_ms=0.0,
        relative_humidity_pct=70.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_pvgis_hourly_point_accepts_valid_data():
    point = PVGISHourlyPoint(**_valid_kwargs())
    assert point.source == "pvgis-era5"  # default SOURCE_NAME


def test_pvgis_hourly_point_rejects_naive_datetimes():
    with pytest.raises(ValidationError):
        PVGISHourlyPoint(**_valid_kwargs(valid_time=datetime(2020, 1, 1, 0, 30)))


def test_pvgis_hourly_point_rejects_out_of_range_irradiance():
    with pytest.raises(ValidationError):
        PVGISHourlyPoint(**_valid_kwargs(ssrd_w_m2=-5.0))
