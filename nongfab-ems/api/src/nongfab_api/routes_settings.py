"""GET/PUT/DELETE /settings - the values a user is allowed to change
(2026-07-25).

The response is self-describing: every field carries its group, Thai label, unit,
bounds, step, default, current effective value, and where the default came from
(`origin`). That is what lets ONE generic form on the frontend render all eight
groups the user asked for, instead of a hand-built screen per group.

Permission model, as the user chose: anyone signed in can READ the settings and
try values locally in their own browser; only an **admin** can publish a value as
the shared system default. So GET is viewer-level and every write requires admin.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import AuthenticatedUser, require_role
from .settings_registry import (
    BY_KEY,
    GROUP_LABELS,
    ORIGIN_LABELS,
    SPECS,
)
from .settings_store import SettingsStore, effective, is_overridden, override_meta

router = APIRouter(tags=["settings"])


class SettingOut(BaseModel):
    key: str
    group: str
    group_label: str
    label: str
    unit: str
    default: float
    value: float
    minimum: float
    maximum: float
    step: float
    origin: str
    origin_label: str
    note: str
    frontend_only: bool
    # True when an admin has published a value for this key; the UI shows a
    # "reset to default" affordance only for those.
    overridden: bool
    updated_at: datetime | None = None
    updated_by: str | None = None


class SettingsResponse(BaseModel):
    settings: list[SettingOut]
    groups: dict[str, str]
    origins: dict[str, str]
    # Whether THIS caller may publish a shared default (admin) or is limited to
    # trying values in their own browser.
    can_publish: bool


class SettingsUpdateRequest(BaseModel):
    # key -> new value. Validated as a whole: one bad field rejects the entire
    # submission rather than applying half of it (see SettingsStore.put_many).
    values: dict[str, float] = Field(default_factory=dict)


class SettingsUpdateResponse(BaseModel):
    updated: dict[str, float]
    settings: list[SettingOut]


def _out(spec) -> SettingOut:
    meta = override_meta().get(spec.key)
    return SettingOut(
        key=spec.key,
        group=spec.group,
        group_label=GROUP_LABELS.get(spec.group, spec.group),
        label=spec.label,
        unit=spec.unit,
        default=spec.default,
        value=effective(spec.key),
        minimum=spec.minimum,
        maximum=spec.maximum,
        step=spec.step,
        origin=spec.origin,
        origin_label=ORIGIN_LABELS.get(spec.origin, spec.origin),
        note=spec.note,
        frontend_only=spec.frontend_only,
        overridden=is_overridden(spec.key),
        updated_at=meta[0] if meta else None,
        updated_by=meta[1] if meta else None,
    )


def _all_out() -> list[SettingOut]:
    return [_out(spec) for spec in SPECS]


def _store(request: Request) -> SettingsStore:
    store = getattr(request.app.state, "settings_store", None)
    if store is None:  # pragma: no cover - wired in main.py's lifespan
        raise HTTPException(status_code=503, detail="settings store is not ready")
    return store


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(user: AuthenticatedUser = Depends(require_role("viewer"))) -> SettingsResponse:
    return SettingsResponse(
        settings=_all_out(),
        groups=dict(GROUP_LABELS),
        origins=dict(ORIGIN_LABELS),
        can_publish=user.role == "admin",
    )


@router.put("/settings", response_model=SettingsUpdateResponse)
async def put_settings(
    payload: SettingsUpdateRequest, request: Request, user: AuthenticatedUser = Depends(require_role("admin"))
) -> SettingsUpdateResponse:
    if not payload.values:
        raise HTTPException(status_code=422, detail="ไม่มีค่าที่จะบันทึก")
    try:
        updated = await _store(request).put_many(payload.values, updated_by=user.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"ไม่รู้จักค่าตั้งชื่อ '{exc.args[0]}'") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _reapply(request)
    return SettingsUpdateResponse(updated=updated, settings=_all_out())


@router.delete("/settings/{key:path}", response_model=SettingsUpdateResponse)
async def delete_setting(key: str, request: Request, _user: AuthenticatedUser = Depends(require_role("admin"))) -> SettingsUpdateResponse:
    """Reset ONE setting back to its registry default. `{key:path}` because the
    keys are dotted (`zone.GIS.tilt_deg`)."""
    if key not in BY_KEY:
        raise HTTPException(status_code=404, detail=f"ไม่รู้จักค่าตั้งชื่อ '{key}'")
    await _store(request).clear(key)
    _reapply(request)
    return SettingsUpdateResponse(updated={key: effective(key)}, settings=_all_out())


@router.post("/settings/reset", response_model=SettingsUpdateResponse)
async def reset_settings(request: Request, _user: AuthenticatedUser = Depends(require_role("admin"))) -> SettingsUpdateResponse:
    """Reset EVERY setting back to the defaults this build ships with."""
    await _store(request).clear_all()
    _reapply(request)
    return SettingsUpdateResponse(updated={}, settings=_all_out())


def _reapply(request: Request) -> None:
    """Push the new effective values into the places that need them injected
    rather than read per-request (the asset registry's overrides, the loss
    model's factors, the soiling model's coefficients). Wired in
    settings_service; imported lazily so this module stays importable on its
    own."""
    from .settings_service import apply_effective_settings

    apply_effective_settings()
