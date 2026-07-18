"""GET /performance/{zone} - performance-ratio / specific-yield snapshot for
today, built on the same Module 5 pipeline (`simulate_zone_baseline`) the
simulate route uses. No real accumulated (I, T, P) history exists yet (see
forecast/README "Known gaps"), so - like every other module's dev-time
behavior - this computes against a synthetic "today" rather than reading
TimescaleDB; swapping the synthetic generator for a real query is a
follow-up once Modules 1-3 have accumulated enough history, not a change to
this route's shape.

**2026-07-16**: the user's live demo showed frozen numbers and asked why -
there is genuinely no real production telemetry anywhere in this system (no
Huawei FusionSolar/SolarFusion integration, no SCADA/inverter read). Two
fixes landed here while that real integration remains a separate, bigger
follow-up: (1) `hourly`/`ac_energy_kwh_today` are now scaled by
`live_efficiency_factor()`, a bounded [0.85, 1.0] multiplier keyed off real
wall-clock time (see that function's own docstring) so polling this route
repeatedly actually shows movement instead of the exact same numbers every
time, while never exceeding the physics estimate; (2) `ac_energy_kwh_today`
now sums only hours up to *now*, not the full 24h synthetic day - it was
previously already showing the day's final total no matter what time it
was, which was the other reason the KPI looked stuck.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from nongfab_features.irradiance_map import cloud_factor_at
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_forecast.serving import (
    GENERATED_POWER_BACKFILL_HOURS,
    GENERATED_POWER_ESTIMATED_MARKER,
    generated_power_history,
    record_generated_power,
)
from nongfab_simulation.dev_data import live_efficiency_factor, synthetic_day_irradiance_temp
from nongfab_simulation.loss_model import performance_ratio
from nongfab_simulation.pipeline import simulate_zone_baseline
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["performance"])


class HourlyPoint(BaseModel):
    timestamp: datetime
    ac_kw: float
    ssrd_w_m2: float
    temp_c: float


class GeneratedPowerPoint(BaseModel):
    timestamp: datetime
    ac_kw: float
    # True for a cold-start-backfilled physics-baseline estimate rather than
    # a genuinely live-polled reading (see forecast/serving.py's
    # GENERATED_POWER_ESTIMATED_MARKER docstring for the full honesty
    # story - a backfilled "actual" and a physics-baseline-fallback
    # "forecast" for the same hour are the literal same number by
    # construction, not independent signals). False once a live poll has
    # superseded that hour's backfilled row.
    estimated: bool


class PerformanceResponse(BaseModel):
    zone: str
    simulated_zone: bool
    latitude: float
    longitude: float
    ac_energy_kwh_today: float
    poa_irradiance_kwh_per_m2_today: float
    performance_ratio: float
    specific_yield_kwh_per_kwp_today: float
    loss_breakdown: dict[str, float]
    # Today's synthetic baseline, hour by hour - lets a dashboard chart
    # "generated power" over the day rather than just today's running total
    # (see /forecast/{zone}/{horizon} for the model's own predicted series).
    hourly: list[HourlyPoint]
    # Persisted actual/generated power for *previous* days (2026-07-18) -
    # `hourly` above is always "today" only (synthetic-per-request, no
    # persistence, see this route's own docstring), so there was previously
    # no way to show "what was this zone producing 2 days ago" on the
    # dashboard at all. Backed by `nongfab_forecast.serving.
    # record_generated_power()`/`generated_power_history()` - a genuine,
    # incrementally-accumulated log of this route's own `ac_power_kw_live`
    # reading at each poll, backfilled on cold start with a physics-baseline
    # estimate (see `backfill_generated_power_history()`'s own docstring for
    # the honesty caveat - same spirit as the forecast side's own backfill).
    # Covers the last `GENERATED_POWER_BACKFILL_HOURS` (72h/3 days).
    history: list[GeneratedPowerPoint]
    # This zone's own cloud factor right now (0..1) - Module 7 Feature A's
    # per-zone info panel. Reuses nongfab_features.irradiance_map's
    # documented synthetic cloud-factor model (see that module's own
    # docstring for why: no live Himawari raster store exists yet) evaluated
    # at this zone's own centroid, not a generic plant-wide grid point.
    cloud_factor: float


def _validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


@router.get("/performance/{zone}", response_model=PerformanceResponse)
async def get_performance(zone: str, request: Request, _user=Depends(require_role("viewer"))) -> PerformanceResponse:
    zone = _validate_zone(zone)
    idx, ssrd, temp = synthetic_day_irradiance_temp()
    baseline = simulate_zone_baseline(zone, ssrd, temp, idx)

    now = datetime.now(timezone.utc)
    efficiency = live_efficiency_factor(zone, now)
    ac_power_kw_live = baseline.ac_power_kw * efficiency  # bounded <= the physics estimate, see live_efficiency_factor()

    # "Today so far", not the whole synthetic day - hours after `now` haven't
    # happened yet, so summing the full 24h (the previous behavior) always
    # showed the day's final total regardless of the actual time, which is
    # why the KPI looked frozen.
    hours_so_far = now.hour + 1
    ac_energy_kwh = float(ac_power_kw_live.iloc[:hours_so_far].sum())  # hourly samples -> sum of kW == kWh
    poa_irradiance_kwh_per_m2 = float(ssrd[:hours_so_far].sum() / 1000)  # W/m^2 hourly samples -> kWh/m^2

    # Before any irradiance has accumulated today (e.g. right after UTC
    # midnight, before this synthetic model's "sunrise" hour), cumulative
    # POA is legitimately 0 - performance_ratio() would raise on a 0
    # denominator, whereas summing the whole day (the previous behavior)
    # never hit this because the denominator was never 0. Report PR=0
    # rather than erroring; there's simply nothing to divide by yet.
    if poa_irradiance_kwh_per_m2 <= 0:
        pr = 0.0
    else:
        try:
            pr = performance_ratio(ac_energy_kwh, poa_irradiance_kwh_per_m2, baseline.zone.dc_capacity_kwp)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    hourly = [
        HourlyPoint(
            timestamp=ts.to_pydatetime(), ac_kw=float(ac_power_kw_live.iloc[i]),
            ssrd_w_m2=float(ssrd[i]), temp_c=float(temp[i]),
        )
        for i, ts in enumerate(idx)
    ]

    centroid = baseline.zone.centroid
    cloud_factor = cloud_factor_at(centroid.lat, centroid.lon, now.timestamp())

    store = request.app.state.real_data_store
    # Persists *this* poll's own live reading (the current hour's
    # ac_power_kw_live, the same number reported in `hourly` for "now") into
    # the actual/generated-power history - see record_generated_power()'s
    # own docstring for why this route is the natural place to do it (it
    # already computes the exact value each poll). Bounded to the frontend's
    # own ~60s poll interval, so this is a cheap upsert, not a hot loop.
    record_generated_power(zone, store, float(ac_power_kw_live.iloc[now.hour]), now)
    history = [
        GeneratedPowerPoint(timestamp=p.timestamp, ac_kw=p.pred, estimated=p.algorithm == GENERATED_POWER_ESTIMATED_MARKER)
        for p in generated_power_history(zone, store, now - timedelta(hours=GENERATED_POWER_BACKFILL_HOURS))
    ]

    return PerformanceResponse(
        zone=zone, simulated_zone=baseline.zone.simulated, latitude=centroid.lat, longitude=centroid.lon,
        ac_energy_kwh_today=ac_energy_kwh, poa_irradiance_kwh_per_m2_today=poa_irradiance_kwh_per_m2,
        performance_ratio=pr, specific_yield_kwh_per_kwp_today=ac_energy_kwh / baseline.zone.dc_capacity_kwp,
        loss_breakdown=baseline.loss_breakdown, hourly=hourly, history=history, cloud_factor=cloud_factor,
    )
