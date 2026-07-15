"""Interactive SLD (single-line diagram) data - Module 7's Feature D "Auto-SLD
viewer". Builds a real equipment topology (module -> string -> MPPT ->
inverter -> AC) from config/assets.yaml's own equipment fields
(module_detail/optimizer/inverter_detail/strings/mppt_count/sub_arrays) - the
same data already transcribed from the plant's real Single Line Diagrams (see
config/assets.yaml's own header comment) - rather than a scanned image of the
original PDF (none is bundled in this repo). Not a claim that every wire/
breaker/junction-box symbol here matches the original drawing pixel for
pixel - it's a generated topology diagram from the same underlying real
equipment counts, meant to be inspected/clicked, not a facsimile.

Only Jetty (`sub_arrays`) has real per-string module counts; GIS/ISB's SLD is
electrical-only (no per-string breakdown survey), so their per-inverter
string module counts are `module_count` spread as evenly as possible across
(inverter x string) slots - an approximation, flagged via
`approximate_string_distribution`, same spirit as `panel_geometry.py`'s own
GIS/ISB visualization approximation.
"""

from __future__ import annotations

from dataclasses import dataclass

from nongfab_common.assets import Zone


@dataclass(frozen=True)
class SLDString:
    id: str
    modules: int


@dataclass(frozen=True)
class SLDBlock:
    """One inverter (GIS/ISB) or one real sub-array (Jetty) and its strings.
    Jetty's block `id` is the sub-array's own real id (e.g. "01A.L") rather
    than an assumed "INV-N" label, since config/assets.yaml doesn't record
    which physical inverter each sub-array is wired to.
    """

    id: str
    inverter_model: str
    inverter_ac_kw: float
    mppt_count: int
    strings: list[SLDString]


@dataclass(frozen=True)
class SLDData:
    zone_id: str
    module_model: str | None
    module_power_w: float
    optimizer_model: str | None
    optimizer_ratio_modules_per_optimizer: int | None
    blocks: list[SLDBlock]
    approximate_string_distribution: bool


def _distribute_evenly(total: int, n_slots: int) -> list[int]:
    """Splits `total` as evenly as possible across `n_slots` non-negative
    integers that sum exactly to `total` - the first `total % n_slots` slots
    get one extra, so no module is ever silently dropped to rounding.
    """
    base, remainder = divmod(total, n_slots)
    return [base + (1 if i < remainder else 0) for i in range(n_slots)]


def _gis_isb_blocks(zone: Zone) -> list[SLDBlock]:
    strings = zone.strings or ["ST-1"]
    inverter_count = zone.inverter_count
    mppt_count = zone.mppt_count or len(strings)
    inverter_ac_kw = zone.inverter_detail.ac_kw_each if zone.inverter_detail else zone.ac_capacity_kw / max(1, inverter_count)

    slot_counts = _distribute_evenly(zone.module_count, inverter_count * len(strings))

    blocks = []
    for inv_i in range(inverter_count):
        block_strings = [
            SLDString(id=string_id, modules=slot_counts[inv_i * len(strings) + s_i])
            for s_i, string_id in enumerate(strings)
        ]
        blocks.append(
            SLDBlock(
                id=f"INV-{inv_i + 1}", inverter_model=zone.inverter_model, inverter_ac_kw=inverter_ac_kw,
                mppt_count=mppt_count, strings=block_strings,
            )
        )
    return blocks


def _jetty_blocks(zone: Zone) -> list[SLDBlock]:
    built = [sa for sa in zone.sub_arrays if sa.strings is not None and sa.modules_per_string is not None]
    inverter_ac_kw = zone.inverter_detail.ac_kw_each if zone.inverter_detail else zone.ac_capacity_kw / max(1, zone.inverter_count)
    mppt_count = zone.mppt_count or (zone.inverter_detail.mppt_per_inverter if zone.inverter_detail else 4)

    blocks = []
    for sub_array in built:
        strings = [
            SLDString(id=f"{sub_array.id}-ST{i + 1}", modules=sub_array.modules_per_string)
            for i in range(sub_array.strings)
        ]
        blocks.append(
            SLDBlock(
                id=sub_array.id, inverter_model=zone.inverter_model, inverter_ac_kw=inverter_ac_kw,
                mppt_count=mppt_count, strings=strings,
            )
        )
    return blocks


def build_sld(zone: Zone) -> SLDData:
    if zone.id == "Jetty":
        blocks, approximate = _jetty_blocks(zone), False
    else:
        blocks, approximate = _gis_isb_blocks(zone), True

    return SLDData(
        zone_id=zone.id,
        module_model=zone.module_detail.name if zone.module_detail else None,
        module_power_w=zone.module_power_w,
        optimizer_model=zone.optimizer.model if zone.optimizer else None,
        optimizer_ratio_modules_per_optimizer=zone.optimizer.ratio_modules_per_optimizer if zone.optimizer else None,
        blocks=blocks,
        approximate_string_distribution=approximate,
    )
