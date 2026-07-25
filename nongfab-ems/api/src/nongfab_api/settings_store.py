"""Reads and writes the admin-published setting overrides, with an in-process
cache so calculation code can ask for an effective value without awaiting a
database round-trip (2026-07-25).

The split that makes this work: the DATABASE holds only what somebody
deliberately changed, and `settings_registry` holds what every default IS. So
"effective value" is just "the override if one exists, else the registry
default", and resetting is a delete rather than a write-back of a default that
could drift out of sync with the code.

Why a cache: these values are read inside physics and financial calculations
(`loss_model.default_loss_factors` is called per zone per simulated day), which
are synchronous and have no business knowing about SQLAlchemy sessions. The cache
is refreshed on startup and after every write, so it is only ever stale if
another process writes - and this deployment runs a single API container (see the
root README's own note on that), which is why a simple process cache is honest
here rather than a bug waiting to happen. If that ever changes, this is the one
place to add a TTL or a notify/listen.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .models import SystemSettingORM
from .settings_registry import BY_KEY, SPECS, validate

logger = logging.getLogger(__name__)

# key -> published override. Absent means "still at the registry default".
_overrides: dict[str, float] = {}
# key -> (updated_at, updated_by), for the audit line the UI shows.
_meta: dict[str, tuple[datetime, str]] = {}


def effective(key: str) -> float:
    """The value calculations should use: the override if one is published, else
    the registry default. Raises KeyError for an unknown key so a typo in
    calculation code fails loudly instead of silently reading 0."""
    if key in _overrides:
        return _overrides[key]
    return BY_KEY[key].default


def overrides() -> dict[str, float]:
    """Copy of every published override (never the live dict, so a caller can't
    mutate the cache by accident)."""
    return dict(_overrides)


def override_meta() -> dict[str, tuple[datetime, str]]:
    return dict(_meta)


def is_overridden(key: str) -> bool:
    return key in _overrides


def effective_all() -> dict[str, float]:
    """Every registry key's effective value - what the frontend renders as the
    current state of the form."""
    return {spec.key: effective(spec.key) for spec in SPECS}


def _remember(key: str, value: float, updated_at: datetime, updated_by: str) -> None:
    _overrides[key] = value
    _meta[key] = (updated_at, updated_by)


def _forget(key: str) -> None:
    _overrides.pop(key, None)
    _meta.pop(key, None)


def reset_cache() -> None:
    """Drop every cached override (tests, and the reset-all path)."""
    _overrides.clear()
    _meta.clear()


class SettingsStore:
    """Async persistence for the overrides. Construct once per app with the
    app's engine, same shape as UserStore/FeedbackStore."""

    def __init__(self, engine: AsyncEngine):
        self._session = async_sessionmaker(engine, expire_on_commit=False)

    async def load_into_cache(self) -> dict[str, float]:
        """Read every stored override into the process cache. Rows whose key is
        no longer in the registry are IGNORED rather than deleted: a key can
        vanish because a deploy rolled back, and silently destroying somebody's
        saved figure in that window would be the worse failure."""
        async with self._session() as session:
            rows = (await session.execute(select(SystemSettingORM))).scalars().all()
        reset_cache()
        unknown = []
        for row in rows:
            if row.key not in BY_KEY:
                unknown.append(row.key)
                continue
            _remember(row.key, float(row.value), row.updated_at, row.updated_by)
        if unknown:
            logger.info("settings: ignoring %d stored key(s) not in this build's registry: %s", len(unknown), sorted(unknown))
        if _overrides:
            logger.info("settings: loaded %d published override(s)", len(_overrides))
        return overrides()

    async def put(self, key: str, value: float, updated_by: str) -> float:
        """Validate and publish one override. Returns the stored value. Raises
        KeyError (unknown key) or ValueError (out of bounds) for the route to
        translate."""
        checked = validate(key, value)
        now = datetime.now(timezone.utc)
        async with self._session() as session:
            existing = await session.get(SystemSettingORM, key)
            if existing is None:
                session.add(SystemSettingORM(key=key, value=checked, updated_at=now, updated_by=updated_by))
            else:
                existing.value = checked
                existing.updated_at = now
                existing.updated_by = updated_by
            await session.commit()
        _remember(key, checked, now, updated_by)
        logger.info("settings: %s set to %s by %s", key, checked, updated_by)
        return checked

    async def put_many(self, values: dict[str, float], updated_by: str) -> dict[str, float]:
        """Publish several overrides. Validates EVERY key before writing any, so
        a form submission with one bad field changes nothing rather than applying
        half of itself."""
        for key, value in values.items():
            if key not in BY_KEY:
                raise KeyError(key)
            validate(key, value)
        written = {}
        for key, value in values.items():
            written[key] = await self.put(key, value, updated_by)
        return written

    async def clear(self, key: str) -> bool:
        """Reset one setting to its registry default. Returns whether an
        override actually existed."""
        if key not in BY_KEY:
            raise KeyError(key)
        async with self._session() as session:
            result = await session.execute(delete(SystemSettingORM).where(SystemSettingORM.key == key))
            await session.commit()
        _forget(key)
        removed = bool(result.rowcount)
        if removed:
            logger.info("settings: %s reset to default", key)
        return removed

    async def clear_all(self) -> int:
        """Reset everything. Returns how many overrides were removed."""
        async with self._session() as session:
            result = await session.execute(delete(SystemSettingORM))
            await session.commit()
        reset_cache()
        removed = int(result.rowcount or 0)
        logger.info("settings: reset all (%d override(s) removed)", removed)
        return removed
