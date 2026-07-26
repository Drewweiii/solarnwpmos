"""Where did this number come from? (2026-07-26, project O)

This project has spent its whole life insisting on the difference between a
measurement, a published figure, a literature default and a guess. That
insistence lives in a dozen places - `settings_registry`'s `origin` field on all
92 editable values, `official_sources`' registry of Thai agency documents,
`loss_model.soiling_source`, `assets.yaml`'s survey comments,
`grid_carbon.MIX_ORIGIN_*`, `routes_verification`'s reference notes - and a
visitor looking at one number on a page can reach none of it.

This module makes the chain behind a number answerable: source -> model ->
setting -> origin. Nothing else on a solar dashboard does this, and it is the
feature that follows most directly from what this project already cares about.

THE ONE DESIGN RULE THAT MATTERS. A setting's origin and note are NEVER copied
here - they are read from `settings_registry` at request time. Hand-written
provenance text would start lying the moment somebody edited the registry, and
no test would catch it, which is precisely the failure mode this feature exists
to prevent. A step that names a setting key that does not exist is a hard error
at import (see `validate_registry`), so a renamed key breaks the build instead
of silently producing a chain with a hole in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .settings_registry import BY_KEY, ORIGIN_LABELS

# What kind of link in the chain a step is. Kept as constants because the
# frontend maps them to icons and a typo would silently fall through.
KIND_SOURCE = "source"
KIND_SETTING = "setting"
KIND_MODEL = "model"
KIND_COMPUTATION = "computation"

# Origins that are not settings (a setting's origin comes from the registry).
# Deliberately the SAME vocabulary as settings_registry's, plus one for a live
# feed, so a reader never has to learn two scales.
ORIGIN_MEASURED_FEED = "measured-feed"

EXTRA_ORIGIN_LABELS = {
    ORIGIN_MEASURED_FEED: "ข้อมูลสดจากแหล่งภายนอก (ดึงอัตโนมัติ ไม่ได้กรอกมือ)",
}


@dataclass(frozen=True)
class ProvenanceStep:
    kind: str
    label: str
    detail: str
    # Set for KIND_SETTING. The origin/note are then read from the registry
    # rather than stored, so this can never drift out of date.
    setting_key: str | None = None
    # Set for every other kind, where there is no registry row to read.
    origin: str | None = None


@dataclass(frozen=True)
class ProvenanceEntry:
    """One number a viewer can click on."""

    key: str
    label: str
    unit: str
    steps: list[ProvenanceStep]
    # The single most important thing a reader could get wrong about this
    # figure. Every entry has one; a number with no caveat worth stating is
    # usually a number nobody needed traced.
    caveat: str
    # Where in the app this figure is shown, so the answer can say "this is the
    # same number as the one on that page" rather than leaving it ambiguous.
    shown_on: list[str] = field(default_factory=list)


# The site has no generation meter at all. It is the single most load-bearing
# caveat in the whole product and appears in more than one chain, so it is
# written once.
_NO_METER = (
    "ไซต์นี้ไม่มีมิเตอร์วัดกำลังผลิตจริง ตัวเลข 'ค่าจริง' ทุกที่ในเว็บคือผลจากโมเดลฟิสิกส์ "
    "ที่ป้อนด้วยสภาพอากาศที่เกิดขึ้นจริง ไม่ใช่ค่าที่อ่านจากมิเตอร์"
)

_ENTRIES: tuple[ProvenanceEntry, ...] = (
    ProvenanceEntry(
        key="forecast.expected_energy_kwh",
        label="พลังงานที่คาดว่าจะผลิตได้",
        unit="kWh",
        shown_on=["หน้า Forecast — บล็อกตัวเลขใหญ่ด้านบน"],
        steps=[
            ProvenanceStep(
                kind=KIND_SOURCE,
                label="พยากรณ์อากาศ NWP (GFS) + ภาพเมฆดาวเทียม Himawari",
                detail="ดึงอัตโนมัติเป็นระยะ เก็บลง nwp_history / cloud_history",
                origin=ORIGIN_MEASURED_FEED,
            ),
            ProvenanceStep(
                kind=KIND_MODEL,
                label="โมเดลพยากรณ์ (NeuralProphet รายวัน · LightGBM/RF/Sum-k LSTM รายชั่วโมง)",
                detail="ระบบเลือกโมเดลที่แม่นกว่าให้อัตโนมัติในแต่ละชั่วโมงล่วงหน้า",
                origin="derived",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="กำลังติดตั้ง DC ของโซน",
                detail="กำลังผลิตเป็นสัดส่วนตรงกับกำลังติดตั้ง",
                setting_key="zone.GIS.dc_capacity_kwp",
            ),
            ProvenanceStep(
                kind=KIND_COMPUTATION,
                label="รวมกำลังผลิตรายชั่วโมงเป็นพลังงาน",
                detail="คูณด้วยระยะห่างระหว่างจุดพยากรณ์ (อ่านจากข้อมูลจริง ใช้ค่ามัธยฐาน ไม่ใช่สมมติว่าเป็นรายชั่วโมง)",
                origin="derived",
            ),
        ],
        caveat="เป็นค่าพยากรณ์ ไม่ใช่ค่าที่ผลิตได้จริง และ" + _NO_METER,
    ),
    ProvenanceEntry(
        key="tou.blended_rate_thb_per_kwh",
        label="อัตราค่าไฟเฉลี่ยถ่วงน้ำหนักที่แท้จริง",
        unit="บาท/kWh",
        shown_on=["หน้า Forecast — แผง TOU Peak/Off-Peak"],
        steps=[
            ProvenanceStep(
                kind=KIND_SOURCE,
                label="ประกาศอัตราค่าไฟฟ้า กฟภ. ประเภทที่ 4 (TOU)",
                detail="ประกาศเป็นไฟล์ภาพสแกน จึงถอดเป็นตัวเลขด้วยมือ — ดูทะเบียนแหล่งข้อมูลที่ /sources",
                origin="confirmed",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="อัตราช่วง Peak",
                detail="ค่าที่ถอดจากประกาศ",
                setting_key="green.normal_rate_thb_per_kwh",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="อัตราช่วง Off-Peak",
                detail="ยังไม่ได้กรอกค่าจริง จึงตั้งเท่ากับอัตรา Peak ไว้ก่อน ทำให้ตัวเลขที่เผยแพร่ไม่ขยับ",
                setting_key="green.offpeak_rate_thb_per_kwh",
            ),
            ProvenanceStep(
                kind=KIND_COMPUTATION,
                label="ถ่วงน้ำหนักด้วยพลังงานที่ผลิตได้จริงในแต่ละช่วง",
                detail="นับวันทำงาน/วันหยุดจากปฏิทินจริง ไม่ได้ประมาณว่า 5/7",
                origin="derived",
            ),
        ],
        caveat="ตราบใดที่ยังไม่กรอกอัตรา Off-Peak จริง ตัวเลขนี้จะเท่ากับอัตรา Peak เสมอ ไม่ได้แปลว่าไม่มีส่วนต่าง",
    ),
    ProvenanceEntry(
        key="green.co2_avoided_kg",
        label="คาร์บอนที่หลีกเลี่ยงได้",
        unit="kgCO₂",
        shown_on=["หน้า Energy Report", "แผง Savings"],
        steps=[
            ProvenanceStep(
                kind=KIND_SOURCE,
                label="ค่าการปล่อยคาร์บอนของระบบไฟฟ้าไทย (กกพ.)",
                detail="ผู้ใช้เลือกใช้ค่าของ กกพ. เมื่อ 2026-07-25 แทนค่าของ อบก. หลังเห็นทั้งสองค่า",
                origin="confirmed",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="ค่าการปล่อยคาร์บอนต่อหน่วย",
                detail="ปรับได้ในหน้า Settings ถ้ามีประกาศใหม่",
                setting_key="green.ef_scope2_kg_per_kwh",
            ),
            ProvenanceStep(
                kind=KIND_COMPUTATION,
                label="คูณกับพลังงานที่ผลิตได้",
                detail="ใช้พลังงานชุดเดียวกับที่หน้าอื่นแสดง ไม่ได้คำนวณแยก",
                origin="derived",
            ),
        ],
        caveat="เป็นการ 'หลีกเลี่ยง' คาร์บอนเฉลี่ยของทั้งระบบ ไม่ใช่คาร์บอนของโรงไฟฟ้าที่ถูกสั่งลดจริงในนาทีนั้น",
    ),
    ProvenanceEntry(
        key="financial.payback_years",
        label="ระยะเวลาคืนทุน",
        unit="ปี",
        shown_on=["หน้า Financial"],
        steps=[
            ProvenanceStep(
                kind=KIND_SETTING,
                label="เงินลงทุนต่อกำลังติดตั้ง (CAPEX)",
                detail="⚠️ ยังเป็นค่าประมาณ ผู้ใช้เลือกคงไว้หลังเห็นราคาตลาดแล้ว และสูงกว่าราคาตลาดไทยปัจจุบัน",
                setting_key="financial.capex_per_kwp_thb",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="อัตราคิดลด (WACC)",
                detail="⚠️ ยังเป็นค่าประมาณเช่นกัน",
                setting_key="financial.discount_rate_pct",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="จำนวนปีที่ได้รับยกเว้นภาษี BOI",
                detail="ผู้ใช้ยืนยันแล้ว: 8 ปีในพื้นที่ทั่วไป และ 12 ปีสำหรับ Jetty",
                setting_key="financial.boi_tax_holiday_years",
            ),
            ProvenanceStep(
                kind=KIND_MODEL,
                label="กระแสเงินสดรายปี + การเสื่อมของแผง",
                detail="ใช้อัตราเสื่อมตามใบรับประกันจริงของแผงที่ติดตั้ง (Trina) ไม่ใช่ค่ามาตรฐานทั่วไป",
                origin="as-built",
            ),
        ],
        caveat="เพราะ CAPEX ที่ใช้สูงกว่าราคาตลาดไทยตอนนี้ ระยะคืนทุนที่เห็นน่าจะมองแง่ร้ายเกินจริง",
    ),
    ProvenanceEntry(
        key="verification.skill_score",
        label="Skill score เทียบ persistence",
        unit="",
        shown_on=["หน้า Forecast — แผง Verification"],
        steps=[
            ProvenanceStep(
                kind=KIND_SOURCE,
                label="คำพยากรณ์ที่ระบบออกไปจริง (forecast_history)",
                detail="ไม่ใช่ค่า error ตอนเทรน แต่เป็นคำพยากรณ์ที่เผยแพร่ไปแล้วจริงๆ",
                origin="derived",
            ),
            ProvenanceStep(
                kind=KIND_SOURCE,
                label="ฝั่ง 'ค่าจริง' ที่ใช้เทียบ",
                detail=_NO_METER,
                origin="derived",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="เกณฑ์ 'มีแดด'",
                detail="ชั่วโมงกลางคืนทายถูกง่ายเกินไป จึงไม่นับรวมในตัวเลขหลัก",
                setting_key="diagnostics.daylight_floor_kw",
            ),
            ProvenanceStep(
                kind=KIND_COMPUTATION,
                label="เทียบกับ baseline แบบ persistence",
                detail="skill = 1 − RMSE โมเดล ÷ RMSE persistence · มากกว่า 0 = เก่งกว่าการเดาว่าค่าจะคงเดิม",
                origin="derived",
            ),
        ],
        caveat="วัด error ของพยากรณ์อากาศที่ส่งผ่านโมเดลฟิสิกส์ ไม่ใช่ความคลาดเคลื่อนเทียบมิเตอร์",
    ),
    ProvenanceEntry(
        key="simulation.annual_energy_kwh",
        label="พลังงานที่ผลิตได้ต่อปี",
        unit="kWh/ปี",
        shown_on=["หน้า Simulation", "หน้า Energy Report"],
        steps=[
            ProvenanceStep(
                kind=KIND_SOURCE,
                label="พิกัดมุมแผงทั้ง 4 มุมของแต่ละโซน",
                detail="รังวัดจริงด้วย Google Maps advanced measurements เมื่อ 2026-07-14 พร้อมระดับความสูงต่อหมุด",
                origin="as-built",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="มุมเอียงแผง",
                detail="⚠️ ยังไม่เคยวัดจริง — assets.yaml ระบุ tilt_deg: null ทุกโซน (SLD เป็นข้อมูลไฟฟ้าอย่างเดียว)",
                setting_key="zone.GIS.tilt_deg",
            ),
            ProvenanceStep(
                kind=KIND_MODEL,
                label="แปลงแสงบนระนาบเอียง (POA) แล้วผ่านโมเดลแปลงเป็นไฟฟ้า",
                detail="Erbs แยกองค์ประกอบแสง + Hay-Davies ฉายลงระนาบแผง",
                origin="literature",
            ),
            ProvenanceStep(
                kind=KIND_SETTING,
                label="ค่าสูญเสียจากคราบสกปรก",
                detail="ค่าอ้างอิงจากงานวิจัย ไม่ได้วัดที่ไซต์นี้ (ยังไม่มีบันทึกการล้างแผงจริง)",
                setting_key="losses.soiling_fallback_land_pct",
            ),
        ],
        caveat=(
            "ตัวเลขนี้อ่อนไหวกับมุมเอียงที่ยังไม่เคยวัดจริง — ถ้าวัดมุมจริงมาได้ ตัวเลขจะแม่นขึ้นทันที "
            "(พิกัดและกำลังติดตั้งเป็นค่าจริงจากการรังวัด มุมเอียง/ทิศเท่านั้นที่ยังไม่มี)"
        ),
    ),
)

BY_VALUE_KEY: dict[str, ProvenanceEntry] = {entry.key: entry for entry in _ENTRIES}


def validate_registry() -> None:
    """Every `setting_key` a step names must exist in settings_registry.

    Called at import. A renamed setting then breaks the build loudly instead of
    quietly serving a chain with a hole where its origin should be - which is
    the exact class of silent drift this whole feature exists to prevent.
    """
    missing = [
        (entry.key, step.setting_key)
        for entry in _ENTRIES
        for step in entry.steps
        if step.kind == KIND_SETTING and step.setting_key not in BY_KEY
    ]
    if missing:
        raise ValueError(f"provenance references unknown settings: {missing}")


validate_registry()


def origin_label(origin: str) -> str:
    """Thai label for an origin, whichever vocabulary it came from."""
    return ORIGIN_LABELS.get(origin) or EXTRA_ORIGIN_LABELS.get(origin) or origin


def resolve_step(step: ProvenanceStep) -> dict:
    """Flatten one step for the API, reading a setting's origin and note LIVE
    from the registry rather than from anything stored here."""
    origin = step.origin
    registry_note = ""
    current_default: float | None = None
    unit = ""
    if step.kind == KIND_SETTING and step.setting_key:
        spec = BY_KEY[step.setting_key]
        origin = spec.origin
        registry_note = spec.note
        current_default = spec.default
        unit = spec.unit
    return {
        "kind": step.kind,
        "label": step.label,
        "detail": step.detail,
        "setting_key": step.setting_key,
        "origin": origin,
        "origin_label": origin_label(origin) if origin else "",
        "registry_note": registry_note,
        "default_value": current_default,
        "unit": unit,
    }


def weakest_origin(entry: ProvenanceEntry) -> str | None:
    """The least-trustworthy origin anywhere in the chain.

    A number is only as sound as its shakiest input, so this is what the UI
    headlines - averaging origins, or showing the best one, would flatter a
    figure that rests on a placeholder somewhere in the middle.
    """
    # Worst first. Anything not listed sorts as better than these.
    ranking = ["placeholder", "tuning", "literature", "derived", ORIGIN_MEASURED_FEED, "as-built", "confirmed"]
    found = [resolve_step(step)["origin"] for step in entry.steps]
    present = [o for o in ranking if o in found]
    return present[0] if present else None
