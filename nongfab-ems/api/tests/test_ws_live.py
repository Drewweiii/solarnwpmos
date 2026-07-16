from datetime import datetime, timezone

import nongfab_simulation.dev_data as dev_data
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import nongfab_api.ws_live as ws_live


def test_zone_snapshot_uses_the_row_nearest_now_not_always_the_last_row(monkeypatch):
    """Regression test: `synthetic_day_irradiance_temp()` always spans today
    00:00-23:00, so blindly taking `.iloc[-1]` would always return the 23:00
    (always-dark) row no matter the real time of day. At a synthetic local
    noon the snapshot should show non-zero, inverter-clipped output.

    Both `ws_live` and `dev_data` are patched to the same fixed instant -
    `synthetic_day_irradiance_temp()` calls its own module-level
    `datetime.now()` (in `nongfab_simulation.dev_data`, not `ws_live`) to
    build the synthetic day, so patching only `ws_live.datetime` left the
    "now" lookup on a fixed day while the synthetic day itself silently
    tracked the real wall-clock date - passing only on the day this test was
    written, then failing the moment the real date rolled over.

    05:00 UTC (not 12:00) is this synthetic model's own "local noon" as of
    the 2026-07-16 Thai-daylight-alignment fix - see
    synthetic_day_irradiance_temp()'s own docstring for why.
    """

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 14, 5, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(ws_live, "datetime", FixedDatetime)
    monkeypatch.setattr(dev_data, "datetime", FixedDatetime)
    snapshot = ws_live._zone_snapshot("GIS")
    assert snapshot["current_ac_kw"] == pytest.approx(50.0, rel=1e-3)


def test_ws_live_pushes_a_snapshot_for_every_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client, client.websocket_connect(f"/ws/live?token={token}") as ws:
        payload = ws.receive_json()
    zone_ids = {z["zone"] for z in payload["zones"]}
    assert {"GIS", "ISB", "Jetty"} <= zone_ids
    assert all(isinstance(z["current_ac_kw"], (int, float)) for z in payload["zones"])


def test_ws_live_pushes_repeatedly(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client, client.websocket_connect(f"/ws/live?token={token}") as ws:
        first = ws.receive_json()
        second = ws.receive_json()
    assert first["zones"] and second["zones"]


def test_ws_live_rejects_missing_token(app):
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/live"):
            pass


def test_ws_live_rejects_invalid_token(app):
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/live?token=garbage"):
            pass
