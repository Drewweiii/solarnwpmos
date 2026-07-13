from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from himawari_ingestion.schemas import CloudObservation, RawFetchResult


def test_valid_observation_roundtrips():
    obs = CloudObservation(
        observed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        latitude=12.71,
        longitude=101.15,
        cloud_opacity_pct=42.0,
        cloud_index=0.5,
        source="mock-fixture",
    )
    assert obs.cloud_opacity_pct == 42.0


def test_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        CloudObservation(
            observed_at=datetime(2024, 1, 1),  # no tzinfo
            latitude=12.71,
            longitude=101.15,
            cloud_opacity_pct=42.0,
            cloud_index=0.5,
            source="mock-fixture",
        )


@pytest.mark.parametrize("field,value", [("cloud_opacity_pct", -1), ("cloud_opacity_pct", 101), ("cloud_index", -1), ("cloud_index", 2)])
def test_rejects_out_of_range_values(field, value):
    kwargs = dict(
        observed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        latitude=12.71,
        longitude=101.15,
        cloud_opacity_pct=42.0,
        cloud_index=0.5,
        source="mock-fixture",
    )
    kwargs[field] = value
    with pytest.raises(ValidationError):
        CloudObservation(**kwargs)


def test_raw_fetch_result_object_key_is_stable_for_same_body():
    fetched_at = datetime(2024, 1, 1, 12, 30, 45, tzinfo=timezone.utc)
    a = RawFetchResult(url="mock://x", fetched_at=fetched_at, content_type="application/json", body=b"hello")
    b = RawFetchResult(url="mock://x", fetched_at=fetched_at, content_type="application/json", body=b"hello")
    assert a.object_key == b.object_key
    assert a.object_key.startswith("himawari/2024/01/01/123045-")


def test_raw_fetch_result_object_key_differs_for_different_body():
    fetched_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    a = RawFetchResult(url="mock://x", fetched_at=fetched_at, content_type="application/json", body=b"hello")
    b = RawFetchResult(url="mock://x", fetched_at=fetched_at, content_type="application/json", body=b"world")
    assert a.object_key != b.object_key
