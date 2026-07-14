"""Loads and validates config/assets.yaml - the single source of truth for Nong
Fab plant geometry (3 zones: GIS, ISB, Jetty), referenced from ส่วนที่ 0 and
ส่วนที่ 5 of the architecture doc. Every module that needs zone coordinates,
capacity, or equipment specs should go through `load_assets()` rather than
duplicating numbers.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    elevation_m: float | None = None  # ground elevation, where surveyed (e.g. Google Maps advanced measurements)
    note: str | None = None


class ZoneCorners(BaseModel):
    UL: LatLon
    UR: LatLon
    LL: LatLon
    LR: LatLon

    def points(self) -> list[LatLon]:
        return [self.UL, self.UR, self.LL, self.LR]


class ModuleSpec(BaseModel):
    name: str
    power_w: float
    technology: str
    cells: int
    dimensions_mm: tuple[float, float, float]
    voc_v: float
    isc_a: float
    vmp_v: float
    imp_a: float
    efficiency_pct: float


class OptimizerSpec(BaseModel):
    model: str
    count: int
    ratio_modules_per_optimizer: int


class InverterDetail(BaseModel):
    model: str
    count: int
    ac_kw_each: float
    mppt_per_inverter: int
    mppt_voltage_range_v: tuple[float, float]
    max_dc_voltage_v: float
    efficiency_pct: float


class SubArray(BaseModel):
    id: str
    side: str | None = None
    strings: int | None = None
    optimizers_per_string: int | None = None
    modules_per_string: int | None = None
    note: str | None = None


class InterconnectionPoint(BaseModel):
    id: str
    distance_from_isb_m: float
    note: str | None = None


class JettyDesignConstraints(BaseModel):
    dc_voltage_drop_max_pct_of_vmp: float
    ac_voltage_drop_max_pct: float
    string_power_balance_max_kw: float


class FuturePhase(BaseModel):
    phase: str
    additional_ac_capacity_kw: float
    note: str | None = None


class Zone(BaseModel):
    id: str
    name_full: str
    ac_capacity_kw: float
    dc_capacity_kwp: float
    dc_ac_ratio: float
    module_count: int
    module_power_w: float = 715
    inverter_model: str
    inverter_count: int
    centroid: LatLon
    corners: ZoneCorners

    strings: list[str] | None = None
    mppt_count: int | None = None
    tilt_deg: float | None = None  # None = not yet field-surveyed (see notes)
    azimuth_deg: float | None = None
    status: str | None = None
    notes: str | None = None
    sld_available: bool | str | None = None
    span_north_south_km: float | None = None

    # Populated where a Single Line Diagram (or equivalent as-built doc) exists -
    # Jetty and GIS both have one; ISB doesn't yet (source doc only briefly describes it).
    module_detail: ModuleSpec | None = None
    optimizer: OptimizerSpec | None = None
    inverter_detail: InverterDetail | None = None
    sub_arrays: list[SubArray] = Field(default_factory=list)
    interconnection_points: list[InterconnectionPoint] = Field(default_factory=list)
    design_constraints: JettyDesignConstraints | None = None
    future_phases: list[FuturePhase] = Field(default_factory=list)


class Environmental(BaseModel):
    co2_saved_kg_per_kw_per_year: float
    trees_equivalent_per_kw_per_year: float
    jetty_600kw_co2_saved_tonnes_per_year: float
    jetty_600kw_trees_equivalent: float


class Site(BaseModel):
    name: str
    project_code: str
    district: str
    nominal_center: LatLon
    total_ac_capacity_kw_current_phase: float
    optimizer_common: str


class CloudTileConfig(BaseModel):
    buffer_deg: float = Field(gt=0)


class AssetRegistry(BaseModel):
    site: Site
    zones: list[Zone]
    environmental: Environmental
    cloud_tile: CloudTileConfig

    def zone(self, zone_id: str) -> Zone:
        for z in self.zones:
            if z.id == zone_id:
                return z
        raise KeyError(f"unknown zone id {zone_id!r}; known zones: {[z.id for z in self.zones]}")


def _default_assets_path() -> Path:
    """config/assets.yaml relative to this file: libs/nongfab_common/src/nongfab_common/assets.py
    -> ../../../../config/assets.yaml (repo root's config/ dir).
    """
    return Path(__file__).resolve().parents[4] / "config" / "assets.yaml"


def load_assets(path: Path | str | None = None) -> AssetRegistry:
    """Loads and validates config/assets.yaml. Path resolution order:
    explicit `path` arg > NONGFAB_ASSETS_PATH env var > repo-relative default.
    """
    resolved = Path(path) if path else Path(os.environ.get("NONGFAB_ASSETS_PATH", "")) if os.environ.get("NONGFAB_ASSETS_PATH") else _default_assets_path()
    raw = yaml.safe_load(resolved.read_text())
    return AssetRegistry.model_validate(raw)


def target_bbox(registry: AssetRegistry) -> tuple[float, float, float, float]:
    """Union bounding box of every zone's 4 corners, padded by cloud_tile.buffer_deg
    on every side. Returns (lat_min, lat_max, lon_min, lon_max).

    This is what Module 1 (Himawari ingestion) points its cloud-tile fetch at -
    the buffer gives lead time to see an approaching cloud front before it
    reaches the plant, regardless of wind direction.
    """
    lats = [p.lat for zone in registry.zones for p in zone.corners.points()]
    lons = [p.lon for zone in registry.zones for p in zone.corners.points()]
    buf = registry.cloud_tile.buffer_deg
    return (min(lats) - buf, max(lats) + buf, min(lons) - buf, max(lons) + buf)
