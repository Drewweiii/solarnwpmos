from __future__ import annotations

import asyncio
import logging
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RobotsDecision:
    allowed: bool
    reason: str


class RobotsChecker:
    """Fetches and caches robots.txt, fails closed if it can't be read.

    Scraping without checking robots.txt first is exactly the kind of thing this
    module must not do - if the site is unreachable (as it currently is - see
    module README), the safe default is to *refuse* to fetch rather than assume
    permission, unless an operator has explicitly opted in via config.
    """

    def __init__(self, base_url: str, user_agent: str, timeout: float, cache_ttl: float, fail_open: bool = False):
        self._base_url = base_url
        self._user_agent = user_agent
        self._timeout = timeout
        self._cache_ttl = cache_ttl
        self._fail_open = fail_open
        self._parser: urllib.robotparser.RobotFileParser | None = None
        self._fetched_at: float = 0.0

    async def _refresh(self, client: httpx.AsyncClient) -> None:
        robots_url = urljoin(self._base_url, "/robots.txt")
        parser = urllib.robotparser.RobotFileParser()
        try:
            resp = await client.get(robots_url, timeout=self._timeout, headers={"User-Agent": self._user_agent})
            resp.raise_for_status()
            parser.parse(resp.text.splitlines())
            self._parser = parser
            self._fetched_at = time.monotonic()
            logger.info("robots.txt refreshed from %s", robots_url)
        except httpx.HTTPError as exc:
            logger.warning("could not fetch robots.txt from %s: %s", robots_url, exc)
            self._parser = None

    async def is_allowed(self, path: str, client: httpx.AsyncClient) -> RobotsDecision:
        stale = (time.monotonic() - self._fetched_at) > self._cache_ttl
        if self._parser is None or stale:
            await self._refresh(client)

        if self._parser is None:
            if self._fail_open:
                return RobotsDecision(True, "robots.txt unreachable; fail_open=True override in effect")
            return RobotsDecision(False, "robots.txt unreachable; failing closed (set allow_fetch_if_robots_unreachable to override)")

        allowed = self._parser.can_fetch(self._user_agent, path)
        return RobotsDecision(allowed, "robots.txt permits" if allowed else "disallowed by robots.txt")


class RateLimiter:
    """Enforces a minimum wall-clock interval between outbound requests, independent of the scheduler."""

    def __init__(self, min_interval_seconds: float):
        self._min_interval = min_interval_seconds
        self._last_call: float | None = None
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._last_call is not None:
                elapsed = now - self._last_call
                remaining = self._min_interval - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_call = time.monotonic()
