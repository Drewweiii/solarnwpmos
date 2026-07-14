"""WebSocket /ws/live - pushes each connected client a periodic snapshot of
every zone's latest synthetic "current" AC power plus (if a model has been
registered for it) the latest hour-ahead forecast, per the architecture doc
("push ค่าล่าสุด + พยากรณ์"). Auth: JWT passed as `?token=` since browser
WebSocket clients cannot set the `Authorization` header on the handshake
request. Push interval: `Settings.live_push_interval_seconds` (default 5s).

Same "no real accumulated history yet" caveat as every other module's
dev-time behavior - `current_ac_kw` comes from Module 5's synthetic baseline
pipeline, not a live TimescaleDB read.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_forecast.serving import ModelNotTrainedError, get_latest_forecast
from nongfab_simulation.dev_data import synthetic_day_irradiance_temp
from nongfab_simulation.pipeline import simulate_zone_baseline

from .auth import decode_access_token
from .config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live"])


def _zone_snapshot(zone_id: str) -> dict:
    idx, ssrd, temp = synthetic_day_irradiance_temp()
    baseline = simulate_zone_baseline(zone_id, ssrd, temp, idx)
    # `idx` spans today 00:00-23:00; iloc[-1] would always be the 23:00 (always-
    # dark) row regardless of wall-clock time, so pick the row closest to now
    # instead of just the last one.
    now_idx = idx.get_indexer([datetime.now(timezone.utc)], method="nearest")[0]
    current_ac_kw = float(baseline.ac_power_kw.iloc[now_idx])

    forecast_hour_ahead_kw = None
    try:
        result = get_latest_forecast(zone_id, "hour")
        forecast_hour_ahead_kw = result.points[0].pred if result.points else None
    except ModelNotTrainedError:
        forecast_hour_ahead_kw = None  # no model registered yet - omit rather than fail the whole push

    return {"zone": zone_id, "current_ac_kw": current_ac_kw, "forecast_hour_ahead_kw": forecast_hour_ahead_kw}


def live_payload() -> dict:
    return {"zones": [_zone_snapshot(zone_id) for zone_id in sorted(nong_fab_zone_capacities_kwp())]}


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    settings: Settings = websocket.app.state.settings
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="missing token")
        return
    try:
        decode_access_token(token, settings)
    except HTTPException:
        await websocket.close(code=1008, reason="invalid or expired token")
        return

    await websocket.accept()
    try:
        while True:
            await websocket.send_json(live_payload())
            await asyncio.sleep(settings.live_push_interval_seconds)
    except WebSocketDisconnect:
        logger.debug("ws/live client disconnected")
