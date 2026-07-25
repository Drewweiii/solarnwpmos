"""The single source of truth for every value a user is allowed to change
(2026-07-25).

Why a registry rather than one endpoint per setting: the user asked for eight
different groups of values to become editable at once - site figures, financial
assumptions, loss factors, the soiling model's coefficients, look-back windows,
diagnostic thresholds, hand-control sensitivity and the expansion plan. Declaring
each one as DATA here means the API describes itself (bounds, units, Thai labels,
defaults) and ONE generic form on the frontend renders all of them. Adding a
setting later is a single entry in this file, not a new route plus new UI.

Every setting is numeric. That is a deliberate limit: it covers all eight groups
and keeps validation to "is it a number inside these bounds", with no free-text
or structured-object editing to sanitize. It is also why the expansion PHASES are
expressed as three separate "additional kW" numbers rather than an editable list
- same expressive power for this plan, none of the list-editing complexity.

`origin` is the honesty field, and it matters more than it looks. Some defaults
are figures the user confirmed for this site (the terminal's 13.5 MW load, its
฿300M/yr bill); some are as-built values read off the SLD; some are documented
placeholders that were never verified for this project (CAPEX ฿30,000/kWp); some
are literature-calibrated model coefficients. The UI shows this per field so
nobody edits a confirmed figure thinking it is a guess, or trusts a guess
thinking it was measured.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- groups -----------------------------------------------------------------
GROUP_SITE = "site"
GROUP_FINANCIAL = "financial"
GROUP_LOSSES = "losses"
GROUP_SOILING = "soiling"
GROUP_WINDOWS = "windows"
GROUP_DIAGNOSTICS = "diagnostics"
GROUP_HAND = "hand"
GROUP_EXPANSION = "expansion"
GROUP_GREEN = "green"
GROUP_GRIDMIX = "gridmix"

GROUP_LABELS: dict[str, str] = {
    GROUP_SITE: "ข้อมูลไซต์และคลัง (Site & facility)",
    GROUP_FINANCIAL: "สมมติฐานการเงิน (Financial assumptions)",
    GROUP_LOSSES: "การสูญเสียของระบบ (Loss factors)",
    GROUP_SOILING: "แบบจำลองคราบสกปรก (Soiling model)",
    GROUP_WINDOWS: "ช่วงเวลาย้อนหลังของแต่ละแผง (Look-back windows)",
    GROUP_DIAGNOSTICS: "เกณฑ์ตรวจสุขภาพระบบ (Diagnostics thresholds)",
    GROUP_HAND: "ความไวการควบคุมด้วยมือ (Hand control)",
    GROUP_EXPANSION: "แผนขยายกำลังผลิต (Expansion plan)",
    GROUP_GREEN: "ค่าไฟและคาร์บอนสำหรับหน้า Savings (Tariff & carbon)",
    GROUP_GRIDMIX: "สัดส่วนเชื้อเพลิงของระบบไฟฟ้าไทย (Grid fuel mix)",
}

# --- where a default came from ---------------------------------------------
# CONFIRMED: the user stated this figure for this site.
ORIGIN_CONFIRMED = "confirmed"
# AS_BUILT: read off the project's own as-built documents / SLD.
ORIGIN_AS_BUILT = "as-built"
# PLACEHOLDER: a documented estimate never verified for this project.
ORIGIN_PLACEHOLDER = "placeholder"
# LITERATURE: a published/industry-standard figure, not measured here.
ORIGIN_LITERATURE = "literature"
# TUNING: an interface/threshold choice with no external truth - pure taste.
ORIGIN_TUNING = "tuning"
# DERIVED: computed from a real public record AT THIS SITE'S OWN COORDINATES.
# Stronger than LITERATURE (which means "measured somewhere else") but weaker
# than CONFIRMED (nobody at the project signed it off); the note must name the
# dataset and period so the figure can be re-derived, not just trusted.
ORIGIN_DERIVED = "derived"

ORIGIN_LABELS: dict[str, str] = {
    ORIGIN_CONFIRMED: "ผู้ใช้ยืนยันแล้ว (ค่าจริงของไซต์นี้)",
    ORIGIN_AS_BUILT: "จากเอกสาร as-built/SLD ของโครงการ",
    ORIGIN_PLACEHOLDER: "ค่าประมาณ ยังไม่ยืนยันกับโครงการนี้",
    ORIGIN_LITERATURE: "ค่าอ้างอิงจากงานวิจัย/มาตรฐาน ไม่ได้วัดที่ไซต์นี้",
    ORIGIN_TUNING: "ค่าตั้งไว้เพื่อความรู้สึกใช้งาน ไม่มีค่าถูก/ผิด",
    ORIGIN_DERIVED: "คำนวณจากข้อมูลจริงย้อนหลังที่พิกัดไซต์นี้",
}

ZONES = ("GIS", "ISB", "Jetty")


@dataclass(frozen=True)
class SettingSpec:
    """One editable value. `minimum`/`maximum` are hard validation bounds - a
    write outside them is rejected, because these feed physics and money
    calculations where a fat-fingered zero changes every number downstream."""

    key: str
    group: str
    label: str
    unit: str
    default: float
    minimum: float
    maximum: float
    step: float
    origin: str
    note: str = ""
    # Frontend-only settings are applied by the browser (hand control); the
    # server stores them so an admin can publish a shared default, but no
    # backend calculation reads them.
    frontend_only: bool = False


def _zone_specs() -> list[SettingSpec]:
    """Per-zone hardware. Defaults are left at 0 deliberately: 0 means "use
    whatever config/assets.yaml says", so the as-built values stay the single
    source of truth until somebody explicitly overrides one. See
    settings_service.apply_asset_overrides."""
    out: list[SettingSpec] = []
    for zone in ZONES:
        out.extend(
            [
                SettingSpec(
                    key=f"zone.{zone}.ac_capacity_kw",
                    group=GROUP_SITE,
                    label=f"{zone}: กำลังติดตั้ง AC",
                    unit="kW",
                    default=0.0,
                    minimum=0.0,
                    maximum=100_000.0,
                    step=1.0,
                    origin=ORIGIN_AS_BUILT,
                    note="0 = ใช้ค่าจาก assets.yaml (ค่า as-built เดิม)",
                ),
                SettingSpec(
                    key=f"zone.{zone}.dc_capacity_kwp",
                    group=GROUP_SITE,
                    label=f"{zone}: กำลังติดตั้ง DC",
                    unit="kWp",
                    default=0.0,
                    minimum=0.0,
                    maximum=100_000.0,
                    step=0.01,
                    origin=ORIGIN_AS_BUILT,
                    note="0 = ใช้ค่าจาก assets.yaml",
                ),
                SettingSpec(
                    key=f"zone.{zone}.tilt_deg",
                    group=GROUP_SITE,
                    label=f"{zone}: มุมเอียงแผง",
                    unit="°",
                    default=0.0,
                    minimum=0.0,
                    maximum=90.0,
                    step=0.5,
                    origin=ORIGIN_AS_BUILT,
                    note="0 = ใช้ค่าจาก assets.yaml · เปลี่ยนค่านี้กระทบทั้งฟิสิกส์ 3D และการคำนวณเงา",
                ),
                SettingSpec(
                    key=f"zone.{zone}.azimuth_deg",
                    group=GROUP_SITE,
                    label=f"{zone}: ทิศที่แผงหัน",
                    unit="° (180=ใต้)",
                    default=0.0,
                    minimum=0.0,
                    maximum=360.0,
                    step=1.0,
                    origin=ORIGIN_AS_BUILT,
                    note="0 = ใช้ค่าจาก assets.yaml",
                ),
            ]
        )
    return out


SPECS: tuple[SettingSpec, ...] = (
    # --- A. site & facility -------------------------------------------------
    SettingSpec(
        key="site.facility_electrical_load_kw",
        group=GROUP_SITE,
        label="โหลดไฟฟ้าเฉลี่ยของคลัง",
        unit="kW",
        default=13_500.0,
        minimum=0.0,
        maximum=200_000.0,
        step=100.0,
        origin=ORIGIN_CONFIRMED,
        note="ผู้ใช้ระบุ 2026-07-23: เฉลี่ยรายวัน 13–14 MW · ใช้คิด solar offset และค่าไฟต่อหน่วยที่แท้จริง",
    ),
    SettingSpec(
        key="site.facility_annual_electricity_cost_thb",
        group=GROUP_SITE,
        label="ค่าไฟฟ้าของคลังต่อปี",
        unit="บาท",
        default=300_000_000.0,
        minimum=0.0,
        maximum=10_000_000_000.0,
        step=1_000_000.0,
        origin=ORIGIN_CONFIRMED,
        note="ผู้ใช้ระบุ 2026-07-23: ~300 ล้านบาท/ปี · หารด้วยหน่วยที่ใช้จริงได้ค่าไฟต่อ kWh ที่ /soiling และ /expansion ใช้",
    ),
    *_zone_specs(),
    # --- B. financial assumptions ------------------------------------------
    SettingSpec(
        key="financial.capex_per_kwp_thb",
        group=GROUP_FINANCIAL,
        label="เงินลงทุนต่อกำลังติดตั้ง (CAPEX)",
        unit="บาท/kWp",
        default=30_000.0,
        minimum=0.0,
        maximum=200_000.0,
        step=500.0,
        origin=ORIGIN_PLACEHOLDER,
        note="ยังไม่ยืนยันกับโครงการนี้ · กระทบ payback ของ /expansion และ NPV/IRR/LCOE ของ /financial",
    ),
    SettingSpec(
        key="financial.opex_pct_of_capex_per_year",
        group=GROUP_FINANCIAL,
        label="ค่าดูแลรักษาต่อปี (OPEX)",
        unit="% ของ CAPEX",
        default=1.2,
        minimum=0.0,
        maximum=20.0,
        step=0.1,
        origin=ORIGIN_PLACEHOLDER,
    ),
    SettingSpec(
        key="financial.tariff_thb_per_kwh",
        group=GROUP_FINANCIAL,
        label="ค่าไฟที่ประหยัดได้ (tariff)",
        unit="บาท/kWh",
        default=4.1025,
        minimum=0.0,
        maximum=30.0,
        step=0.0001,
        origin=ORIGIN_LITERATURE,
        note=(
            "อัตราจริงจากประกาศค่าไฟประเภทที่ 4 กิจการขนาดใหญ่ TOU ช่วง Peak ระดับแรงดัน HV "
            "(≥69 kV) = 4.1025 บาท/kWh — ค่าเดียวกับที่หน้า Savings ใช้ (green_savings.py) "
            "· เดิมหน้านี้ตั้งไว้ 4.00 ซึ่งเป็นเลขกลมที่ไม่มีแหล่งอ้างอิง ทำให้สองหน้าตีมูลค่า "
            "ไฟหน่วยเดียวกันไม่เท่ากัน · เป็นการประมาณที่บันทึกไว้: คิดทั้งปีที่อัตรา Peak "
            "ยังไม่ได้หักชั่วโมง off-peak เสาร์-อาทิตย์/วันหยุด (ต้องมีโปรไฟล์การใช้ไฟจริงราย "
            "ครึ่งชั่วโมงก่อนถึงจะละเอียดกว่านี้ได้) · หมายเหตุ: /soiling และ /expansion "
            "ไม่ใช้ค่านี้ ใช้ค่าไฟจริงต่อหน่วยที่คำนวณจากบิลจริงแทน"
        ),
    ),
    SettingSpec(
        key="financial.tariff_escalation_pct_per_year",
        group=GROUP_FINANCIAL,
        label="ค่าไฟขึ้นต่อปี",
        unit="%/ปี",
        default=3.0,
        minimum=-10.0,
        maximum=20.0,
        step=0.1,
        origin=ORIGIN_PLACEHOLDER,
    ),
    SettingSpec(
        key="financial.opex_escalation_pct_per_year",
        group=GROUP_FINANCIAL,
        label="ค่าดูแลขึ้นต่อปี (เงินเฟ้อ)",
        unit="%/ปี",
        default=3.0,
        minimum=-10.0,
        maximum=20.0,
        step=0.1,
        origin=ORIGIN_PLACEHOLDER,
    ),
    SettingSpec(
        key="financial.discount_rate_pct",
        group=GROUP_FINANCIAL,
        label="อัตราคิดลด (WACC)",
        unit="%",
        default=8.0,
        minimum=0.0,
        maximum=30.0,
        step=0.1,
        origin=ORIGIN_PLACEHOLDER,
        note="ยังไม่ยืนยันกับต้นทุนเงินทุนจริงขององค์กร",
    ),
    SettingSpec(
        key="financial.tax_rate_pct",
        group=GROUP_FINANCIAL,
        label="ภาษีเงินได้นิติบุคคล",
        unit="%",
        default=20.0,
        minimum=0.0,
        maximum=50.0,
        step=0.5,
        origin=ORIGIN_CONFIRMED,
        note="20% เป็นอัตราจริงของไทย ไม่ใช่ค่าสมมติ",
    ),
    SettingSpec(
        key="financial.boi_tax_holiday_years",
        group=GROUP_FINANCIAL,
        label="ปีที่ยกเว้นภาษี BOI — พื้นที่ทั่วไป (GIS, ISB)",
        unit="ปี",
        default=8.0,
        minimum=0.0,
        maximum=15.0,
        step=1.0,
        origin=ORIGIN_CONFIRMED,
        note="ผู้ใช้ยืนยัน 2026-07-25: โครงการนี้ได้สิทธิ BOI ยกเว้นภาษีนิติบุคคล 8 ปีในพื้นที่ทั่วไป · Jetty ได้ 12 ปี (ดูค่าถัดไป)",
    ),
    SettingSpec(
        key="financial.boi_tax_holiday_years_jetty",
        group=GROUP_FINANCIAL,
        label="ปีที่ยกเว้นภาษี BOI — Jetty",
        unit="ปี",
        default=12.0,
        minimum=0.0,
        maximum=15.0,
        step=1.0,
        origin=ORIGIN_CONFIRMED,
        note=(
            "ผู้ใช้ยืนยัน 2026-07-25: Jetty ได้ 12 ปี ยาวกว่าพื้นที่ทั่วไป · "
            "/financial ตอนนี้วิเคราะห์เฉพาะ GIS+ISB ที่ติดตั้งแล้ว จึงใช้ค่า 8 ปีเป็นหลัก "
            "ค่านี้จะมีผลเมื่อคิดเฟสที่รวม Jetty — เลือกได้เองจากสไลเดอร์ในหน้า Financial"
        ),
    ),
    SettingSpec(
        key="financial.degradation_pct_per_year",
        group=GROUP_FINANCIAL,
        label="แผงเสื่อมสภาพต่อปี (ปีที่ 2 เป็นต้นไป)",
        unit="%/ปี",
        default=0.4,
        minimum=0.0,
        maximum=5.0,
        step=0.01,
        origin=ORIGIN_LITERATURE,
        note=(
            "ค่ารับประกันของแผงรุ่นที่ติดตั้งจริง — Trina Vertex N TSM-NEG21C.20 (N-type i-TOPCon 715 W) "
            "ตามที่ระบุใน assets.yaml · รับประกันเชิงเส้น 30 ปี: ปีแรก 1% จากนั้น 0.40%/ปี เหลือ 87.4% ที่ปีที่ 30 "
            "(100 − 1 − 0.4×29 = 87.4 ลงตัวพอดี) · เดิมใช้ 0.55 ซึ่งเป็นช่วงกลางๆ ของอุตสาหกรรม ไม่เจาะจงรุ่นนี้"
        ),
    ),
    SettingSpec(
        key="financial.degradation_first_year_pct",
        group=GROUP_FINANCIAL,
        label="แผงเสื่อมสภาพปีแรก (LID)",
        unit="%",
        default=1.0,
        minimum=0.0,
        maximum=10.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note=(
            "ปีแรกเสื่อมมากกว่าปีถัดๆ ไปเพราะ light-induced degradation ซึ่งเกิดครั้งเดียว ไม่ใช่การปัดเศษของอัตรารายปี · "
            "ค่า 1% มาจากใบรับประกันของ Trina สำหรับรุ่นนี้โดยตรง · แยกเป็นคนละค่าเพื่อให้กระแสเงินสดที่เผยแพร่ "
            "ตรงกับใบรับประกันปีต่อปี"
        ),
    ),
    # --- uncertainty (2026-07-25, project B) ---------------------------------
    # These are SPREADS, not values: they say how unsure each assumption is, and
    # drive the P50/P90 table and the Monte Carlo on /financial. All start as
    # documented judgements rather than measurements - there is no multi-year
    # on-site yield record and no signed EPC price - so every one is settable
    # and every one is labelled as an estimate on screen.
    SettingSpec(
        key="financial.annual_yield_cv_pct",
        group=GROUP_FINANCIAL,
        label="ความแปรปรวนของพลังงานรายปี (สำหรับ P50/P90)",
        unit="% ของค่าเฉลี่ย",
        default=2.11,
        minimum=0.0,
        maximum=30.0,
        step=0.01,
        origin=ORIGIN_DERIVED,
        note=(
            "ผลผลิตแต่ละปีไม่เท่ากันเพราะปีที่เมฆมาก/ฝนมากต่างกัน ค่านี้คือส่วนเบี่ยงเบน "
            "มาตรฐานคิดเป็น % ของค่าเฉลี่ย · คำนวณจากรังสีอาทิตย์รายวันจริงของ NASA POWER "
            "(ALLSKY_SFC_SW_DWN) ที่พิกัดหนองแฟบ 12.71 N / 101.15 E ครบ 26 ปี (2000-2025): "
            "เฉลี่ย 1,852.6 kWh/m²/ปี · SD 39.0 · ปีแย่สุด 2011 = 1,792.1 · ปีดีสุด 2004 = 1,939.1 "
            "· เดิมใช้ 4% ตามงานวิจัยเขตร้อน (3-5%) ซึ่งกว้างเกินจริงเกือบเท่าตัวสำหรับไซต์นี้ "
            "· ยังไม่ใช่ค่าที่วัดจากมิเตอร์หน้างาน (โรงยังใหม่) และเป็นความแปรปรวนของ 'แสง' "
            "ไม่ใช่ของ 'ไฟที่ผลิตได้' โดยตรง · ตั้งเป็น 0 = ถือว่าทุกปีเท่ากันเป๊ะ แล้ว P90 จะเท่ากับ P50 "
            "· คำนวณซ้ำได้ด้วย financial/scripts/derive_annual_cv.py"
        ),
    ),
    SettingSpec(
        key="financial.capex_std_per_kwp_thb",
        group=GROUP_FINANCIAL,
        label="ความไม่แน่นอนของ CAPEX",
        unit="บาท/kWp (ส่วนเบี่ยงเบนมาตรฐาน)",
        default=4_000.0,
        minimum=0.0,
        maximum=30_000.0,
        step=500.0,
        origin=ORIGIN_PLACEHOLDER,
        note=(
            "CAPEX ตั้งต้น (฿30,000/kWp) ยังไม่ใช่ราคาจริงของโครงการ ค่านี้บอกว่า 'ไม่แน่ใจ "
            "ประมาณเท่าไร' ซึ่งเป็นตัวขับความกว้างของช่วง NPV มากที่สุด — เมื่อได้ราคาจริง "
            "จากสัญญาแล้ว ควรลดค่านี้ลงมาก หรือตั้งเป็น 0 ถ้าราคาถูกล็อกแล้ว"
        ),
    ),
    SettingSpec(
        key="financial.discount_rate_std_pct",
        group=GROUP_FINANCIAL,
        label="ความไม่แน่นอนของ WACC",
        unit="% (ส่วนเบี่ยงเบนมาตรฐาน)",
        default=1.5,
        minimum=0.0,
        maximum=10.0,
        step=0.1,
        origin=ORIGIN_PLACEHOLDER,
        note="WACC ตั้งต้น 8% ยังไม่ยืนยันกับฝ่ายการเงิน ค่านี้คือช่วงที่ยอมให้มันขยับตอนสุ่ม",
    ),
    SettingSpec(
        key="financial.tariff_std_thb_per_kwh",
        group=GROUP_FINANCIAL,
        label="ความไม่แน่นอนของค่าไฟที่หลีกเลี่ยงได้",
        unit="บาท/kWh (ส่วนเบี่ยงเบนมาตรฐาน)",
        default=0.3,
        minimum=0.0,
        maximum=3.0,
        step=0.05,
        origin=ORIGIN_PLACEHOLDER,
        note="ค่า Ft เปลี่ยนทุก 4 เดือน และโครงสร้างอัตราอาจถูกทบทวน ค่านี้คือช่วงที่ยอมให้ค่าไฟขยับ",
    ),
    SettingSpec(
        key="financial.monte_carlo_samples",
        group=GROUP_FINANCIAL,
        label="จำนวนรอบสุ่มของ Monte Carlo",
        unit="รอบ",
        default=2000.0,
        minimum=100.0,
        maximum=20_000.0,
        step=100.0,
        origin=ORIGIN_TUNING,
        note="ยิ่งมากยิ่งนิ่งแต่ช้าลง · 2,000 รอบใช้เวลาราว 0.5 วินาที",
    ),
    SettingSpec(
        key="financial.lifetime_years",
        group=GROUP_FINANCIAL,
        label="อายุโครงการที่ใช้วิเคราะห์",
        unit="ปี",
        default=25.0,
        minimum=1.0,
        maximum=40.0,
        step=1.0,
        origin=ORIGIN_LITERATURE,
    ),
    # --- C. loss factors ----------------------------------------------------
    SettingSpec(
        key="losses.external_shading_pct",
        group=GROUP_LOSSES,
        label="เงาจากสิ่งกีดขวางภายนอก",
        unit="%",
        default=2.0,
        minimum=0.0,
        maximum=30.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="เงาระหว่างแถวคำนวณจากเรขาคณิตจริงอยู่แล้ว · ค่านี้คือส่วนเผื่อสิ่งกีดขวางภายนอกที่ยังไม่มีการสำรวจ",
    ),
    SettingSpec(
        key="losses.mismatch_pct",
        group=GROUP_LOSSES,
        label="ความไม่เท่ากันของแผง (mismatch)",
        unit="%",
        default=2.0,
        minimum=0.0,
        maximum=20.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="losses.dc_wiring_pct",
        group=GROUP_LOSSES,
        label="สูญเสียในสาย DC",
        unit="%",
        default=2.0,
        minimum=0.0,
        maximum=20.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="losses.connections_pct",
        group=GROUP_LOSSES,
        label="สูญเสียที่จุดต่อ",
        unit="%",
        default=0.5,
        minimum=0.0,
        maximum=10.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="losses.availability_pct",
        group=GROUP_LOSSES,
        label="เวลาที่ระบบไม่พร้อมจ่าย (availability)",
        unit="%",
        default=3.0,
        minimum=0.0,
        maximum=30.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="losses.soiling_fallback_land_pct",
        group=GROUP_LOSSES,
        label="คราบสกปรกสำรอง: โซนบนพื้น",
        unit="%",
        default=2.5,
        minimum=0.0,
        maximum=30.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="ใช้เฉพาะเมื่อยังประเมินคราบจากข้อมูลจริงไม่ได้ (ดูแผง Soiling Advisor)",
    ),
    SettingSpec(
        key="losses.soiling_fallback_marine_pct",
        group=GROUP_LOSSES,
        label="คราบสกปรกสำรอง: โซนริมทะเล (Jetty)",
        unit="%",
        default=6.0,
        minimum=0.0,
        maximum=30.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
    ),
    # --- D. soiling model ---------------------------------------------------
    SettingSpec(
        key="soiling.pm10_reference_ug_m3",
        group=GROUP_SOILING,
        label="PM10 อ้างอิง",
        unit="µg/m³",
        default=50.0,
        minimum=1.0,
        maximum=500.0,
        step=1.0,
        origin=ORIGIN_LITERATURE,
        note="ระดับ PM10 ที่ทำให้อัตราสะสมเท่ากับค่าอ้างอิงด้านล่างพอดี",
    ),
    SettingSpec(
        key="soiling.pm10_rate_pct_per_day",
        group=GROUP_SOILING,
        label="อัตราสะสมจากฝุ่นที่ PM10 อ้างอิง",
        unit="%/วัน",
        default=0.20,
        minimum=0.0,
        maximum=5.0,
        step=0.01,
        origin=ORIGIN_LITERATURE,
        note="Kimber (2007) / Coello & Boyle (2019) รายงาน 0.1–0.3 %/วัน สำหรับพื้นที่ที่ไม่ใช่ทะเลทราย",
    ),
    SettingSpec(
        key="soiling.salt_rate_pct_per_day",
        group=GROUP_SOILING,
        label="อัตราสะสมเพิ่มจากละอองเกลือ (สูงสุด)",
        unit="%/วัน",
        default=0.18,
        minimum=0.0,
        maximum=5.0,
        step=0.01,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="soiling.dust_reference_ug_m3",
        group=GROUP_SOILING,
        label="ฝุ่นแร่อ้างอิง",
        unit="µg/m³",
        default=20.0,
        minimum=1.0,
        maximum=500.0,
        step=1.0,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="soiling.dust_rate_pct_per_day",
        group=GROUP_SOILING,
        label="อัตราสะสมเพิ่มจากฝุ่นแร่",
        unit="%/วัน",
        default=0.05,
        minimum=0.0,
        maximum=5.0,
        step=0.01,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="soiling.max_loss_pct",
        group=GROUP_SOILING,
        label="คราบสกปรกอิ่มตัวที่",
        unit="%",
        default=12.0,
        minimum=1.0,
        maximum=50.0,
        step=0.5,
        origin=ORIGIN_LITERATURE,
        note="เมื่อกระจกเคลือบเต็มแล้ว ฝุ่นที่เพิ่มมาแทบไม่ทำให้แย่ลงอีก",
    ),
    SettingSpec(
        key="soiling.rain_clean_threshold_mm",
        group=GROUP_SOILING,
        label="ฝนน้อยสุดที่เริ่มล้างแผง",
        unit="mm/วัน",
        default=0.25,
        minimum=0.0,
        maximum=20.0,
        step=0.05,
        origin=ORIGIN_LITERATURE,
        note="Kimber ใช้ 0.254 mm (0.01 นิ้ว) · ต่ำกว่านี้ถือว่าฝนปรอยไม่ได้ล้าง",
    ),
    SettingSpec(
        key="soiling.rain_full_clean_mm",
        group=GROUP_SOILING,
        label="ฝนที่ล้างสะอาดเต็มที่",
        unit="mm/วัน",
        default=5.0,
        minimum=0.5,
        maximum=100.0,
        step=0.5,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="soiling.residual_after_rain_pct",
        group=GROUP_SOILING,
        label="คราบที่เหลือหลังฝนล้าง",
        unit="%",
        default=0.3,
        minimum=0.0,
        maximum=5.0,
        step=0.05,
        origin=ORIGIN_LITERATURE,
        note="ฝนหนักแค่ไหนก็ยังเหลือคราบ และตัวฝนเองก็พาฝุ่นมาด้วย",
    ),
    SettingSpec(
        key="soiling.cleaning_trigger_pct",
        group=GROUP_SOILING,
        label="ระดับที่ควรล้างแผง",
        unit="%",
        default=3.0,
        minimum=0.5,
        maximum=20.0,
        step=0.1,
        origin=ORIGIN_TUNING,
        note="เกณฑ์ไว้วางแผน ไม่ใช่ข้อผูกพันตามสัญญา",
    ),
    SettingSpec(
        key="soiling.salt_exposure_marine",
        group=GROUP_SOILING,
        label="สัดส่วนที่โซนริมทะเลรับละอองเกลือ",
        unit="× (1=เต็มที่)",
        default=1.0,
        minimum=0.0,
        maximum=2.0,
        step=0.05,
        origin=ORIGIN_LITERATURE,
        note="Jetty อยู่บนสะพานเหนือน้ำ จึงรับเต็ม",
    ),
    SettingSpec(
        key="soiling.salt_exposure_inland",
        group=GROUP_SOILING,
        label="สัดส่วนที่โซนพื้นดินรับละอองเกลือ",
        unit="×",
        default=0.45,
        minimum=0.0,
        maximum=2.0,
        step=0.05,
        origin=ORIGIN_LITERATURE,
        note="GIS/ISB ตั้งลึกเข้าไปหลังอาคารคลัง · ยังไม่มีการสำรวจการตกสะสมเกลือจริง",
    ),
    # --- E. look-back windows ----------------------------------------------
    SettingSpec(
        key="windows.verification_days",
        group=GROUP_WINDOWS,
        label="Verification มองย้อนหลัง",
        unit="วัน",
        default=30.0,
        minimum=1.0,
        maximum=90.0,
        step=1.0,
        origin=ORIGIN_TUNING,
    ),
    SettingSpec(
        key="windows.anomaly_days",
        group=GROUP_WINDOWS,
        label="หาวันผิดปกติย้อนหลัง",
        unit="วัน",
        default=45.0,
        minimum=7.0,
        maximum=90.0,
        step=1.0,
        origin=ORIGIN_TUNING,
    ),
    SettingSpec(
        key="windows.soiling_days",
        group=GROUP_WINDOWS,
        label="ประเมินคราบสกปรกย้อนหลัง",
        unit="วัน",
        default=90.0,
        minimum=7.0,
        maximum=92.0,
        step=1.0,
        origin=ORIGIN_TUNING,
        note="สูงสุด 92 วัน เพราะ backfill ของ Open-Meteo Air-Quality ย้อนได้ไม่เกินนั้น",
    ),
    # --- F. diagnostics thresholds -----------------------------------------
    SettingSpec(
        key="diagnostics.anomaly_ratio_threshold",
        group=GROUP_DIAGNOSTICS,
        label="แจ้งเตือนเมื่อผลผลิตต่ำกว่า",
        unit="× ของค่าปกติ",
        default=0.70,
        minimum=0.1,
        maximum=1.0,
        step=0.01,
        origin=ORIGIN_TUNING,
        note="0.70 = ต่ำกว่า 70% ของค่าปกติรายวันของเดือนนั้น",
    ),
    SettingSpec(
        key="diagnostics.daylight_floor_kw",
        group=GROUP_DIAGNOSTICS,
        label="เกณฑ์ 'มีแดด' ของ Verification",
        unit="kW",
        default=0.5,
        minimum=0.0,
        maximum=50.0,
        step=0.1,
        origin=ORIGIN_TUNING,
        note="ชั่วโมงที่ทั้งค่าทำนายและค่าจริงต่ำกว่านี้ถือเป็นกลางคืน ไม่นำมาคิด",
    ),
    SettingSpec(
        key="diagnostics.cloud_max_age_minutes",
        group=GROUP_DIAGNOSTICS,
        label="ภาพเมฆเก่าได้ไม่เกิน",
        unit="นาที",
        default=90.0,
        minimum=10.0,
        maximum=1440.0,
        step=5.0,
        origin=ORIGIN_TUNING,
    ),
    SettingSpec(
        key="diagnostics.uv_max_age_minutes",
        group=GROUP_DIAGNOSTICS,
        label="UV รายวันเก่าได้ไม่เกิน",
        unit="นาที",
        default=2880.0,
        minimum=60.0,
        maximum=20_160.0,
        step=60.0,
        origin=ORIGIN_TUNING,
    ),
    SettingSpec(
        key="diagnostics.uv_hourly_max_age_minutes",
        group=GROUP_DIAGNOSTICS,
        label="UV รายชั่วโมงเก่าได้ไม่เกิน",
        unit="นาที",
        default=1080.0,
        minimum=60.0,
        maximum=10_080.0,
        step=30.0,
        origin=ORIGIN_TUNING,
    ),
    SettingSpec(
        key="diagnostics.nwp_min_lead_minutes",
        group=GROUP_DIAGNOSTICS,
        label="พยากรณ์อากาศต้องครอบคลุมล่วงหน้าอย่างน้อย",
        unit="นาที",
        default=360.0,
        minimum=30.0,
        maximum=4320.0,
        step=30.0,
        origin=ORIGIN_TUNING,
    ),
    SettingSpec(
        key="diagnostics.aerosol_min_lead_minutes",
        group=GROUP_DIAGNOSTICS,
        label="ข้อมูลฝุ่นต้องครอบคลุมล่วงหน้าอย่างน้อย",
        unit="นาที",
        default=180.0,
        minimum=30.0,
        maximum=4320.0,
        step=30.0,
        origin=ORIGIN_TUNING,
        note="ต่ำกว่านี้แล้ว lead +1..+6h ของโมเดลจะเงียบๆ กลับไปใช้ค่า default",
    ),
    # --- G. hand control (applied in the browser) --------------------------
    SettingSpec(
        key="hand.deadzone",
        group=GROUP_HAND,
        label="เขตนิ่ง (deadzone)",
        unit="สัดส่วนจอ",
        default=0.06,
        minimum=0.0,
        maximum=0.4,
        step=0.01,
        origin=ORIGIN_TUNING,
        note="มือขยับในระยะนี้จากกลางจอถือว่าไม่สั่งอะไร · สูงขึ้น = มือสั่นไม่กวนกล้อง แต่ต้องขยับมากขึ้น",
        frontend_only=True,
    ),
    SettingSpec(
        key="hand.pinch_engage_ratio",
        group=GROUP_HAND,
        label="ความไวท่าหนีบนิ้ว (เข้าโหมดซูม)",
        unit="อัตราส่วน",
        default=0.42,
        minimum=0.1,
        maximum=1.0,
        step=0.02,
        origin=ORIGIN_TUNING,
        note="สูงขึ้น = หนีบหลวมๆ ก็เข้าโหมดซูม แต่อาจสลับมาจากท่ากางมือง่ายขึ้น",
        frontend_only=True,
    ),
    SettingSpec(
        key="hand.rate_gain",
        group=GROUP_HAND,
        label="อัตราขยายการขยับมือ",
        unit="×",
        default=2.2,
        minimum=0.5,
        maximum=6.0,
        step=0.1,
        origin=ORIGIN_TUNING,
        note="สูงขึ้น = ขยับมือน้อยก็สั่งเต็มความเร็ว",
        frontend_only=True,
    ),
    SettingSpec(
        key="hand.azimuth_speed_rad_s",
        group=GROUP_HAND,
        label="ความเร็วหมุนกล้อง",
        unit="rad/วินาที",
        default=2.0,
        minimum=0.2,
        maximum=8.0,
        step=0.1,
        origin=ORIGIN_TUNING,
        frontend_only=True,
    ),
    SettingSpec(
        key="hand.polar_speed_rad_s",
        group=GROUP_HAND,
        label="ความเร็วขึ้น-ลงมุมกล้อง",
        unit="rad/วินาที",
        default=1.1,
        minimum=0.1,
        maximum=5.0,
        step=0.1,
        origin=ORIGIN_TUNING,
        frontend_only=True,
    ),
    SettingSpec(
        key="hand.zoom_speed_per_s",
        group=GROUP_HAND,
        label="ความเร็วซูม",
        unit="e-folds/วินาที",
        default=0.8,
        minimum=0.1,
        maximum=4.0,
        step=0.1,
        origin=ORIGIN_TUNING,
        frontend_only=True,
    ),
    SettingSpec(
        key="hand.latch_hold_seconds",
        group=GROUP_HAND,
        label="เวลาค้างท่า 👍 ก่อนสั่งเริ่ม/หยุด",
        unit="วินาที",
        default=0.35,
        minimum=0.05,
        maximum=3.0,
        step=0.05,
        origin=ORIGIN_TUNING,
        frontend_only=True,
    ),
    # --- H. expansion plan --------------------------------------------------
    SettingSpec(
        key="expansion.phase_a_additional_ac_kw",
        group=GROUP_EXPANSION,
        label="เฟสขยายที่ 1: กำลังที่เพิ่ม",
        unit="kW AC",
        default=100.0,
        minimum=0.0,
        maximum=50_000.0,
        step=10.0,
        origin=ORIGIN_AS_BUILT,
        note="assets.yaml ระบุเฟส 1.5 = +100 kW (inverter A05/A06) · 0 = ปิดเฟสนี้",
    ),
    SettingSpec(
        key="expansion.phase_b_additional_ac_kw",
        group=GROUP_EXPANSION,
        label="เฟสขยายที่ 2: กำลังที่เพิ่ม",
        unit="kW AC",
        default=300.0,
        minimum=0.0,
        maximum=50_000.0,
        step=10.0,
        origin=ORIGIN_AS_BUILT,
        note="assets.yaml ระบุเฟส 2 = +300 kW (เป้ารวม 600 kW AC)",
    ),
    SettingSpec(
        key="expansion.phase_c_additional_ac_kw",
        group=GROUP_EXPANSION,
        label="เฟสขยายที่ 3: กำลังที่เพิ่ม",
        unit="kW AC",
        default=0.0,
        minimum=0.0,
        maximum=50_000.0,
        step=10.0,
        origin=ORIGIN_TUNING,
        note="ยังไม่มีในแผน · ใส่ตัวเลขเพื่อลองดูว่าถ้าขยายต่อจะได้อะไร",
    ),
    SettingSpec(
        key="expansion.target_offset_a_pct",
        group=GROUP_EXPANSION,
        label="เป้าครอบคลุมโหลดที่ 1",
        unit="%",
        default=5.0,
        minimum=0.0,
        maximum=100.0,
        step=1.0,
        origin=ORIGIN_TUNING,
        note="0 = ไม่แสดงเป้านี้",
    ),
    SettingSpec(
        key="expansion.target_offset_b_pct",
        group=GROUP_EXPANSION,
        label="เป้าครอบคลุมโหลดที่ 2",
        unit="%",
        default=10.0,
        minimum=0.0,
        maximum=100.0,
        step=1.0,
        origin=ORIGIN_TUNING,
    ),
    SettingSpec(
        key="expansion.target_offset_c_pct",
        group=GROUP_EXPANSION,
        label="เป้าครอบคลุมโหลดที่ 3",
        unit="%",
        default=25.0,
        minimum=0.0,
        maximum=100.0,
        step=1.0,
        origin=ORIGIN_TUNING,
    ),
    # --- I. green savings: tariffs + carbon (2026-07-25) --------------------
    SettingSpec(
        key="green.normal_rate_thb_per_kwh",
        group=GROUP_GREEN,
        label="ค่าไฟปกติที่โซลาร์ไปแทน (TOU Peak, HV)",
        unit="บาท/kWh",
        default=4.1025,
        minimum=0.0,
        maximum=30.0,
        step=0.0001,
        origin=ORIGIN_LITERATURE,
        note="จากประกาศอัตราค่าไฟประเภทที่ 4 กิจการขนาดใหญ่ (ผู้ใช้ส่งไฟล์อ้างอิงมา 2026-07-19) · ประกาศใหม่ทุกปี จึงควรอัปเดตได้เอง",
    ),
    SettingSpec(
        key="green.ugt1_premium_thb_per_kwh",
        group=GROUP_GREEN,
        label="ส่วนเพิ่ม UGT1 (premium)",
        unit="บาท/kWh",
        default=0.0375,
        minimum=0.0,
        maximum=5.0,
        step=0.0001,
        origin=ORIGIN_LITERATURE,
        note="UGT1 = ค่าไฟปกติ (รวม Ft) + ส่วนเพิ่มนี้ · ระบบคิดต่อให้อัตโนมัติ ไม่ต้องกรอกยอดรวม",
    ),
    SettingSpec(
        key="green.ugt2_rate_thb_per_kwh",
        group=GROUP_GREEN,
        label="อัตรา UGT2 (Portfolio A, HV)",
        unit="บาท/kWh",
        default=4.0423,
        minimum=0.0,
        maximum=30.0,
        step=0.0001,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="green.ef_scope2_kg_per_kwh",
        group=GROUP_GREEN,
        label="ค่าการปล่อยคาร์บอนของกริด (Grid Emission Factor)",
        unit="kgCO₂/kWh",
        default=0.4758,
        minimum=0.0,
        maximum=2.0,
        step=0.0001,
        origin=ORIGIN_LITERATURE,
        note=(
            "แหล่งราชการไทย 2 แห่งให้ตัวเลขไม่ตรงกัน: เอกสารหลักเกณฑ์ UGT ของ กกพ. = 0.4758 "
            "(และ ~0.407 สำหรับปี 2565) · TGO grid-mix (จากไฟล์อ้างอิงที่ผู้ใช้ส่งมา 2026-07-19) = 0.4999 — "
            "ผู้ใช้เลือกใช้ค่าของ กกพ. เมื่อ 2026-07-25 เพราะอัตรา UGT1/UGT2 บนหน้าเดียวกันก็มาจากเอกสารฉบับนี้"
        ),
    ),
    SettingSpec(
        key="green.offpeak_rate_thb_per_kwh",
        group=GROUP_GREEN,
        label="ค่าไฟช่วง Off-Peak (TOU)",
        unit="บาท/kWh",
        default=4.1025,
        minimum=0.0,
        maximum=30.0,
        step=0.0001,
        origin=ORIGIN_PLACEHOLDER,
        note=(
            "ยังไม่มีอัตรา Off-Peak จริงในระบบ จึงตั้งเท่ากับอัตรา Peak ไว้ก่อน = ผลลัพธ์เท่าเดิมทุกประการ "
            "ไม่มีตัวเลขไหนขยับเงียบๆ · หน้า /tou คำนวณแล้วว่า ~32% ของพลังงานทั้งปีตกนอกช่วง Peak "
            "(เสาร์-อาทิตย์ทั้งวัน + ช่วง 06:00–09:00 ของวันทำงาน) พอกรอกอัตราจริงจากประกาศ ตัวเลขประหยัดจะแม่นขึ้นทันที"
        ),
    ),
    SettingSpec(
        key="green.offpeak_holiday_days",
        group=GROUP_GREEN,
        label="วันหยุดที่คิดเป็น Off-Peak ทั้งวัน",
        unit="วัน/ปี",
        default=0.0,
        minimum=0.0,
        maximum=40.0,
        step=1.0,
        origin=ORIGIN_PLACEHOLDER,
        note=(
            "กฟภ./กฟน. คิดเฉพาะวันหยุดในรายการที่ประกาศไว้เป็น Off-Peak ไม่ใช่ทุกวันหยุดราชการ "
            "ตั้ง 0 ไว้ก่อนเพื่อให้สัดส่วน Peak ที่รายงานเป็น 'เพดานบน' — ของจริง Off-Peak มีแต่จะมากกว่านี้ ไม่มีน้อยกว่า"
        ),
    ),
    SettingSpec(
        key="green.carbon_credit_unit_per_kwp_year",
        group=GROUP_GREEN,
        label="คาร์บอนเครดิตต่อกำลังติดตั้ง",
        unit="ตัน CO₂eq/kWp/ปี",
        default=0.901,
        minimum=0.0,
        maximum=10.0,
        step=0.001,
        origin=ORIGIN_LITERATURE,
        note="กฎง่ายๆ ที่ผู้ใช้ให้มา: 1 kWp → 901 kgCO₂/ปี · คิดจากกำลังติดตั้ง ไม่ได้คิดจากพลังงานที่ผลิตจริง",
    ),
    SettingSpec(
        key="green.trees_per_kwp_year",
        group=GROUP_GREEN,
        label="เทียบเท่าต้นไม้ต่อกำลังติดตั้ง",
        unit="ต้น/kWp/ปี",
        default=101.0,
        minimum=0.0,
        maximum=1000.0,
        step=1.0,
        origin=ORIGIN_LITERATURE,
    ),
    SettingSpec(
        key="green.carbon_price_thb_per_tonne",
        group=GROUP_GREEN,
        label="ราคาคาร์บอนเครดิตอ้างอิง",
        unit="บาท/ตัน CO₂eq",
        default=100.0,
        minimum=0.0,
        maximum=10_000.0,
        step=10.0,
        origin=ORIGIN_LITERATURE,
        note="ราคาตลาดอ้างอิงจากเอกสาร workshop คาร์บอนเครดิต · ราคาจริงผันผวนตามตลาด",
    ),
    # --- J. national grid fuel mix, for the hourly carbon curve (2026-07-25) -
    #
    # Shares of Thailand's WHOLE-SYSTEM electricity generation, in percent.
    # Defaults are EPPO's published 2566/2023 figures (219,540.04 GWh total,
    # GWh column reconciles exactly) - real, but an ANNUAL average. Enter a
    # monthly table and the API's origin label flips from "annual" to
    # "published".
    #
    # Deliberately the NATIONAL split, not EGAT's own-system table: the latter
    # shows imports at ~1% because it only covers plant EGAT itself runs, and
    # stacking that against a national load curve would misstate the merit order.
    #
    # They are percentages that need not sum to exactly 100: the model
    # normalises whatever it is given, so a published table that rounds to
    # 99.8% is usable as-is rather than being an error to reconcile by hand.
    SettingSpec(
        key="gridmix.natural_gas_pct",
        group=GROUP_GRIDMIX,
        label="ก๊าซธรรมชาติ",
        unit="% ของการผลิตไฟฟ้าทั้งประเทศ",
        default=58.61,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="สนพ. 2566: 128,678.77 GWh (58.61%) — ก๊าซเป็นเชื้อเพลิงชายขอบเกือบทุกชั่วโมงในไทย",
    ),
    SettingSpec(
        key="gridmix.coal_lignite_pct",
        group=GROUP_GRIDMIX,
        label="ถ่านหิน/ลิกไนต์",
        unit="% ของการผลิตไฟฟ้าทั้งประเทศ",
        default=13.1,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="สนพ. 2566: 28,758.06 GWh (13.10%) · แบบจำลองใช้ค่าคาร์บอนถ่านหินของ IPCC (820 gCO₂eq/kWh) ซึ่งต่ำกว่าลิกไนต์จริงของไทย",
    ),
    SettingSpec(
        key="gridmix.imported_pct",
        group=GROUP_GRIDMIX,
        label="นำเข้า (ส่วนใหญ่พลังน้ำ สปป.ลาว)",
        unit="% ของการผลิตไฟฟ้าทั้งประเทศ",
        default=14.94,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="สนพ. 2566: 32,805.15 GWh (14.94%) — ส่วนใหญ่พลังน้ำจาก สปป.ลาว",
    ),
    SettingSpec(
        key="gridmix.renewables_pct",
        group=GROUP_GRIDMIX,
        label="พลังงานหมุนเวียนในประเทศ",
        unit="% ของการผลิตไฟฟ้าทั้งประเทศ",
        default=10.42,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="สนพ. 2566: 22,867.18 GWh (10.42%) · แบบจำลองใช้ค่าคาร์บอนของโซลาร์ (48 gCO₂eq/kWh) ซึ่งต่ำกว่าชีวมวลที่เป็นสัดส่วนใหญ่ในไทย",
    ),
    SettingSpec(
        key="gridmix.hydro_pct",
        group=GROUP_GRIDMIX,
        label="พลังน้ำในประเทศ",
        unit="% ของการผลิตไฟฟ้าทั้งประเทศ",
        default=2.92,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="สนพ. 2566: 6,421.04 GWh (2.92%) — พลังน้ำในประเทศ แยกจากที่นำเข้า",
    ),
    SettingSpec(
        key="gridmix.oil_pct",
        group=GROUP_GRIDMIX,
        label="น้ำมัน/ดีเซล",
        unit="% ของการผลิตไฟฟ้าทั้งประเทศ",
        default=0.01,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        origin=ORIGIN_LITERATURE,
        note="สนพ. 2566: 9.85 GWh (0.01%) — แทบไม่เดินเครื่องแล้ว แต่คงไว้ในลำดับ merit-order เพราะเป็นโรงพีคที่แพงและสกปรกที่สุด",
    ),
)

BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SPECS}


def spec(key: str) -> SettingSpec:
    """The spec for `key`, or KeyError for an unknown one - callers translate
    that into a 404/422 rather than silently accepting an unknown setting."""
    return BY_KEY[key]


def default(key: str) -> float:
    return BY_KEY[key].default


def validate(key: str, value: float) -> float:
    """Bounds-check one write. Raises ValueError with a Thai message the API
    passes straight through, since these are user-facing form errors."""
    s = spec(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{s.label}: ต้องเป็นตัวเลข")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise ValueError(f"{s.label}: ต้องเป็นตัวเลขที่ใช้งานได้")
    if numeric < s.minimum or numeric > s.maximum:
        raise ValueError(f"{s.label}: ต้องอยู่ระหว่าง {s.minimum:g} ถึง {s.maximum:g} {s.unit}".strip())
    return numeric
