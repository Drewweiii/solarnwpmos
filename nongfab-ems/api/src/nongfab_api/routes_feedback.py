"""POST /feedback (any signed-in visitor, viewer role or above) and GET
/feedback (admin only) - a simple one-way contact/feedback channel from
visitors to admin, per the user's explicit request for "a way to send
questions to admin, like feedback or otherwise". No reply/resolve workflow -
just submit and list, kept intentionally minimal.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .auth import AuthenticatedUser, require_role
from .models import FeedbackMessageORM, as_utc

router = APIRouter(tags=["feedback"])

MAX_TEXT_LENGTH = 2000


MAX_DISPLAY_NAME_LENGTH = 40


class FeedbackCreate(BaseModel):
    text: str
    # The visitor's own self-chosen display name (chatProfile.ts) - the login
    # username (e.g. the shared "pttlng" demo account) can't tell two real
    # people apart, so admin sees the name the sender actually picked. Optional
    # so an older client that doesn't send it still works.
    display_name: str | None = None


class FeedbackItem(BaseModel):
    id: int
    username: str
    role: str
    text: str
    created_at: datetime
    # Falls back to `username` for rows written before this column existed.
    display_name: str | None = None


def _display_name(row: FeedbackMessageORM) -> str | None:
    return row.display_name or None


class FeedbackStore:
    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def add(self, username: str, role: str, text: str, display_name: str | None = None) -> FeedbackItem:
        async with self._session_factory() as session:
            row = FeedbackMessageORM(
                username=username, role=role, text=text, created_at=datetime.now(timezone.utc), display_name=display_name
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return FeedbackItem(
                id=row.id, username=row.username, role=row.role, text=row.text, created_at=as_utc(row.created_at), display_name=_display_name(row)
            )

    async def list_all(self) -> list[FeedbackItem]:
        async with self._session_factory() as session:
            stmt = select(FeedbackMessageORM).order_by(FeedbackMessageORM.id.desc())
            rows = (await session.execute(stmt)).scalars().all()
        return [
            FeedbackItem(
                id=row.id, username=row.username, role=row.role, text=row.text, created_at=as_utc(row.created_at), display_name=_display_name(row)
            )
            for row in rows
        ]


@router.post("/feedback", response_model=FeedbackItem)
async def post_feedback(
    body: FeedbackCreate, request: Request, user: AuthenticatedUser = Depends(require_role("viewer"))
) -> FeedbackItem:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="feedback text must not be empty")
    display_name = (body.display_name or "").strip()[:MAX_DISPLAY_NAME_LENGTH] or None
    store: FeedbackStore = request.app.state.feedback_store
    return await store.add(user.username, user.role, text[:MAX_TEXT_LENGTH], display_name)


@router.get("/feedback", response_model=list[FeedbackItem])
async def get_feedback(request: Request, _user: AuthenticatedUser = Depends(require_role("admin"))) -> list[FeedbackItem]:
    store: FeedbackStore = request.app.state.feedback_store
    return await store.list_all()
