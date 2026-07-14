import os

import pytest

from himawari_ingestion.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        source_mode="mock",
        min_seconds_between_requests=0.0,
        max_retry_attempts=2,
        retry_backoff_base_seconds=0.01,
        retry_backoff_max_seconds=0.05,
        request_timeout_seconds=2.0,
    )


@pytest.fixture
def timescale_test_dsn() -> str:
    dsn = os.environ.get("TIMESCALE_TEST_DSN")
    if not dsn:
        pytest.skip("set TIMESCALE_TEST_DSN to run integration tests against a real TimescaleDB")
    return dsn


@pytest.fixture
def require_live_noaa() -> None:
    if os.environ.get("RUN_LIVE_NOAA_TESTS") != "1":
        pytest.skip("set RUN_LIVE_NOAA_TESTS=1 to run integration tests against the real NOAA S3 bucket (slow, ~30-90s)")
