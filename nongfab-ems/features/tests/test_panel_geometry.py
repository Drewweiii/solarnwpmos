import pytest
from nongfab_common.assets import load_assets

from nongfab_features.panel_geometry import (
    DEFAULT_AZIMUTH_DEG,
    DEFAULT_TILT_DEG,
    generate_zone_layout,
)


@pytest.fixture(scope="module")
def registry():
    return load_assets()


def test_gis_panel_count_matches_module_count(registry):
    layout = generate_zone_layout("GIS", registry)
    assert len(layout.panels) == registry.zone("GIS").module_count == 84


def test_isb_panel_count_matches_module_count(registry):
    layout = generate_zone_layout("ISB", registry)
    assert len(layout.panels) == registry.zone("ISB").module_count == 196


def test_jetty_panel_count_matches_module_count(registry):
    layout = generate_zone_layout("Jetty", registry)
    assert len(layout.panels) == registry.zone("Jetty").module_count == 320


def test_jetty_layout_uses_real_sub_array_block_ids(registry):
    layout = generate_zone_layout("Jetty", registry)
    block_ids = {panel.block_id for panel in layout.panels}
    assert block_ids == {"01A.L", "02A.L", "03A.R", "04A.R"}
    # "05A" is a documented future phase with no module count yet - must not appear
    assert "05A" not in block_ids


def test_jetty_blocks_spread_along_the_north_south_span(registry):
    layout = generate_zone_layout("Jetty", registry)
    norths_by_block = {}
    for panel in layout.panels:
        norths_by_block.setdefault(panel.block_id, []).append(panel.north_m)
    block_centers = {block: sum(norths) / len(norths) for block, norths in norths_by_block.items()}
    # 4 distinct along-span positions, not all stacked on top of each other
    assert len(set(round(v, 1) for v in block_centers.values())) == 4


def test_jetty_left_and_right_side_blocks_are_laterally_separated(registry):
    layout = generate_zone_layout("Jetty", registry)
    left_easts = [p.east_m for p in layout.panels if p.block_id in ("01A.L", "02A.L")]
    right_easts = [p.east_m for p in layout.panels if p.block_id in ("03A.R", "04A.R")]
    assert max(left_easts) < min(right_easts)


def test_gis_and_isb_use_default_tilt_and_azimuth_when_not_surveyed(registry):
    assert registry.zone("GIS").tilt_deg is None
    assert registry.zone("GIS").azimuth_deg is None
    layout = generate_zone_layout("GIS", registry)
    assert layout.tilt_deg == DEFAULT_TILT_DEG
    assert layout.azimuth_deg == DEFAULT_AZIMUTH_DEG


def test_zone_own_tilt_azimuth_override_the_default_when_present():
    from nongfab_common.assets import AssetRegistry

    raw = load_assets().model_dump()
    raw["zones"][0]["tilt_deg"] = 22.5
    raw["zones"][0]["azimuth_deg"] = 200.0
    registry = AssetRegistry.model_validate(raw)

    layout = generate_zone_layout(registry.zones[0].id, registry)
    assert layout.tilt_deg == 22.5
    assert layout.azimuth_deg == 200.0


def test_row_zero_panels_exist_for_every_block(registry):
    for zone_id in ("GIS", "ISB", "Jetty"):
        layout = generate_zone_layout(zone_id, registry)
        blocks = {panel.block_id for panel in layout.panels}
        for block_id in blocks:
            rows = {p.row for p in layout.panels if p.block_id == block_id}
            assert 0 in rows


def test_unknown_zone_raises_key_error(registry):
    with pytest.raises(KeyError):
        generate_zone_layout("Nowhere", registry)
