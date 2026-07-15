from datetime import date

import pytest
from pydantic import ValidationError

from nasa_power_ingestion.schemas import RawFetchResult, UVObservation


def test_uv_observation_accepts_valid_data():
    obs = UVObservation(observation_date=date(2026, 7, 1), latitude=12.71, longitude=101.15, uv_index=8.9, source="test")
    assert obs.uv_index == 8.9


def test_uv_observation_rejects_missing_sentinel():
    with pytest.raises(ValidationError):
        UVObservation(observation_date=date(2026, 7, 1), latitude=12.71, longitude=101.15, uv_index=-999.0, source="test")


@pytest.mark.parametrize("bad_lat", [-91.0, 91.0])
def test_uv_observation_rejects_out_of_range_latitude(bad_lat):
    with pytest.raises(ValidationError):
        UVObservation(observation_date=date(2026, 7, 1), latitude=bad_lat, longitude=101.15, uv_index=5.0, source="test")


def test_raw_fetch_result_object_key_is_stable_and_namespaced():
    raw = RawFetchResult(url="mock://x", fetched_at="2026-07-15T12:00:00+00:00", content_type="application/json", body=b'{"a":1}')
    assert raw.object_key.startswith("nasa-power/2026/07/15/120000-")
    assert raw.object_key.endswith(".json")
