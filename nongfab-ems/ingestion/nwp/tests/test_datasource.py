import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from nwp_ingestion.compliance import RateLimiter
from nwp_ingestion.config import Settings
from nwp_ingestion.datasource import (
    MockNWPDataSource,
    NomadsGfsDataSource,
    S3GfsBackfillDataSource,
    _build_filter_url,
    _byte_range_for_field,
    _decode_grib_sync,
    _decode_single_field_grib_sync,
    _most_recent_published_cycle,
    _parse_grib_idx,
)
from nwp_ingestion.geolocation import FetchBBox

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample_gfs_nongfab.grib2"
AWS_IDX_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample_gfs_aws_f001.idx"
AWS_DSWRF_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample_gfs_aws_dswrf.grib2"
AWS_BASE_URL = "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20260714/00/atmos/gfs.t00z.pgrb2.0p25.f001"


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
    assert params["var_APCP"] == ["on"]
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
    # This fixture was captured live before var_APCP was added to the filter
    # request (see _build_filter_url) - it genuinely carries no "tp" GRIB message,
    # so precip_mm must come back None (honest "no data"), not a fabricated 0.0.
    assert point.precip_mm is None


@pytest.mark.asyncio
async def test_mock_datasource_returns_one_pair_per_configured_forecast_hour():
    settings = Settings(source_mode="mock")
    source = MockNWPDataSource(settings, fixture_path=FIXTURE_PATH, forecast_hours=[1, 2, 3])

    pairs = await source.fetch_latest_cycle()

    assert len(pairs) == 3
    for raw, point in pairs:
        assert raw.content_type == "application/x-grib2"
        assert point.source == "mock-fixture"


def test_parse_grib_idx_extracts_msg_num_offset_short_name_level():
    """AWS_IDX_FIXTURE_PATH is a real .idx sidecar fetched live 2026-07-15 from
    noaa-gfs-bdp-pds (gfs.20260714/00z, f001) - not fabricated.
    """
    idx = _parse_grib_idx(AWS_IDX_FIXTURE_PATH.read_text())
    assert len(idx) > 500  # a full GFS 0.25deg message list has ~600+ fields
    assert (653, 458738967, "DSWRF", "surface") in idx


def test_parse_grib_idx_drops_the_forecast_hour_dependent_step_suffix():
    """The 4th colon-segment ("0-1 hour ave fcst") is intentionally not part of
    the parsed tuple - it varies by forecast hour (see _S3_BACKFILL_FIELDS's
    docstring) and matching against it broke every fhour except f001 in an
    earlier version of this module, caught by a real end-to-end run against
    fhour=2 (see README "Backfill").
    """
    idx = _parse_grib_idx("653:458738967:d=2026071400:DSWRF:surface:0-1 hour ave fcst:\n")
    assert idx == [(653, 458738967, "DSWRF", "surface")]


def test_byte_range_for_field_uses_next_messages_offset_as_end():
    idx = _parse_grib_idx(AWS_IDX_FIXTURE_PATH.read_text())
    start, end = _byte_range_for_field(idx, "DSWRF", "surface")
    # verified live 2026-07-15 against the real bucket: this exact range 200s with a
    # real GRIB2 message decodable to ssrd_w_m2 ~= 36.34 at Nong Fab.
    assert (start, end) == (458738967, 459546159)


def test_byte_range_for_field_last_message_in_file_is_open_ended():
    idx = [(1, 100, "FIELD_A", "sfc"), (2, 500, "FIELD_B", "sfc")]
    start, end = _byte_range_for_field(idx, "FIELD_B", "sfc")
    assert (start, end) == (500, None)


def test_byte_range_for_field_raises_for_unknown_field():
    idx = [(1, 100, "FIELD_A", "sfc")]
    with pytest.raises(ValueError):
        _byte_range_for_field(idx, "NOT_PRESENT", "sfc")


def test_byte_range_for_field_does_not_confuse_tmp_with_aptmp():
    """Real ambiguity caught live 2026-07-15: f006's real .idx has both a TMP and
    an APTMP message at "2 m above ground", with TMP listed first - a naive
    substring match ("TMP:2 m above ground:" is itself a substring of
    "APTMP:2 m above ground:") would silently pick whichever happens to sort
    first, not necessarily the right one. Exact (short_name, level) equality
    can't make this mistake.
    """
    idx = [(1, 100, "TMP", "2 m above ground"), (2, 200, "APTMP", "2 m above ground")]
    start, end = _byte_range_for_field(idx, "TMP", "2 m above ground")
    assert (start, end) == (100, 199)


def test_decode_single_field_grib_sync_extracts_dswrf_from_real_fixture():
    """AWS_DSWRF_FIXTURE_PATH is the real DSWRF byte range fetched live 2026-07-15
    from noaa-gfs-bdp-pds via the exact range test_byte_range_for_field_uses_next_
    messages_offset_as_end proves is correct - not synthetic.
    """
    grib_bytes = AWS_DSWRF_FIXTURE_PATH.read_bytes()
    value = _decode_single_field_grib_sync(grib_bytes, target_lat=12.68337, target_lon=101.11987)
    assert value == pytest.approx(36.34, abs=0.5)


@pytest.mark.asyncio
@respx.mock
async def test_s3_backfill_source_fetch_cycle_assembles_all_five_fields():
    respx.get(f"{AWS_BASE_URL}.idx").mock(return_value=httpx.Response(200, text=AWS_IDX_FIXTURE_PATH.read_text()))
    respx.get(AWS_BASE_URL).mock(return_value=httpx.Response(206, content=b"fake-grib-bytes"))

    settings = Settings(source_mode="http")
    # Real values captured live 2026-07-15 (see test_real_class-style verification in
    # README) - patches asyncio.to_thread (the decode call) rather than re-decoding 5
    # real multi-hundred-KB fixtures per test run; _decode_single_field_grib_sync's
    # own correctness is covered by test_decode_single_field_grib_sync_extracts_dswrf_
    # from_real_fixture above against real bytes. 6th value is the precip (APCP)
    # decode added 2026-07-18 - AWS_IDX_FIXTURE_PATH genuinely carries an APCP
    # message at f001 (see test_byte_range_for_field_resolves_duplicate_apcp_entries
    # below), so this path is exercised for real, not skipped.
    fake_decoded = [
        36.34000015258789, 299.2613830566406, 80.80000305175781, 4.881699085235596, 3.0757031440734863, 0.42,
    ]
    async with httpx.AsyncClient() as client:
        source = S3GfsBackfillDataSource(settings, client, RateLimiter(0.0), target_latitude=12.68337, target_longitude=101.11987)
        with patch("nwp_ingestion.datasource.asyncio.to_thread", new=AsyncMock(side_effect=fake_decoded)):
            raw, point = await source.fetch_cycle(datetime(2026, 7, 14, 0, tzinfo=timezone.utc), forecast_hour=1)

    assert point.issue_time == datetime(2026, 7, 14, 0, tzinfo=timezone.utc)
    assert point.valid_time == datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
    assert point.ssrd_w_m2 == pytest.approx(36.34, abs=0.01)
    assert point.temp2m_c == pytest.approx(26.11, abs=0.01)  # 299.2614K - 273.15
    assert point.relative_humidity_pct == pytest.approx(80.8, abs=0.01)
    assert point.wind10m_u_ms == pytest.approx(4.8817, abs=0.001)
    assert point.wind10m_v_ms == pytest.approx(3.0757, abs=0.001)
    assert point.precip_mm == pytest.approx(0.42, abs=0.001)
    assert point.source == S3GfsBackfillDataSource.SOURCE_NAME
    assert raw.forecast_hour == 1
    assert len(raw.body) == 6 * len(b"fake-grib-bytes")  # concatenation of all 5 required + 1 precip field responses


@pytest.mark.asyncio
@respx.mock
async def test_s3_backfill_source_fetch_cycle_tolerates_precip_decode_failure():
    """Precipitation is optional (see _S3_BACKFILL_PRECIP_FIELD's own docstring) -
    a decode failure on just that field must not fail the whole backfill row the
    way a failure on one of the 5 required fields would.
    """
    respx.get(f"{AWS_BASE_URL}.idx").mock(return_value=httpx.Response(200, text=AWS_IDX_FIXTURE_PATH.read_text()))
    respx.get(AWS_BASE_URL).mock(return_value=httpx.Response(206, content=b"fake-grib-bytes"))

    settings = Settings(source_mode="http")
    fake_decoded = [
        36.34000015258789, 299.2613830566406, 80.80000305175781, 4.881699085235596, 3.0757031440734863,
        RuntimeError("simulated precip decode failure"),
    ]
    async with httpx.AsyncClient() as client:
        source = S3GfsBackfillDataSource(settings, client, RateLimiter(0.0), target_latitude=12.68337, target_longitude=101.11987)
        with patch("nwp_ingestion.datasource.asyncio.to_thread", new=AsyncMock(side_effect=fake_decoded)):
            raw, point = await source.fetch_cycle(datetime(2026, 7, 14, 0, tzinfo=timezone.utc), forecast_hour=1)

    assert point.precip_mm is None
    assert point.ssrd_w_m2 == pytest.approx(36.34, abs=0.01)  # the 5 required fields are unaffected


def test_byte_range_for_field_resolves_duplicate_apcp_entries():
    """Real quirk verified live 2026-07-18 against AWS_IDX_FIXTURE_PATH: GFS
    publishes *two* idx lines reading exactly "APCP:surface:0-1 hour acc fcst" at
    f001 (msg 596 and 597, different byte offsets) - not a parsing bug, an actual
    GFS publishing duplicate. Exact (short_name, level) match takes the first one,
    same resolution _byte_range_for_field already applies to any other collision.
    """
    idx = _parse_grib_idx(AWS_IDX_FIXTURE_PATH.read_text())
    matches = [row for row in idx if row[2] == "APCP" and row[3] == "surface"]
    assert len(matches) == 2

    start, end = _byte_range_for_field(idx, "APCP", "surface")
    assert start == matches[0][1]
    assert end == matches[1][1] - 1


@pytest.mark.asyncio
async def test_s3_backfill_source_fetch_latest_cycle_delegates_to_fetch_cycle():
    settings = Settings(source_mode="http", backfill_forecast_hour=1, publish_latency_minutes=240)
    async with httpx.AsyncClient() as client:
        source = S3GfsBackfillDataSource(settings, client, RateLimiter(0.0))
        fake_point = object()
        with patch.object(source, "fetch_cycle", new=AsyncMock(return_value=(object(), fake_point))) as mocked:
            pairs = await source.fetch_latest_cycle()

    assert len(pairs) == 1
    assert pairs[0][1] is fake_point
    called_issue_time, called_fhour = mocked.call_args.args
    assert called_fhour == 1
    assert called_issue_time.hour in settings.gfs_cycles


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("NWP_LIVE_TEST") != "1", reason="set NWP_LIVE_TEST=1 to hit the real AWS GFS bucket")
@pytest.mark.asyncio
async def test_s3_backfill_datasource_against_real_aws_bucket():
    settings = Settings(source_mode="http")
    async with httpx.AsyncClient() as client:
        source = S3GfsBackfillDataSource(settings, client, RateLimiter(0.3), target_latitude=12.68337, target_longitude=101.11987)
        raw, point = await source.fetch_cycle(datetime(2026, 7, 14, 0, tzinfo=timezone.utc), forecast_hour=1)

    assert point.source == S3GfsBackfillDataSource.SOURCE_NAME
    assert 0 <= point.ssrd_w_m2 <= 1500
    assert len(raw.body) > 0


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("NWP_LIVE_TEST") != "1", reason="set NWP_LIVE_TEST=1 to hit the real AWS GFS bucket")
@pytest.mark.asyncio
async def test_s3_backfill_datasource_works_beyond_forecast_hour_one():
    """Regression test for a real bug caught live 2026-07-15: an earlier version
    of _S3_BACKFILL_FIELDS matched each field's exact f001 step-type text (e.g.
    "0-1 hour ave fcst"), which only happens to be correct at fhour=1 - every
    other forecast hour (whose step-type text is different, e.g. "0-6 hour ave
    fcst" at f006, "6-12 hour ave fcst" at f012) raised ValueError. Exercises
    several forecast hours spanning GFS's different accumulation-window
    conventions (short initial windows, then rolling 6h windows).
    """
    settings = Settings(source_mode="http")
    issue_time = datetime(2026, 7, 14, 0, tzinfo=timezone.utc)
    async with httpx.AsyncClient() as client:
        source = S3GfsBackfillDataSource(settings, client, RateLimiter(0.3), target_latitude=12.68337, target_longitude=101.11987)
        for fhour in (2, 6, 12, 24):
            _, point = await source.fetch_cycle(issue_time, forecast_hour=fhour)
            assert 0 <= point.ssrd_w_m2 <= 1500
            assert -30 <= point.temp2m_c <= 60
            assert point.valid_time == issue_time + timedelta(hours=fhour)


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
