"""Capture the report's UI screenshots from the running dashboard.

These are real captures of the real application, not mock-ups. The report's
chapter on the interface would be worthless otherwise - and this project's
standing rule against presenting invented data as real applies to pictures of
the product just as much as to its numbers.

Prerequisites (both on localhost):
    API   nongfab_api on :8000, seeded demo users, SQLite is fine
    web   vite dev server on :5173 with VITE_API_URL=http://localhost:8000

Run:  python3 docs/report/screenshots.py
Out:  docs/report/screenshots/*.png
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

WEB = "http://localhost:5173"
# The sandbox's Playwright python package and its installed browser build are
# different versions, so the bundled resolver looks for a revision that is not
# there. Pointing at the browser that IS installed is the documented escape
# hatch and avoids re-downloading Chromium.
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# The seeded viewer account. Deliberately the viewer rather than admin: the
# report shows the site as a visitor meets it, and role-gated panels should be
# absent from those figures rather than silently included.
USER, PASSWORD = "pttlng", "12345"

VIEWPORT = {"width": 1440, "height": 900}


async def dismiss_overlays(page) -> None:
    """Close the welcome splash and the chat-profile modal if they appear.

    Both are first-visit-only and neither is part of what these figures are
    meant to show, but they cover the page completely, so a capture taken
    without closing them is a screenshot of a modal.
    """
    for selector in (".login-welcome-close", ".chat-profile-setup-cancel"):
        try:
            el = page.locator(selector).first
            if await el.count() and await el.is_visible():
                await el.click()
                await page.wait_for_timeout(400)
        except Exception:
            pass

    # The chat-profile modal has no skip button unless a cancel handler was
    # passed, and its submit stays disabled until a display name is typed - so
    # the only reliable way past it is to complete it, exactly as a visitor
    # does. Guessed selectors (.chat-profile-skip/.chat-profile-close) silently
    # matched nothing on the first run and every screenshot came out as a
    # picture of this modal.
    try:
        form = page.locator(".chat-profile-setup").first
        if await form.count() and await form.is_visible():
            await page.fill("#chat-profile-setup-name", "ผู้เยี่ยมชม")
            await page.click(".chat-profile-setup-submit")
            await page.wait_for_timeout(700)
    except Exception:
        pass


async def login(page) -> None:
    # NOT networkidle: the dashboard holds /ws/live and /ws/chat open for its
    # whole session, so the network never goes idle and every goto times out
    # after 30s. domcontentloaded plus an explicit settle is the right wait for
    # an app with persistent sockets.
    await page.goto(WEB, wait_until="domcontentloaded")
    await page.wait_for_timeout(2500)
    await dismiss_overlays(page)
    try:
        await page.fill('input[name="username"], input#username', USER)
        await page.fill('input[name="password"], input#password', PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2500)
    except Exception:
        # Already signed in from a previous run's storage state.
        pass
    await dismiss_overlays(page)


async def shot(page, path: str, name: str, wait_ms: int = 3500, full: bool = False) -> None:
    await page.goto(f"{WEB}{path}", wait_until="domcontentloaded")
    await dismiss_overlays(page)
    # Charts animate in and data arrives asynchronously; capturing too early
    # produces a figure full of empty panels that misrepresents the product.
    await page.wait_for_timeout(wait_ms)
    await page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print(f"  wrote screenshots/{name}.png")


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME)
        page = await browser.new_page(viewport=VIEWPORT, device_scale_factor=2)

        await login(page)
        await shot(page, "/", "s1-dashboard")
        await shot(page, "/forecast", "s2-forecast", wait_ms=5000)
        await shot(page, "/forecast", "s3-forecast-full", wait_ms=5000, full=True)
        await shot(page, "/energy-report", "s4-energy-report", full=True)
        await shot(page, "/3d", "s5-3d-view", wait_ms=7000)
        await shot(page, "/settings", "s6-settings", full=True)

        # Mobile, because the site is meant to be usable on a phone and a report
        # that only shows the desktop layout is showing half the product.
        mobile = await browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True
        )
        await login(mobile)
        await shot(mobile, "/forecast", "s7-mobile-forecast", wait_ms=5000)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
