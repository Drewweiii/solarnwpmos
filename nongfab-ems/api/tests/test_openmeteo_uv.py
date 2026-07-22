"""Unit tests for the Open-Meteo UV source (openmeteo_uv.fetch_uv_observations)
- mocks the HTTP layer so no real network is touched, same
'no mocked-real-HTTP-content beyond this' scope as the other ingestion sources."""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

from nongfab_api.openmeteo_uv import (
    SOURCE_NAME,
    fetch_hourly_uv_observations,
    fetch_uv_observations,
)


def _client_returning(payload: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fetch_uv_observations_parses_daily_series():
    payload = {"daily": {"time": ["2026-07-17", "2026-07-18", "2026-07-19"], "uv_index_max": [7.85, 8.5, 8.85]}}
    async with _client_returning(payload) as client:
        obs = await fetch_uv_observations(client, 12.68, 101.12, past_days=3)
    assert [o.observation_date for o in obs] == [date(2026, 7, 17), date(2026, 7, 18), date(2026, 7, 19)]
    assert [o.uv_index for o in obs] == [7.85, 8.5, 8.85]
    assert all(o.source == SOURCE_NAME for o in obs)


async def test_fetch_uv_observations_skips_null_days_without_fabricating():
    payload = {"daily": {"time": ["2026-07-17", "2026-07-18"], "uv_index_max": [None, 8.5]}}
    async with _client_returning(payload) as client:
        obs = await fetch_uv_observations(client, 12.68, 101.12)
    assert len(obs) == 1
    assert obs[0].observation_date == date(2026, 7, 18)


async def test_fetch_uv_observations_empty_when_no_daily_block():
    async with _client_returning({}) as client:
        obs = await fetch_uv_observations(client, 12.68, 101.12)
    assert obs == []


async def test_fetch_uv_observations_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_uv_observations(client, 12.68, 101.12)


async def test_fetch_hourly_uv_observations_parses_utc_series():
    payload = {"hourly": {"time": ["2026-07-19T00:00", "2026-07-19T01:00", "2026-07-19T12:00"], "uv_index": [0.0, 0.0, 9.2]}}
    async with _client_returning(payload) as client:
        obs = await fetch_hourly_uv_observations(client, 12.68, 101.12, past_days=1)
    assert [o.observed_at for o in obs] == [
        datetime(2026, 7, 19, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc),
    ]
    assert [o.uv_index for o in obs] == [0.0, 0.0, 9.2]
    assert all(o.observed_at.tzinfo is timezone.utc for o in obs)
    assert all(o.source == SOURCE_NAME for o in obs)


async def test_fetch_hourly_uv_observations_skips_null_hours_without_fabricating():
    payload = {"hourly": {"time": ["2026-07-19T10:00", "2026-07-19T11:00"], "uv_index": [None, 8.1]}}
    async with _client_returning(payload) as client:
        obs = await fetch_hourly_uv_observations(client, 12.68, 101.12)
    assert len(obs) == 1
    assert obs[0].observed_at == datetime(2026, 7, 19, 11, 0, tzinfo=timezone.utc)


async def test_fetch_hourly_uv_observations_empty_when_no_hourly_block():
    async with _client_returning({}) as client:
        obs = await fetch_hourly_uv_observations(client, 12.68, 101.12)
    assert obs == []


async def test_fetch_hourly_uv_observations_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_hourly_uv_observations(client, 12.68, 101.12)
