import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from nwp_ingestion.config import Settings
from nwp_ingestion.datasource import (
    MockNWPDataSource,
    NomadsGfsDataSource,
    _build_filter_url,
    _decode_grib_sync,
    _most_recent_published_cycle,
)
from nwp_ingestion.geolocation import FetchBBox

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample_gfs_nongfab.grib2"


def test_build_filter_url_contains_expected_gfs_filter_params():
    settings = Settings(source_mode="mock")
    cycle = datetime(2026, 7, 14, 0, tzinfo=timezone.utc)
    bbox = FetchBBox(lat_min=12.3, lat_max=13.0, lon_min=100.8, lon_max=101.5)

    url = _build_filter_url(settings, cycle, forecast_hour=3, bbox=bbox)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.netloc == "nomads.ncep.noaa.gov"
    assert parsed.path == "/cgi-bin/filter_gfs_0p25.pl"
    assert params["file"] == ["gfs.t00z.pgrb2.0p25.f003"]
    assert params["dir"] == ["/gfs.20260714/00/atmos"]
    assert params["var_DSWRF"] == ["on"]
    assert params["var_TMP"] == ["on"]
    assert params["var_UGRD"] == ["on"]
    assert params["var_VGRD"] == ["on"]
    assert params["var_RH"] == ["on"]
    assert params["toplat"] == ["13.0"]
    assert params["bottomlat"] == ["12.3"]
    assert params["leftlon"] == ["100.8"]
    assert params["rightlon"] == ["101.5"]


@pytest.mark.parametrize(
    "now,cycles,latency_minutes,expected",
    [
        # normal case: 05:00 anchor(-4h)=01:00 -> most recent cycle <= 01:00 among [0,6,12,18] is 00:00
        (datetime(2026, 7, 14, 5, 0, tzinfo=timezone.utc), [0, 6, 12, 18], 240, datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc)),
        # crosses midnight backward: anchor lands on the previous day
        (datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc), [0, 6, 12, 18], 240, datetime(2026, 7, 13, 18, 0, tzinfo=timezone.utc)),
        # fallback branch: 0 is not a configured cycle hour, anchor before the day's first cycle
        (datetime(2026, 7, 14, 5, 0, tzinfo=timezone.utc), [6, 12, 18], 240, datetime(2026, 7, 13, 18, 0, tzinfo=timezone.utc)),
    ],
)
def test_most_recent_published_cycle(now, cycles, latency_minutes, expected):
    assert _most_recent_published_cycle(now, cycles, latency_minutes) == expected


def test_decode_grib_sync_extracts_expected_fields_from_real_sample():
    """FIXTURE_PATH is a real ~1KB GRIB2 subset fetched live from NOAA NOMADS
    (gfs.20260714/00z, f001) around Nong Fab - not a synthetic/fabricated file.
    """
    grib_bytes = FIXTURE_PATH.read_bytes()
    point = _decode_grib_sync(grib_bytes, target_lat=12.71, target_lon=101.15, source_label="test")

    assert point.issue_time == datetime(2026, 7, 14, 0, tzinfo=timezone.utc)
    assert point.valid_time == datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
    # nearest 0.25deg grid point to (12.71, 101.15)
    assert point.latitude == pytest.approx(12.75)
    assert point.longitude == pytest.approx(101.25)
    assert point.ssrd_w_m2 == pytest.approx(16.56, abs=0.5)
    assert point.temp2m_c == pytest.approx(25.61, abs=0.5)
    assert point.wind10m_u_ms == pytest.approx(2.66, abs=0.5)
    assert point.wind10m_v_ms == pytest.approx(1.95, abs=0.5)
    assert point.relative_humidity_pct == pytest.approx(84.3, abs=0.5)
    assert point.source == "test"


@pytest.mark.asyncio
async def test_mock_datasource_returns_one_pair_per_configured_forecast_hour():
    settings = Settings(source_mode="mock")
    source = MockNWPDataSource(settings, fixture_path=FIXTURE_PATH, forecast_hours=[1, 2, 3])

    pairs = await source.fetch_latest_cycle()

    assert len(pairs) == 3
    for raw, point in pairs:
        assert raw.content_type == "application/x-grib2"
        assert point.source == "mock-fixture"


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("NWP_LIVE_TEST") != "1", reason="set NWP_LIVE_TEST=1 to hit the real NOMADS filter service")
@pytest.mark.asyncio
async def test_nomads_gfs_datasource_against_real_nomads():
    import httpx

    from nwp_ingestion.compliance import RateLimiter

    settings = Settings(source_mode="http", forecast_hours=[1])
    async with httpx.AsyncClient() as client:
        source = NomadsGfsDataSource(settings, client, RateLimiter(settings.min_seconds_between_requests))
        pairs = await source.fetch_latest_cycle()

    assert len(pairs) == 1
    raw, point = pairs[0]
    assert point.source == NomadsGfsDataSource.SOURCE_NAME
    assert 0 <= point.ssrd_w_m2 <= 1500
