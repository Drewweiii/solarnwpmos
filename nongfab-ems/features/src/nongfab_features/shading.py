"""Analytical fixed-tilt row-to-row self-shading, combined with panel
geometry (panel_geometry.py) to produce a per-panel "solar access %" -
Feature B's "ระบายสีแต่ละแผงตาม solar access/ประสิทธิภาพ" and "solar access %"
readout.

Models inter-row self-shading only (the array shading itself) - there is no
obstacle survey (trees/structures) in config/assets.yaml, so external
obstacle shading is out of scope here (a "Known gaps" item, not a fabricated
input). Uses a standard 2D cross-section approximation valid for a repeating
array of identical parallel rows: only the immediately-preceding row's
shadow is considered (a shadow long enough to reach row+2 would in reality
partially shade it too - this simplified model doesn't capture that
extreme-low-sun case). Good enough for a visualization-grade estimate, not
a bankable energy-yield calculation.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from .clearsky import compute_clearsky_and_position, nong_fab_site_location
from .panel_geometry import Panel, ZoneLayout, generate_zone_layout

# Asia/Bangkok - the representative-day sampling below is built in local solar
# time so each month's day-length/sun-arc is genuine, matching how
# nongfab_simulation.pipeline.monthly_ac_energy_estimates already samples.
_NONG_FAB_TZ = "Asia/Bangkok"


def row_shaded_fraction(
    tilt_deg: float, azimuth_deg: float, row_pitch_m: float, slant_height_m: float,
    solar_elevation_deg: float, solar_azimuth_deg: float,
) -> float:
    """Fraction (0-1) of a row's slant height shaded by the row immediately
    in front of it. Callers handle `row == 0` themselves (nothing shades the
    front row) - this function always models "a row exists in front".
    Returns 0 if the sun is in front of (or side-on to) the array, since a
    row's shadow then falls forward, away from the row behind it; 1 if the
    sun is below the horizon (treated as "no usable light", not "0% shaded"
    - see `zone_solar_access`, which handles night separately for row 0 too).
    """
    if solar_elevation_deg <= 0:
        return 1.0

    tilt = math.radians(tilt_deg)
    delta_azimuth = math.radians(solar_azimuth_deg - azimuth_deg)
    # A shadow extends opposite the direction light arrives *from* - i.e. in
    # the same horizontal direction the array itself faces, when the sun is
    # roughly in front of the array (illuminating it "head-on"). So
    # behind_component peaks at +1 when the sun's azimuth matches the
    # array's own facing azimuth exactly (delta_azimuth == 0): the array is
    # lit dead-on and casts its longest shadow straight back onto the row
    # behind it. It's <= 0 (no backward shadow in this simplified model)
    # once the sun swings around behind the array (delta_azimuth -> 180).
    behind_component = math.cos(delta_azimuth)
    if behind_component <= 0:
        return 0.0

    elevation = math.radians(solar_elevation_deg)
    row_base_m = slant_height_m * math.cos(tilt)  # horizontal footprint of one tilted row
    row_height_m = slant_height_m * math.sin(tilt)  # height of its highest (back) edge

    shadow_horizontal_m = row_height_m / math.tan(elevation) * behind_component
    # How far the shadow reaches past the next row's front edge (which sits
    # `row_pitch_m` behind this row's own front edge).
    shadow_overhang_m = (row_base_m - row_pitch_m) + shadow_horizontal_m
    if shadow_overhang_m <= 0 or row_base_m <= 0:
        return 0.0
    return max(0.0, min(1.0, shadow_overhang_m / row_base_m))


@dataclass(frozen=True)
class PanelSolarAccess:
    block_id: str
    row: int
    col: int
    east_m: float
    north_m: float
    shaded_fraction: float
    solar_access_pct: float


def zone_solar_access(layout: ZoneLayout, solar_elevation_deg: float, solar_azimuth_deg: float) -> list[PanelSolarAccess]:
    """Per-panel solar access for every panel in `layout`, at one instant in
    time (one sun position) - callers combine this with clear-sky/weather
    data (features.clearsky) for an *irradiance* value; this function is
    purely geometric (0-100%, independent of actual sky conditions).
    """

    def _panel_access(panel: Panel) -> PanelSolarAccess:
        if solar_elevation_deg <= 0:
            shaded = 1.0
        elif panel.row == 0:
            shaded = 0.0
        else:
            shaded = row_shaded_fraction(
                panel.tilt_deg, panel.azimuth_deg, layout.row_pitch_m, panel.slant_height_m,
                solar_elevation_deg, solar_azimuth_deg,
            )
        return PanelSolarAccess(
            block_id=panel.block_id, row=panel.row, col=panel.col,
            east_m=panel.east_m, north_m=panel.north_m,
            shaded_fraction=shaded, solar_access_pct=(1 - shaded) * 100,
        )

    return [_panel_access(panel) for panel in layout.panels]


def average_solar_access_pct(panel_access: list[PanelSolarAccess]) -> float:
    """The "avg unshaded access across all panels" readout (Aurora-style,
    e.g. "95%") - 100.0 for an empty layout (nothing to be shaded)."""
    if not panel_access:
        return 100.0
    return sum(p.solar_access_pct for p in panel_access) / len(panel_access)


# Representative-day sampling for the annual shading integral below: one
# mid-month day per calendar month, hourly - the same 12-representative-days
# granularity nongfab_simulation.pipeline.monthly_ac_energy_estimates already
# uses for its own annual energy swing, so the shading loss and the energy it
# derates are sampled over the same sun geometry.
_SHADING_SAMPLE_DAY_OF_MONTH = 15
_SHADING_SAMPLE_YEAR = 2025  # any non-leap year - shading is a fixed geometric property, the exact year is irrelevant


@lru_cache(maxsize=None)
def annual_shading_loss_pct(zone_id: str) -> float:
    """A zone's annual, clear-sky-energy-weighted inter-row self-shading loss
    (percent), computed from its real modelled array geometry
    (`generate_zone_layout` -> `zone_solar_access`) integrated over a full
    year's sun path - the geometry-derived replacement for the flat
    `nongfab_simulation.loss_model.DEFAULT_SHADING_PCT` literature default
    (2026-07-22, roadmap item 3 option A).

    Energy-weighted, not time-averaged: each sample's mean shaded fraction is
    weighted by that instant's clear-sky GHI, so the geometrically-severe but
    energetically-tiny low-sun hours near sunrise/sunset (and night, GHI~=0)
    don't dominate the figure - what matters is shading loss on the energy the
    array actually collects. Formula: `100 * sum(ghi * shaded_frac) /
    sum(ghi)` over 12 mid-month days x 24 hours.

    Scope (unchanged from `row_shaded_fraction`'s own docstring): inter-row
    *self*-shading only. External-obstacle shading (a neighbouring structure,
    terrain) is NOT modelled here and remains a documented known gap - it needs
    a real site obstacle survey this project doesn't have, exactly the reason
    the fuller ray-cast approach wasn't taken. So this can legitimately come
    out *below* the old 3% flat default for a well-pitched array: that's an
    honest statement about this array's own row geometry, not a claim that
    zero external shading exists.

    `@lru_cache`d: this is a fixed, deterministic geometric property of the
    array (no weather, no request state), so it's computed once per zone per
    process and reused - safe to call from the hot `default_loss_factors`
    path.
    """
    layout = generate_zone_layout(zone_id)
    lat, lon = nong_fab_site_location()

    weighted_shaded = 0.0
    total_ghi = 0.0
    for month in range(1, 13):
        start = pd.Timestamp(year=_SHADING_SAMPLE_YEAR, month=month, day=_SHADING_SAMPLE_DAY_OF_MONTH, tz=_NONG_FAB_TZ)
        idx = pd.date_range(start, periods=24, freq="h", tz=_NONG_FAB_TZ)
        solpos = compute_clearsky_and_position(idx, lat, lon, tz=_NONG_FAB_TZ)
        for elev, azim, ghi in zip(solpos["elevation_deg"], solpos["azimuth_deg"], solpos["ghi_clearsky"]):
            if elev <= 0 or ghi <= 0:
                continue  # night / no collectable energy - carries zero weight anyway
            mean_shaded_frac = 1 - average_solar_access_pct(zone_solar_access(layout, float(elev), float(azim))) / 100
            weighted_shaded += ghi * mean_shaded_frac
            total_ghi += ghi

    if total_ghi <= 0:
        return 0.0
    return 100 * weighted_shaded / total_ghi


@dataclass(frozen=True)
class StringPowerEstimate:
    block_id: str
    string_index: int
    module_count: int
    avg_solar_access_pct: float
    estimated_power_kw: float


@dataclass(frozen=True)
class BlockPowerBalance:
    block_id: str
    strings: list[StringPowerEstimate]
    imbalance_kw: float
    max_allowed_kw: float | None
    exceeds_limit: bool


def string_power_balance(
    panel_access: list[PanelSolarAccess], module_power_w: float, max_allowed_kw: float | None = None,
) -> list[BlockPowerBalance]:
    """Per-string estimated power (each module at its own nameplate
    `module_power_w`, scaled by that panel's own solar-access % from
    `zone_solar_access` - a relative/comparative figure, not a real-time
    absolute power reading), grouped by `(block_id, row)`.

    `row` only doubles as a real electrical string index where
    `panel_geometry.py`'s own layout assigns it that way -
    `_jetty_layout()`'s call to `_grid_panels(sub_array.id, sub_array.strings,
    sub_array.modules_per_string, ...)` lays out exactly one row per real
    string (`sub_array.strings` from config/assets.yaml). GIS/ISB's
    rectangular-block layout (`_rectangular_block_layout`) is a
    visualization approximation whose `row` does NOT correspond to a real
    string - callers should only pass panel_access from a zone with a real
    per-string layout (Jetty today), same "only Jetty has real sub-array
    data" caveat as `panel_geometry.py`/`sld.py` document elsewhere. This
    function doesn't itself know which zone produced `panel_access`, so it
    trusts the caller on that.

    `max_allowed_kw` - the zone's own `design_constraints.
    string_power_balance_max_kw` (config/assets.yaml), if it has one;
    `exceeds_limit` is always False when it's None (no constraint to check
    against, not "assumed fine").
    """
    by_block: dict[str, dict[int, list[PanelSolarAccess]]] = defaultdict(lambda: defaultdict(list))
    for p in panel_access:
        by_block[p.block_id][p.row].append(p)

    results = []
    for block_id, rows in by_block.items():
        strings = []
        for row, panels in sorted(rows.items()):
            avg_access = sum(p.solar_access_pct for p in panels) / len(panels)
            estimated_kw = (avg_access / 100) * len(panels) * module_power_w / 1000
            strings.append(
                StringPowerEstimate(
                    block_id=block_id, string_index=row, module_count=len(panels),
                    avg_solar_access_pct=avg_access, estimated_power_kw=estimated_kw,
                )
            )
        powers = [s.estimated_power_kw for s in strings]
        imbalance_kw = max(powers) - min(powers) if powers else 0.0
        results.append(
            BlockPowerBalance(
                block_id=block_id, strings=strings, imbalance_kw=imbalance_kw, max_allowed_kw=max_allowed_kw,
                exceeds_limit=max_allowed_kw is not None and imbalance_kw > max_allowed_kw,
            )
        )
    return results
