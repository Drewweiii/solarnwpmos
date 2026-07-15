from nongfab_common.assets import load_assets

from nongfab_features.sld import build_sld


def test_gis_sld_total_modules_match_module_count():
    registry = load_assets()
    zone = registry.zone("GIS")
    sld = build_sld(zone)
    total = sum(s.modules for block in sld.blocks for s in block.strings)
    assert total == zone.module_count


def test_gis_sld_flags_approximate_string_distribution():
    registry = load_assets()
    sld = build_sld(registry.zone("GIS"))
    assert sld.approximate_string_distribution is True


def test_gis_sld_has_one_block_per_inverter():
    registry = load_assets()
    zone = registry.zone("GIS")
    sld = build_sld(zone)
    assert len(sld.blocks) == zone.inverter_count == 1


def test_isb_sld_total_modules_match_module_count_despite_uneven_division():
    """196 modules / 3 inverters / 4 strings doesn't divide evenly - the
    remainder distribution must still sum exactly, not silently drop modules."""
    registry = load_assets()
    zone = registry.zone("ISB")
    sld = build_sld(zone)
    total = sum(s.modules for block in sld.blocks for s in block.strings)
    assert total == zone.module_count == 196
    assert len(sld.blocks) == 3


def test_jetty_sld_uses_real_sub_array_ids_not_synthetic_inverter_labels():
    registry = load_assets()
    zone = registry.zone("Jetty")
    sld = build_sld(zone)
    block_ids = {b.id for b in sld.blocks}
    assert block_ids == {"01A.L", "02A.L", "03A.R", "04A.R"}


def test_jetty_sld_total_modules_match_module_count():
    registry = load_assets()
    zone = registry.zone("Jetty")
    sld = build_sld(zone)
    total = sum(s.modules for block in sld.blocks for s in block.strings)
    assert total == zone.module_count == 320


def test_jetty_sld_not_flagged_approximate():
    registry = load_assets()
    sld = build_sld(registry.zone("Jetty"))
    assert sld.approximate_string_distribution is False


def test_sld_includes_real_module_and_optimizer_model_names():
    registry = load_assets()
    sld = build_sld(registry.zone("GIS"))
    assert sld.module_model == "Trina Vertex N TSM-NEG21C.20"
    assert sld.optimizer_model == "Huawei MERC-1300W-P"
    assert sld.optimizer_ratio_modules_per_optimizer == 2
