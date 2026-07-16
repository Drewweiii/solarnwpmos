import os

import pytest

from pvgis_ingestion.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        source_mode="mock",
        max_retry_attempts=2,
        retry_backoff_base_seconds=0.01,
        retry_backoff_max_seconds=0.05,
        request_timeout_seconds=2.0,
    )


@pytest.fixture
def pvgis_live_test_enabled() -> bool:
    return os.environ.get("PVGIS_LIVE_TEST") == "1"
