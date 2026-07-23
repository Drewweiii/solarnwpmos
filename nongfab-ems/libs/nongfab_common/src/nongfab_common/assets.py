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

    # True where no panels are physically installed yet (design/simulation-only -
    # e.g. Jetty, confirmed by satellite imagery showing bare trestle, no PV visible).
    # Forecast/simulation modules should treat these zones' output as a capacity-
    # driven projection (see forecast.pv_conversion.default_params_from_capacity),
    # never as something to fit a regression against real (I, T, P) history - there
    # is no real history to have. False (the default) means real installed hardware,
    # even if this repo hasn't accumulated enough sensor history to train on yet.
    simulated: bool = False

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


class LngTerminal(BaseModel):
    """Public facts about the host LNG terminal (PTT LNG Nong Fab / Map Ta Phut
    Terminal 2) the solar array sits on. Describes the LNG FACILITY, not the
    solar plant - every figure is from cited public sources (see the `sources`
    list), not measured by this project. Surfaced read-only in the frontend's
    "About this facility" card so viewers understand the site's context. All
    fields default to None/empty so existing minimal YAML/test fixtures that
    omit the whole block still validate.
    """

    # Identity
    official_name: str = ""
    also_known_as: str = ""
    is_thailand_second_onshore_terminal: bool = False
    owner: str = ""
    epc_contractors: str = ""
    owners_engineer: str = ""
    location: str = ""
    # Capacity & storage
    regas_capacity_mmtpa: float | None = None
    peak_capacity_mmtpa: float | None = None
    storage_tank_count: int | None = None
    storage_tank_capacity_m3: float | None = None
    storage_tank_type: str = ""
    storage_claim: str = ""
    # Marine / jetty
    jetty_length_km_public: float | None = None
    jetty_length_km_user_stated: float | None = None
    trestle_length_km: float | None = None
    jetty_claim: str = ""
    lng_carrier_min_m3: float | None = None
    lng_carrier_max_m3: float | None = None
    # Project & investment
    contract_awarded_year: int | None = None
    epc_contract_value_musd: float | None = None
    investment_cost_billion_thb: float | None = None
    operational_since_year: int | None = None
    first_cargo_date: str = ""
    first_cargo_carrier: str = ""
    first_cargo_origin: str = ""
    # Land use
    land_area_total_ha: float | None = None
    land_area_terminal_ha: float | None = None
    land_area_office_ha: float | None = None
    # Sustainability
    cold_energy_reuse: bool = False
    seawater_recycling: bool = False
    landscape_award: str = ""
    sources: list[str] = Field(default_factory=list)


class Site(BaseModel):
    name: str
    project_code: str
    district: str
    nominal_center: LatLon
    total_ac_capacity_kw_current_phase: float
    optimizer_common: str
    # Defaulted (not required) so existing minimal test fixtures/YAML don't
    # need updating - added 2026-07-16 from the user's own Google Earth
    # pin annotations confirming the plant's formal facility code and
    # street, not previously captured anywhere in this registry.
    facility_code: str = ""
    street_address: str = ""
    # Public LNG-terminal context (2026-07-23) - None where the YAML omits it,
    # so older fixtures/tests keep validating. See LngTerminal.
    lng_terminal: LngTerminal | None = None
    # Facility average electrical demand (kW) - user-stated real operating figure
    # (13.5 MW, avg daily 13-14 MW). Drives the Energy Management panel's "% of
    # facility load offset". None when the YAML omits it.
    facility_electrical_load_kw: float | None = None
    # Facility average annual electricity cost (THB/yr) - user-stated (~300 MTHB).
    # Lets the EMS panel value the solar output as an approximate baht/yr bill
    # saving at the facility's own implied average tariff. None when omitted.
    facility_annual_electricity_cost_thb: float | None = None


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
    env_path = os.environ.get("NONGFAB_ASSETS_PATH")
    resolved = Path(path) if path else Path(env_path) if env_path else _default_assets_path()
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
