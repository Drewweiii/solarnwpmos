"""Provenance + staleness watch for the official Thai energy sources this site
quotes: EGAT, PEA, กกพ (ERC) and PTT LNG (2026-07-25).

The problem this solves. Several numbers on this dashboard are tariffs and
emission factors transcribed by hand from official announcements - the TOU HV
peak rate, the UGT1 premium, the UGT2 portfolio rate, the scope-2 emission
factor. They are correct on the day they are typed in and silently wrong the
day the agency republishes. Nothing in the site knew where any of them came
from, and nothing would ever notice a new announcement.

Why this is a WATCHER and not a scraper. Extracting the numbers automatically
was attempted first and does not work - established by testing, not assumed:

  * PEA/กกพ rate announcements (`ประกาศ กฟภ. UGT2.pdf` and friends) are 300 dpi
    scanned JPEGs with no text layer at all - `pdftotext` yields ~10 characters
    from a whole document.
  * OCR does not rescue them. tesseract with Thai langdata reads the prose
    well and the DIGITS badly, because the figures are Thai numerals; three
    configurations disagreed on every rate cell, produced Thai letters inside
    numbers (๓.ฒ๕๒๐, ๐.๐ซ่๑๒๐), and misread the announcement year as ๒๕๐๕ (1962).
    Those errors are silent and plausible-looking - the worst possible property
    for a number feeding a money calculation.
  * Even PEA's `electricity_tariff.pdf`, which DOES have a real text layer,
    contains zero four-decimal numbers: its 61 rate tables are embedded images
    inside an otherwise-textual PDF.

So this module never guesses a rate. It does the part that is exactly
reliable: record which official document each hand-entered number came from,
check that the agency's page is still reachable, and compare the documents
published there now against the list recorded when the number was transcribed.
A document appearing or disappearing is a fact about hyperlinks, not an OCR
inference - so when this says "the agency published something new", it is
right, and a human then reads the PDF and updates the value.

Thailand-first (CLAUDE.md): every source here is the Thai authority that
actually governs this site's electricity - PEA is its distribution utility,
กกพ the regulator, EGAT the system operator, PTT LNG the owner.

Compliance. Checked when written: `erc.or.th/robots.txt` is `Disallow:` (all
allowed); `pea.co.th`'s wildcard block disallows only admin/search/user paths,
not `/our-services/` or `/sites/default/files/`; `sothailand.com` publishes no
directives. EGAT's own `robots.txt` DOES disallow `/home/wp-content/`, which is
where its PDFs live - so EGAT-hosted announcement files are deliberately NOT
fetched here, and the equivalents hosted by กกพ and PEA are watched instead.
One HEAD-like GET per page, at most on the cadence the route caches at.
"""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "NongFabEMS/1.0 (PTT LNG Nong Fab solar dashboard; research use)"
REQUEST_TIMEOUT_SECONDS = 25.0

# Agency pages change on the scale of months (a tariff revision, a new UGT
# announcement). Checking hourly is already far more often than anything moves.
MIN_REFRESH_SECONDS = 3600.0

# The date every baseline below was captured, and every quoted value verified
# against the document named in it.
BASELINE_CAPTURED = "2026-07-25"


@dataclass(frozen=True)
class QuotedValue:
    """One number on this site that was transcribed from an official document."""

    label: str
    value: str
    # Where it lives in the code, so a reader can go change it.
    code_location: str
    note: str = ""


@dataclass(frozen=True)
class OfficialSource:
    """One agency page this site depends on, and what was taken from it."""

    key: str
    agency: str
    agency_full: str
    # The human-readable page a person should open to check the numbers.
    page_url: str
    purpose: str
    quoted: tuple[QuotedValue, ...] = ()
    # Document filenames published on `page_url` when the baseline was taken.
    # Filenames only, not full URLs: agencies reorganise directories without
    # reissuing a document, and a moved file is not a new announcement.
    baseline_documents: tuple[str, ...] = ()
    # False for pages that publish no documents to diff (a live JSON feed, or
    # a corporate site) - those are reachability-only.
    watch_documents: bool = True


# --- The registry ------------------------------------------------------------
#
# Baselines were captured by fetching each page on BASELINE_CAPTURED. Values
# quoted below were verified against the named documents on that same date.

SOURCES: tuple[OfficialSource, ...] = (
    OfficialSource(
        key="egat_sysgen",
        agency="กฟผ.",
        agency_full="การไฟฟ้าฝ่ายผลิตแห่งประเทศไทย (EGAT)",
        page_url="https://www.sothailand.com/sysgen/",
        purpose="ข้อมูลกำลังผลิตของระบบไฟฟ้าทั้งประเทศแบบเรียลไทม์ (แผน/จริง/สถิติ peak)",
        quoted=(),  # nothing transcribed - this one is a live feed, see egat_grid.py
        watch_documents=False,
    ),
    OfficialSource(
        key="pea_tariff",
        agency="กฟภ.",
        agency_full="การไฟฟ้าส่วนภูมิภาค (PEA)",
        page_url="https://www.pea.co.th/our-services/tariff",
        purpose="อัตราค่าไฟฟ้าที่ไซต์นี้ใช้จริง (กฟภ. เป็นผู้จำหน่ายไฟให้หนองแฟบ) และประกาศอัตรา UGT",
        quoted=(
            QuotedValue(
                label="ค่าไฟฟ้าอัตราปกติ TOU ช่วง Peak แรงดันสูง",
                value="4.1025 บาท/kWh",
                code_location="api/green_savings.py: NORMAL_TOU_HV_PEAK_THB_PER_KWH",
            ),
            QuotedValue(
                label="ส่วนเพิ่ม (Premium) ของ UGT1 ระดับขายปลีก",
                value="0.0375 บาท/kWh",
                code_location="api/green_savings.py: UGT1_RETAIL_PREMIUM_THB_PER_KWH",
            ),
        ),
        baseline_documents=(
            "electricity_tariff.pdf",
            "ประกาศอัตรา UGT1.pdf",
            "ประกาศ กฟภ. UGT1 2569.pdf",
            "ประกาศ กฟภ. UGT2.pdf",
            "ประกาศค่าบริการเลือกใช้อัตรา TOU_0.pdf",
            "Electricity_Tariff_2015.pdf",
            "Electricity_Tariff_JAN_2023.pdf",
            "Electricity_Tariff_MAY_2023.pdf",
            "Electricity_Tariff_NOV_2018.pdf",
            "Electricity Tariff 2012.pdf",
            "FiTv_2565.pdf",
            "FiTv_2566.pdf",
            "FiTv_2567.pdf",
            "FiTv_2568.pdf",
            "FiTv_2569.pdf",
            "PEA_Contact_Channel.pdf",
        ),
    ),
    OfficialSource(
        key="erc_ugt",
        agency="กกพ.",
        agency_full="สำนักงานคณะกรรมการกำกับกิจการพลังงาน (ERC)",
        page_url="https://www.erc.or.th/th/util-green-tariff",
        purpose="หลักเกณฑ์และอัตราค่าบริการไฟฟ้าสีเขียว (UGT1/UGT2) ซึ่งเป็นตัวกำหนดหน่วยที่หักลบได้",
        quoted=(
            QuotedValue(
                label="อัตรา UGT2 Portfolio A แรงดันสูง ระดับขายปลีก",
                value="4.0423 บาท/kWh",
                code_location="api/green_savings.py: UGT2_PORTFOLIO_A_HV_THB_PER_KWH",
            ),
            QuotedValue(
                label="Grid Emission Factor (scope 2)",
                value="0.4999 kgCO₂/kWh",
                code_location="api/green_savings.py: EF_SCOPE2_KG_CO2_PER_KWH",
                note=(
                    "⚠️ เอกสารหลักเกณฑ์ UGT ของ กกพ. เอง ระบุ Grid Emission Factor ที่ "
                    "0.4758 tCO₂/MWh (ณ มี.ค. 2563) และประมาณ 0.407 tCO₂/MWh ในปี 2565 "
                    "ซึ่งไม่ตรงกับค่าที่เว็บนี้ใช้อยู่ — ต้องให้ผู้ดูแลตัดสินใจว่าจะยึดค่าใด "
                    "เพราะกระทบตัวเลขคาร์บอนที่เผยแพร่บนหน้า Energy Report"
                ),
            ),
        ),
        baseline_documents=(
            "1.ประกาศ กกพ. เรื่อง หลักเกณฑ์การให้บริการและการกำหนดอัตราค่าบริการไฟฟ้าสีเขียว (Utility Green Tariff) พ.ศ. 2566.pdf",
            "2.หลักเกณฑ์การกำหนดอัตราค่าบริการไฟฟ้าสีเขียว (Utility Green Tariff UGT).pdf",
            "20241129_ประกาศอัตรา_UGT1_กฟผ.pdf",
            "20260123_ร่าง_ประกาศอัตรา_UGT1_ปี_2569.pdf",
            "3.Proclamation of the Energy Regulatory Commission on Criteria for Service"
            " and Determination of Rates for Green Electricity Service 2566.pdf",
            "4.UGT Criteria.pdf",
            "5. ประกาศ กกพ. เรื่อง มาตรฐานการออกใบรับรองสำหรับการให้บริการไฟฟ้าสีเขียว พ.ศ.2568.pdf",
            "6.Notification of the Energy Regulatory Commission on Certification Standards for Green Electricity Provision 2025.pdf",
            "7.คำอธิบายร่างประกาศ กกพ. เรื่องมาตรฐานการออกใบรับรองสำหรับการให้บริการไฟฟ้าสีเขียว.pdf",
            "8. Explanatory Note Proclamation of the Energy Regulatory Commission on Certification Standard for Green Electricity Provision B.E.pdf",
            "ประกาศ กฟภ. UGT1 2569.pdf",
            "ประกาศ กฟภ. UGT2.pdf",
            "ประกาศอัตรา UGT1.pdf",
        ),
    ),
    OfficialSource(
        key="erc_tariff",
        agency="กกพ.",
        agency_full="สำนักงานคณะกรรมการกำกับกิจการพลังงาน (ERC)",
        page_url="https://www.erc.or.th/th/electricity-service-rate",
        purpose="ค่า Ft และโครงสร้างอัตราค่าไฟฟ้าฐาน ซึ่งเปลี่ยนทุก 4 เดือนและทำให้ค่าไฟที่ใช้คำนวณเก่าได้",
        quoted=(),
        # This page renders its figures through an embedded PDF viewer rather
        # than linking documents, so there is no link list to diff - watch that
        # it stays reachable and let a human read the current Ft there.
        watch_documents=False,
    ),
    OfficialSource(
        key="pttlng",
        agency="PTT LNG",
        agency_full="บริษัท พีทีที แอลเอ็นจี จำกัด",
        page_url="https://www.pttlng.com/",
        purpose="เจ้าของคลัง LNG หนองแฟบ (Terminal 2) ซึ่งเป็นที่ตั้งของระบบโซลาร์นี้",
        quoted=(),
        # Corporate site: no operational or tariff data is published, so there
        # is nothing to diff. Kept in the registry so the dashboard names its
        # owner rather than leaving the fourth agency silently unrepresented.
        watch_documents=False,
    ),
)


STATUS_OK = "ok"
STATUS_CHANGED = "changed"
STATUS_UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class SourceCheck:
    """The result of checking one source right now."""

    key: str
    status: str
    detail: str
    documents_now: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    checked_at: datetime | None = None


_PDF_HREF = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)


def extract_document_names(page_html: str) -> list[str]:
    """Filenames of every PDF linked from a page, percent-decoded and
    deduplicated. Filenames rather than URLs so a directory reorganisation
    doesn't masquerade as a brand-new announcement."""
    names: set[str] = set()
    for href in _PDF_HREF.findall(page_html):
        decoded = urllib.parse.unquote(html.unescape(href))
        name = decoded.rsplit("/", 1)[-1].strip()
        if name:
            names.add(name)
    return sorted(names)


def diff_documents(baseline: tuple[str, ...] | list[str], now: list[str]) -> tuple[list[str], list[str]]:
    """(added, removed) between the recorded baseline and what is published
    now. Both sorted, so the output is stable to compare and to display."""
    baseline_set, now_set = set(baseline), set(now)
    return sorted(now_set - baseline_set), sorted(baseline_set - now_set)


def evaluate(source: OfficialSource, page_html: str | None, checked_at: datetime) -> SourceCheck:
    """Turn one fetch into a verdict. Pure - the network lives in `check_all`.

    An unreachable page is reported as such and never as "unchanged": the whole
    point is to notice a change, and a failed fetch is an absence of evidence,
    not evidence of absence.
    """
    if page_html is None:
        return SourceCheck(
            key=source.key,
            status=STATUS_UNREACHABLE,
            detail="เข้าหน้าเว็บของหน่วยงานไม่ได้ในขณะนี้ จึงยังตรวจไม่ได้ว่ามีประกาศใหม่หรือไม่",
            checked_at=checked_at,
        )

    if not source.watch_documents:
        return SourceCheck(
            key=source.key,
            status=STATUS_OK,
            detail="เข้าถึงได้ตามปกติ (หน้านี้ไม่ได้เผยแพร่เป็นไฟล์เอกสารให้เทียบรายการ)",
            checked_at=checked_at,
        )

    now = extract_document_names(page_html)
    added, removed = diff_documents(source.baseline_documents, now)
    if not added and not removed:
        return SourceCheck(
            key=source.key,
            status=STATUS_OK,
            detail=f"รายการเอกสารทางการ {len(now)} ฉบับ ตรงกับที่บันทึกไว้เมื่อ {BASELINE_CAPTURED}",
            documents_now=now,
            checked_at=checked_at,
        )

    parts = []
    if added:
        parts.append(f"มีเอกสารใหม่ {len(added)} ฉบับ")
    if removed:
        parts.append(f"เอกสารหายไป {len(removed)} ฉบับ")
    return SourceCheck(
        key=source.key,
        status=STATUS_CHANGED,
        detail=(
            f"{' และ '.join(parts)} เทียบกับที่บันทึกไว้เมื่อ {BASELINE_CAPTURED} — "
            "ควรเปิดอ่านและตรวจสอบว่าค่าที่เว็บนี้ใช้อยู่ยังตรงกับประกาศล่าสุดหรือไม่"
        ),
        documents_now=now,
        added=added,
        removed=removed,
        checked_at=checked_at,
    )


def overall_status(checks: list[SourceCheck]) -> str:
    """Worst verdict across all sources - `changed` outranks `unreachable`
    because a real new announcement is actionable while a timeout is not."""
    if any(c.status == STATUS_CHANGED for c in checks):
        return STATUS_CHANGED
    if any(c.status == STATUS_UNREACHABLE for c in checks):
        return STATUS_UNREACHABLE
    return STATUS_OK


async def check_all(client: httpx.AsyncClient | None = None) -> list[SourceCheck]:
    """Fetch every registered page once and evaluate it."""
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )
    try:
        now = datetime.now(timezone.utc)
        return [evaluate(source, await _get_text(client, source.page_url), now) for source in SOURCES]
    finally:
        if owns_client:
            await client.aclose()


async def _get_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.text
    except Exception as exc:  # noqa: BLE001 - any upstream problem is "can't check"
        logger.warning("official_sources: %s unreachable (%s)", url, exc)
        return None
