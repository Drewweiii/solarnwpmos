"""GET /provenance - click any number, see where it came from (2026-07-26, project O).

Returns the chain behind one published figure: which source, through which
model, using which settings, and what each of those links' `origin` is. See
`provenance.py` for the registry and for why a setting's origin is read live
from `settings_registry` rather than restated here.

Viewer-level on purpose. Being able to see that a number rests on a placeholder
is exactly the kind of thing a public dashboard should not hide behind a login.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require_role
from .provenance import BY_VALUE_KEY, ProvenanceEntry, resolve_step, weakest_origin

router = APIRouter(tags=["provenance"])

_INTRO = (
    "ทุกตัวเลขบนเว็บนี้ตามรอยกลับไปหาที่มาได้ — แหล่งข้อมูล → โมเดล → ค่าที่ตั้งไว้ → "
    "และแต่ละขั้นมาจากไหน (ยืนยันแล้ว / as-built / งานวิจัย / ค่าประมาณ)"
)

_WEAKEST_NOTE = (
    "ระดับความน่าเชื่อถือที่แสดงคือ 'ขั้นที่อ่อนที่สุดในสาย' ไม่ใช่ค่าเฉลี่ย — "
    "ตัวเลขจะแข็งแรงได้แค่เท่ากับข้อมูลที่อ่อนที่สุดที่มันใช้"
)


class StepOut(BaseModel):
    kind: str
    label: str
    detail: str
    setting_key: str | None
    origin: str | None
    origin_label: str
    # The setting's own note and current default, read live from the registry -
    # never a copy stored in the provenance table.
    registry_note: str
    default_value: float | None
    unit: str


class ProvenanceOut(BaseModel):
    key: str
    label: str
    unit: str
    steps: list[StepOut]
    caveat: str
    shown_on: list[str]
    # The least-trustworthy origin anywhere in the chain. This is the headline,
    # not the best or the average - see provenance.weakest_origin.
    weakest_origin: str | None
    weakest_origin_label: str
    weakest_note: str = _WEAKEST_NOTE


class ProvenanceIndexOut(BaseModel):
    intro: str = _INTRO
    keys: list[str]


def _out(entry: ProvenanceEntry) -> ProvenanceOut:
    weakest = weakest_origin(entry)
    steps = [StepOut(**resolve_step(step)) for step in entry.steps]
    label = next((s.origin_label for s in steps if s.origin == weakest), "")
    return ProvenanceOut(
        key=entry.key,
        label=entry.label,
        unit=entry.unit,
        steps=steps,
        caveat=entry.caveat,
        shown_on=entry.shown_on,
        weakest_origin=weakest,
        weakest_origin_label=label,
    )


@router.get("/provenance", response_model=ProvenanceIndexOut)
async def list_provenance(_user=Depends(require_role("viewer"))) -> ProvenanceIndexOut:
    return ProvenanceIndexOut(keys=sorted(BY_VALUE_KEY))


@router.get("/provenance/{key:path}", response_model=ProvenanceOut)
async def get_provenance(key: str, _user=Depends(require_role("viewer"))) -> ProvenanceOut:
    entry = BY_VALUE_KEY.get(key)
    if entry is None:
        # Naming the available keys turns a 404 into something a developer can
        # act on - these keys are written by hand at call sites and a typo is
        # the likeliest way to land here.
        raise HTTPException(
            status_code=404,
            detail=f"unknown provenance key '{key}'. known: {sorted(BY_VALUE_KEY)}",
        )
    return _out(entry)
