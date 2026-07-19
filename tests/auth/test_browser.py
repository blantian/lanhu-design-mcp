"""auth.browser 的 Playwright 适配器与会话生命周期测试。"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from lanhu_design_mcp.auth.browser import PlaywrightBrowserBackend

LANHU_SESSION = {"name": "session", "value": "abc123", "domain": ".lanhuapp.com"}
OTHER_COOKIE = {"name": "track", "value": "x", "domain": "example.com"}


class FakeContext:
    def __init__(self):
        self.pages = []
        self._close_handlers = []
        self.closed = False
        self._close_raised = False

    def on(self, event, handler):
        if event == "close":
            self._close_handlers.append(handler)

    def fire_close(self):
        self.closed = True
        for h in self._close_handlers:
            h()

    async def cookies(self):
        return [LANHU_SESSION, OTHER_COOKIE]

    async def new_page(self):
        page = FakePage(self)
        self.pages.append(page)
        return page

    async def close(self):
        self.fire_close()
        if self._close_raised:
            raise RuntimeError("close failed")


class FakePage:
    def __init__(self, context):
        self._close_handlers = []
        self.closed = False
        self._context = context
        self._goto_url = None

    def on(self, event, handler):
        if event == "close":
            self._close_handlers.append(handler)

    async def goto(self, url, **kw):
        self._goto_url = url

    def fire_close(self):
        self.closed = True
        for h in self._close_handlers:
            h()


class FakeBrowserType:
    def __init__(self):
        self._last_context = None

    async def launch_persistent_context(self, **kw):
        ctx = FakeContext()
        self._last_context = ctx
        return ctx


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeBrowserType()
        self._exit_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self._exit_count += 1


class TestPlaywrightBackendAdapter:
    @staticmethod
    def _install_fake_playwright(fake_ap):
        fake_mod = types.ModuleType("playwright.async_api")
        fake_mod.async_playwright = lambda: fake_ap
        sys.modules["playwright"] = types.ModuleType("playwright")
        sys.modules["playwright.async_api"] = fake_mod
        return fake_mod

    def test_context_close_event_sets_session_closed(self):
        async def run():
            backend = PlaywrightBrowserBackend()
            fp = FakePlaywright()
            self._install_fake_playwright(fp)
            session = await backend.open(Path("/tmp/fake-profile"), headless=True)
            assert not session.is_closed()
            fp.chromium._last_context.fire_close()
            assert session.is_closed()
            assert fp._exit_count == 0
            await session.close()
            assert fp._exit_count == 1
        asyncio.run(run())

    def test_visible_mode_navigates_and_wires_page_close(self):
        async def run():
            backend = PlaywrightBrowserBackend()
            fp = FakePlaywright()
            self._install_fake_playwright(fp)
            session = await backend.open(Path("/tmp/fake-profile"), headless=False)
            ctx = fp.chromium._last_context
            assert ctx is not None
            assert len(ctx.pages) == 1
            page = ctx.pages[0]
            assert page._goto_url == "https://lanhuapp.com/"
            assert len(ctx.pages) == 1
            assert not session.is_closed()
            page.fire_close()
            assert session.is_closed()
            assert fp._exit_count == 0
            await session.close()
            assert fp._exit_count == 1
        asyncio.run(run())

    def test_navigation_failure_still_stops_playwright(self):
        async def run():
            backend = PlaywrightBrowserBackend()
            fp = FakePlaywright()
            self._install_fake_playwright(fp)

            class FailingPage(FakePage):
                async def goto(self, url, **kw):
                    raise RuntimeError("connection refused")

            async def launch_with_failing_goto(self, **kw):
                ctx = FakeContext()
                self._last_context = ctx
                if not kw.get("headless"):
                    page = FailingPage(ctx)
                    ctx.pages = [page]
                    ctx._close_raised = True
                return ctx

            with patch.object(FakeBrowserType, "launch_persistent_context", launch_with_failing_goto):
                with pytest.raises(Exception):
                    await backend.open(Path("/tmp/fake-profile"), headless=False)
                assert fp._exit_count == 1
        asyncio.run(run())
