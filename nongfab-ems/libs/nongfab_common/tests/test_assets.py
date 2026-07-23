import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from nongfab_common.assets import AssetRegistry, load_assets, target_bbox

MINIMAL_YAML = textwrap.dedent("""
    site:
      name: "Test Site"
      project_code: "TEST001"
      district: "Test District"
      nominal_center: { lat: 12.71, lon: 101.15 }
      total_ac_capacity_kw_current_phase: 400
      optimizer_common: "Test Optimizer"

    zones:
      - id: A
        name_full: "Zone A"
        ac_capacity_kw: 50
        dc_capacity_kwp: 60
        dc_ac_ratio: 1.2
        module_count: 84
        inverter_model: "Test Inverter"
        inverter_count: 1
        centroid: { lat: 12.70, lon: 101.10 }
        corners:
          UL: { lat: 12.71, lon: 101.09 }
          UR: { lat: 12.71, lon: 101.11 }
          LL: { lat: 12.69, lon: 101.09 }
          LR: { lat: 12.69, lon: 101.11 }
      - id: B
        name_full: "Zone B"
        ac_capacity_kw: 150
        dc_capacity_kwp: 140
        dc_ac_ratio: 0.93
        module_count: 196
        inverter_model: "Test Inverter"
        inverter_count: 3
        centroid: { lat: 12.68, lon: 101.20 }
        corners:
          UL: { lat: 12.685, lon: 101.195 }
          UR: { lat: 12.685, lon: 101.205 }
          LL: { lat: 12.675, lon: 101.195 }
          LR: { lat: 12.675, lon: 101.205 }

    environmental:
      co2_saved_kg_per_kw_per_year: 901
      trees_equivalent_per_kw_per_year: 101
      jetty_600kw_co2_saved_tonnes_per_year: 540.6
      jetty_600kw_trees_equivalent: 60600

    cloud_tile:
      buffer_deg: 0.05
    """)


@pytest.fixture
def minimal_registry_path(tmp_path: Path) -> Path:
    p = tmp_path / "assets.yaml"
    p.write_text(MINIMAL_YAML)
    return p


def test_load_assets_parses_and_validates(minimal_registry_path):
    registry = load_assets(minimal_registry_path)
    assert isinstance(registry, AssetRegistry)
    assert registry.site.project_code == "TEST001"
    assert len(registry.zones) == 2


def test_load_assets_via_explicit_env_var(minimal_registry_path, monkeypatch):
    monkeypatch.setenv("NONGFAB_ASSETS_PATH", str(minimal_registry_path))
    registry = load_assets()
    assert registry.site.project_code == "TEST001"


def test_zone_lookup_by_id(minimal_registry_path):
    registry = load_assets(minimal_registry_path)
    zone = registry.zone("A")
    assert zone.ac_capacity_kw == 50

    with pytest.raises(KeyError):
        registry.zone("does-not-exist")


def test_target_bbox_is_union_of_corners_plus_buffer(minimal_registry_path):
    registry = load_assets(minimal_registry_path)
    lat_min, lat_max, lon_min, lon_max = target_bbox(registry)

    # union of corners: lat [12.675, 12.71], lon [101.09, 101.205], buffer 0.05
    assert lat_min == pytest.approx(12.675 - 0.05)
    assert lat_max == pytest.approx(12.71 + 0.05)
    assert lon_min == pytest.approx(101.09 - 0.05)
    assert lon_max == pytest.approx(101.205 + 0.05)


def test_missing_required_field_raises_validation_error(tmp_path):
    bad_yaml = textwrap.dedent("""
        site:
          name: "Test Site"
        zones: []
        environmental:
          co2_saved_kg_per_kw_per_year: 901
          trees_equivalent_per_kw_per_year: 101
          jetty_600kw_co2_saved_tonnes_per_year: 540.6
          jetty_600kw_trees_equivalent: 60600
        cloud_tile:
          buffer_deg: 0.05
        """)
    p = tmp_path / "bad.yaml"
    p.write_text(bad_yaml)
    with pytest.raises(ValidationError):
        load_assets(p)


def test_real_repo_assets_yaml_loads_and_validates():
    """Not a synthetic fixture - loads the actual config/assets.yaml this repo ships,
    so a schema/data mismatch fails CI instead of only being caught manually.
    """
    registry = load_assets()  # default path resolution -> repo's config/assets.yaml
    assert {z.id for z in registry.zones} == {"GIS", "ISB", "Jetty"}

    jetty = registry.zone("Jetty")
    assert jetty.module_detail is not None
    assert jetty.module_detail.power_w == 715
    assert jetty.optimizer.count == 160
    assert len(jetty.sub_arrays) == 5
    assert len(jetty.interconnection_points) == 3
    # confirmed by satellite imagery (2026-07-14): no panels physically installed
    # yet, unlike GIS/ISB - forecast/simulation modules must treat this as a
    # capacity-driven projection, not something to fit real sensor history against.
    assert jetty.simulated is True
    # LLjet/LRjet sit on the trestle pier over open water - Google Maps reads 0m
    # ground elevation there (not missing data, an accurate "no ground" reading).
    assert jetty.corners.LL.elevation_m == pytest.approx(0.0)
    assert jetty.corners.UL.elevation_m == pytest.approx(2.98)

    gis = registry.zone("GIS")
    assert gis.simulated is False  # real installed hardware, unlike Jetty
    assert gis.dc_ac_ratio == 1.20
    # from the GIS Single Line Diagram (PPA25.0008-PTTLNGEE-001): same Trina module
    # as Jetty, but only 84 of them behind a single 50kW inverter / 42 optimizers.
    assert gis.module_detail is not None
    assert gis.module_detail.power_w == 715
    assert gis.optimizer.count == 42
    assert gis.optimizer.ratio_modules_per_optimizer == 2
    assert gis.inverter_detail.count == 1
    assert gis.inverter_detail.ac_kw_each == 50
    # ground elevation from Google Maps advanced measurements - real per-corner survey data
    assert gis.corners.UL.elevation_m == pytest.approx(6.09)
    assert gis.corners.LL.elevation_m == pytest.approx(7.04)

    isb = registry.zone("ISB")
    assert isb.dc_ac_ratio == 0.93
    # from the ISB Single Line Diagram (PPA25.0008-PTTLNGEE-001): same Trina module,
    # 196 of them behind 3x 50kW inverters / 98 optimizers.
    assert isb.module_detail is not None
    assert isb.module_detail.power_w == 715
    assert isb.optimizer.count == 98
    assert isb.optimizer.ratio_modules_per_optimizer == 2
    assert isb.inverter_detail.count == 3
    assert isb.inverter_detail.ac_kw_each == 50
    assert isb.corners.UL.elevation_m == pytest.approx(11.57)
    assert isb.corners.LR.elevation_m == pytest.approx(10.15)

    lat_min, lat_max, lon_min, lon_max = target_bbox(registry)
    # sanity: matches the ~12.61-12.74N, 101.06-101.18E region from the architecture doc
    assert 12.55 < lat_min < 12.65
    assert 12.70 < lat_max < 12.80
    assert 101.00 < lon_min < 101.10
    assert 101.15 < lon_max < 101.25

    # Public LNG-terminal context (2026-07-23) - the facts the frontend's
    # "About this facility" card surfaces. Sourced, not measured here.
    lng = registry.site.lng_terminal
    assert lng is not None
    assert lng.official_name == "Map Ta Phut LNG Terminal 2 (Nong Fab)"
    assert lng.regas_capacity_mmtpa == pytest.approx(7.5)
    assert lng.peak_capacity_mmtpa == pytest.approx(9.0)
    assert lng.storage_tank_count == 2
    assert lng.storage_tank_capacity_m3 == pytest.approx(250000)
    # Both jetty figures are recorded honestly rather than reconciled to one.
    assert lng.jetty_length_km_public == pytest.approx(5.5)
    assert lng.jetty_length_km_user_stated == pytest.approx(5.66)
    assert len(lng.sources) >= 1
    # Expanded Terminal-2 dataset (2026-07-23 research pass).
    assert lng.investment_cost_billion_thb == pytest.approx(38.5)
    assert lng.epc_contract_value_musd == pytest.approx(925)
    assert lng.land_area_total_ha == pytest.approx(29.7)
    assert lng.first_cargo_date == "2022-06-18"
    assert lng.is_thailand_second_onshore_terminal is True

    # Real user-stated facility figures driving the Energy Management panel.
    assert registry.site.facility_electrical_load_kw == pytest.approx(13500)
    assert registry.site.facility_annual_electricity_cost_thb == pytest.approx(300_000_000)


def test_lng_terminal_optional_when_omitted(minimal_registry_path):
    """The minimal fixture omits site.lng_terminal entirely - it must still load,
    with lng_terminal defaulting to None, so older YAML/fixtures keep validating.
    """
    registry = load_assets(minimal_registry_path)
    assert registry.site.lng_terminal is None
