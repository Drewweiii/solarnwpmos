"""GET /sources - where this site's hand-entered numbers came from, and whether
the agency that issued them has published anything new since (2026-07-25).

This is the "เพื่อความชัวร์" half of connecting to EGAT / PEA / กกพ / PTT LNG.
The other half - pulling live numbers - is only possible for EGAT (see
`routes_grid`); every Thai tariff announcement is a scanned image, so the
figures here are transcribed by hand and this route exists to make sure nobody
forgets that, and to notice when a transcription has gone stale.

See `official_sources` for the registry, the compliance notes, and the evidence
behind "watch the documents, never OCR the rates".
"""

from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import official_sources
from .auth import require_role

router = APIRouter(tags=["sources"])

METHOD_NOTE = (
    "ระบบไม่ได้อ่านตัวเลขจากประกาศโดยอัตโนมัติ เพราะประกาศอัตราค่าไฟของไทยเป็นไฟล์สแกน "
    "และการใช้ OCR กับเลขไทยให้ผลผิดแบบเงียบ ๆ (ทดสอบแล้ว) ระบบจึงทำเฉพาะสิ่งที่แม่นยำแน่นอน "
    "คือจำว่าค่าแต่ละตัวมาจากเอกสารฉบับใด แล้วคอยเทียบว่าหน่วยงานออกเอกสารใหม่หรือยัง"
)


class QuotedValueOut(BaseModel):
    label: str
    value: str
    code_location: str
    note: str = ""


class SourceOut(BaseModel):
    key: str
    agency: str
    agency_full: str
    page_url: str
    purpose: str
    quoted: list[QuotedValueOut]
    watch_documents: bool
    status: str
    detail: str
    documents_now: list[str]
    added: list[str]
    removed: list[str]


class SourcesResponse(BaseModel):
    overall_status: str
    checked_at: datetime | None
    baseline_captured: str
    sources: list[SourceOut]
    method_note: str = METHOD_NOTE


# Shared across viewers, like the grid snapshot: these pages move on the scale
# of months, and one check an hour for the whole deployment is already generous
# toward the agencies' servers.
_cache: dict[str, object] = {"at": 0.0, "checks": None}


async def _cached_checks() -> list[official_sources.SourceCheck]:
    now = time.monotonic()
    fetched_at = float(_cache["at"])  # type: ignore[arg-type]
    cached = _cache["checks"]
    if cached is not None and now - fetched_at < official_sources.MIN_REFRESH_SECONDS:
        return cached  # type: ignore[return-value]
    checks = await official_sources.check_all()
    _cache["at"] = now
    _cache["checks"] = checks
    return checks


@router.get("/sources", response_model=SourcesResponse)
async def get_sources(_user=Depends(require_role("viewer"))) -> SourcesResponse:
    checks = await _cached_checks()
    by_key = {c.key: c for c in checks}

    out: list[SourceOut] = []
    for source in official_sources.SOURCES:
        check = by_key.get(source.key)
        out.append(
            SourceOut(
                key=source.key,
                agency=source.agency,
                agency_full=source.agency_full,
                page_url=source.page_url,
                purpose=source.purpose,
                quoted=[
                    QuotedValueOut(label=q.label, value=q.value, code_location=q.code_location, note=q.note)
                    for q in source.quoted
                ],
                watch_documents=source.watch_documents,
                status=check.status if check else official_sources.STATUS_UNREACHABLE,
                detail=check.detail if check else "ยังไม่ได้ตรวจสอบ",
                documents_now=check.documents_now if check else [],
                added=check.added if check else [],
                removed=check.removed if check else [],
            )
        )

    return SourcesResponse(
        overall_status=official_sources.overall_status(checks),
        checked_at=next((c.checked_at for c in checks if c.checked_at), None),
        baseline_captured=official_sources.BASELINE_CAPTURED,
        sources=out,
    )
