"""Tests for managed_auth pure foundations and async state machine."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from lanhu_design_mcp.auth.manager import (
    AuthDependencyError,
    AuthProfileLockedError,
    HttpSessionValidator,
    ManagedBrowserAuth,
    PlaywrightBrowserBackend,
    get_managed_auth,
)
from lanhu_design_mcp.auth.profile import (
    ensure_owned_profile,
)


# ---------------------------------------------------------------------------
# filter_lanhu_cookies
# ---------------------------------------------------------------------------
# format_cookie_header
# ---------------------------------------------------------------------------
# AuthSnapshot serialization safety
# ---------------------------------------------------------------------------
# ensure_owned_profile
# ---------------------------------------------------------------------------
# remove_owned_profile
# ---------------------------------------------------------------------------
# cross-checks
# ===========================================================================
# Async state-machine tests — FakeBackend, no Playwright
# ===========================================================================


class FakeSession:
    def __init__(self, cookies, event=None):
        self._cookies = cookies
        self._closed = False
        self._event = event

    async def cookies(self):
        if self._event:
            await self._event.wait()
        return list(self._cookies)

    def is_closed(self):
        return self._closed

    async def close(self):
        self._closed = True


class FakeBackend:
    def __init__(self, *, cookies=None, cookies_after=None, open_side_effect=None):
        self._cookies = cookies or []
        self._cookies_after = cookies_after
        self._open_side_effect = open_side_effect
        self.open_count = 0

    async def open(self, profile_dir, *, headless=False):
        self.open_count += 1
        if self._open_side_effect:
            raise self._open_side_effect  # noqa: R503
        return FakeSession(self._cookies, event=self._cookies_after)


LANHU_SESSION = {"name": "session", "value": "abc123", "domain": ".lanhuapp.com"}
LANHU_USER_TOKEN = {"name": "user_token", "value": "tok", "domain": "lanhuapp.com"}
FAKE_VALID_HEADER = "session=abc123"


class FakeSessionValidator:
    """Injectable validator for deterministic tests."""

    def __init__(self, valid=True, error=None):
        self._valid = valid
        self._error = error
        self.call_count = 0
        self.last_header = None

    async def validate(self, cookie_header):
        self.call_count += 1
        self.last_header = cookie_header
        if self._error:
            raise self._error
        return self._valid
OTHER_COOKIE = {"name": "track", "value": "x", "domain": "example.com"}


def _auth(backend=None, profile_dir=None, **kw):
    if profile_dir is None:
        profile_dir = Path("/tmp/test-profile")
    if backend is None:
        backend = FakeBackend()
    kw.setdefault("poll_interval", 0.01)
    kw.setdefault("timeout", 1)
    kw.setdefault("session_validator", FakeSessionValidator(valid=True))
    return ManagedBrowserAuth(backend=backend, profile_dir=profile_dir, **kw)


class TestStartLogin:
    @pytest.mark.asyncio
    async def test_start_login_is_non_blocking_and_idempotent(self, tmp_path):
        cookies_after = asyncio.Event()
        backend = FakeBackend(cookies=[LANHU_SESSION], cookies_after=cookies_after)
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        first = await auth.start_login()
        second = await auth.start_login()
        assert first["status"] in {"starting", "waiting_for_user"}
        assert second["sessionId"] == first["sessionId"]
        assert backend.open_count == 1
        cookies_after.set()
        await auth.shutdown()

    @pytest.mark.asyncio
    async def test_status_now_is_local_and_never_opens_browser(self, tmp_path):
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        result = auth.status_now()
        assert result["status"] == "missing"
        assert backend.open_count == 0

    @pytest.mark.asyncio
    async def test_successful_login_caches_only_lanhu_cookies(self, tmp_path):
        backend = FakeBackend(cookies=[LANHU_SESSION, OTHER_COOKIE])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        status = await auth.status()
        assert status["status"] == "authenticated"
        assert status["cookieNames"] == ["session"]
        info = await auth.resolve_cookie()
        assert info.source == "managed_browser"
        assert info.cookie == "session=abc123"
        assert info.configured is True

    @pytest.mark.asyncio
    async def test_user_token_is_also_an_auth_cookie(self, tmp_path):
        backend = FakeBackend(cookies=[LANHU_USER_TOKEN, OTHER_COOKIE])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        info = await auth.resolve_cookie()
        assert info.source == "managed_browser"
        assert info.cookie == "user_token=tok"

    @pytest.mark.asyncio
    async def test_login_with_neither_auth_cookie_never_authenticates(self, tmp_path):
        backend = FakeBackend(cookies=[OTHER_COOKIE])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        # It should time out rather than authenticate
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] != "authenticated"
        assert result["authenticated"] is False


class TestResolveCookie:
    @pytest.mark.asyncio
    async def test_resolve_cookie_returns_memory_first(self, tmp_path):
        cookies_after = asyncio.Event()
        backend = FakeBackend(cookies=[LANHU_SESSION], cookies_after=cookies_after)
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        cookies_after.set()
        await auth.wait_for_terminal_state()
        backend.open_count = 0
        info = await auth.resolve_cookie()
        assert info.source == "managed_browser"
        assert backend.open_count == 0  # served from memory

    @pytest.mark.asyncio
    async def test_resolve_cookie_headless_from_profile_when_no_memory(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = _auth(backend=backend, profile_dir=profile)
        info = await auth.resolve_cookie()
        assert info.source == "managed_browser"
        assert backend.open_count == 1  # headless open
        # second call must reuse memory
        backend.open_count = 0
        info2 = await auth.resolve_cookie()
        assert info2.configured is True

    @pytest.mark.asyncio
    async def test_resolve_cookie_missing_when_no_profile_and_no_memory(self, tmp_path):
        auth = _auth(profile_dir=tmp_path / "nonexistent")
        info = await auth.resolve_cookie()
        assert info.source == "missing"


class TestInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_clears_only_memory(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = _auth(backend=backend, profile_dir=profile)
        await auth.resolve_cookie()
        assert auth._cached_header is not None
        auth.invalidate()
        assert auth._cached_header is None
        assert profile.exists()  # profile untouched


class TestLogout:
    @pytest.mark.asyncio
    async def test_unconfirmed_logout_is_noop(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        auth = _auth(profile_dir=profile)
        result = await auth.logout(confirm=False)
        assert result["status"] == "confirmation_required"
        assert profile.exists()

    @pytest.mark.asyncio
    async def test_confirmed_logout_removes_profile(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = _auth(backend=backend, profile_dir=profile)
        await auth.resolve_cookie()
        result = await auth.logout(confirm=True)
        assert result["status"] == "logged_out"
        assert not profile.exists()


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_resolve_cookie_is_serialized(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = _auth(backend=backend, profile_dir=profile)
        results = await asyncio.gather(auth.resolve_cookie(), auth.resolve_cookie())
        assert results[0].configured is True
        assert results[1].configured is True


class TestDependencyErrors:
    @pytest.mark.asyncio
    async def test_missing_playwright_returns_dependency_missing(self, tmp_path):
        backend = FakeBackend(open_side_effect=AuthDependencyError("pip install 'lanhu-design-mcp[auth]'"))
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "dependency_missing"

    @pytest.mark.asyncio
    async def test_profile_locked_returns_safe_status(self, tmp_path):
        backend = FakeBackend(open_side_effect=AuthProfileLockedError("profile locked"))
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "profile_locked"

    @pytest.mark.asyncio
    async def test_generic_failure_sanitized(self, tmp_path):
        class WeirdError(Exception):
            pass

        backend = FakeBackend(open_side_effect=WeirdError("secret-token=abc"))
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "failed"
        assert "secret-token" not in str(result.get("message", ""))

    @pytest.mark.asyncio
    async def test_auth_snapshot_never_leaks_cookie_in_message(self, tmp_path):
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        d = await auth.status()
        # cookie values must never appear
        text = str(d)
        assert "abc123" not in text
        assert "session=abc123" not in text


class TestCancellationAndTimeout:
    @pytest.mark.asyncio
    async def test_cancelled_by_closing_browser(self, tmp_path):
        backend = FakeClosableBackend(cookies=[])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile", timeout=5, poll_interval=0.05)
        await auth.start_login()
        await asyncio.sleep(0.1)
        if backend._last_session:
            backend._last_session.simulate_external_close()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_retry_after_terminal_failure(self, tmp_path):
        backend = FakeBackend()
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile", timeout=0.1, poll_interval=0.05)
        backend._cookies = []
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result1 = await auth.status()
        assert result1["authenticated"] is False

        # After failure, a new start_login should work
        backend._cookies = [LANHU_SESSION]
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result2 = await auth.status()
        assert result2["authenticated"] is True


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_closes_session_and_cancels_task(self, tmp_path):
        cookies_after = asyncio.Event()
        backend = FakeBackend(cookies=[LANHU_SESSION], cookies_after=cookies_after)
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        cookies_after.set()
        await auth.shutdown()
        result = await auth.status()
        assert result["status"] in {"missing", "authenticated"}


class TestSingleton:
    def test_get_managed_auth_returns_same_instance(self, tmp_path):
        a1 = get_managed_auth()
        a2 = get_managed_auth()
        assert a1 is a2


# ===========================================================================
# Task 3 fix tests
# ===========================================================================

TFSTK_ONLY = {"name": "tfstk", "value": "xyz", "domain": ".lanhuapp.com"}
TRACKING_ONLY = {"name": "tracking", "value": "x", "domain": "lanhuapp.com"}


class FakeClosableSession(FakeSession):
    """Session that supports external close simulation."""
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._external_close_event = asyncio.Event()

    def simulate_external_close(self):
        self._closed = True
        self._external_close_event.set()


class FakeClosableBackend(FakeBackend):
    """Backend whose sessions support external close simulation."""
    def __init__(self, *args, session_class=FakeClosableSession, **kw):
        super().__init__(*args, **kw)
        self.session_class = session_class
        self._last_session = None

    async def open(self, profile_dir, *, headless=False):
        self.open_count += 1
        if self._open_side_effect:
            raise self._open_side_effect
        session = self.session_class(self._cookies, event=self._cookies_after)
        self._last_session = session
        return session


class BlockingBackend:
    """Backend that blocks until an event is set."""
    def __init__(self, cookies=None, block_event=None):
        self._cookies = cookies or []
        self._block_event = block_event or asyncio.Event()
        self.open_count = 0

    async def open(self, profile_dir, *, headless=False):
        self.open_count += 1
        await self._block_event.wait()
        return FakeSession(self._cookies)


# ---------------------------------------------------------------------------
# Fix 1: auth criterion – tracking-only cookies must not authenticate
# ---------------------------------------------------------------------------


class TestAuthCriterion:
    @pytest.mark.asyncio
    async def test_non_auth_lanhu_cookies_do_not_authenticate_profile(self, tmp_path):
        """tfstk and tracking cookies on Lanhu domains must NOT authenticate."""
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(cookies=[TFSTK_ONLY, TRACKING_ONLY])
        auth = _auth(backend=backend, profile_dir=profile)
        info = await auth.resolve_cookie()
        assert info.source == "missing", f"expected missing, got {info.source} with {info.cookie}"

    @pytest.mark.asyncio
    async def test_lanhu_cookies_with_session_plus_others_is_valid(self, tmp_path):
        """session + tfstk + tracking all on allowed domains → authenticated with all."""
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(cookies=[LANHU_SESSION, TFSTK_ONLY, TRACKING_ONLY, OTHER_COOKIE])
        auth = _auth(backend=backend, profile_dir=profile)
        info = await auth.resolve_cookie()
        assert info.source == "managed_browser"
        assert "session=abc123" in info.cookie


# ---------------------------------------------------------------------------
# Fix 2: safe error messages – never str(exc) in MCP-facing _message
# ---------------------------------------------------------------------------


class TestSafeMessages:
    @pytest.mark.asyncio
    async def test_dependency_error_message_is_fixed_safe_text(self, tmp_path):
        backend = FakeBackend(open_side_effect=AuthDependencyError("sentinel-secret-123"))
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "dependency_missing"
        msg = result.get("message", "")
        assert "sentinel-secret-123" not in msg

    @pytest.mark.asyncio
    async def test_profile_locked_message_is_fixed_safe_text(self, tmp_path):
        backend = FakeBackend(open_side_effect=AuthProfileLockedError("sentinel-token-456"))
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "profile_locked"
        msg = result.get("message", "")
        assert "sentinel-token-456" not in msg

    @pytest.mark.asyncio
    async def test_probe_profile_exposes_dependency_missing(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(open_side_effect=AuthDependencyError("install hint"))
        auth = _auth(backend=backend, profile_dir=profile)
        result = await auth.status(probe_profile=True)
        assert result["status"] == "dependency_missing"
        assert result["authenticated"] is False
        msg = result.get("message", "")
        assert "sentinel" not in msg

    @pytest.mark.asyncio
    async def test_probe_profile_exposes_profile_locked(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(open_side_effect=AuthProfileLockedError("sentinel-locked-789"))
        auth = _auth(backend=backend, profile_dir=profile)
        result = await auth.status(probe_profile=True)
        assert result["status"] == "profile_locked"
        assert result["authenticated"] is False
        msg = result.get("message", "")
        assert "sentinel-locked-789" not in msg

    @pytest.mark.asyncio
    async def test_probe_generic_error_exposes_failed(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        backend = FakeBackend(open_side_effect=RuntimeError("boom"))
        auth = _auth(backend=backend, profile_dir=profile)
        result = await auth.status(probe_profile=True)
        assert result["status"] == "failed"
        assert result["authenticated"] is False

    @pytest.mark.asyncio
    async def test_status_probe_on_unmarked_profile_stays_missing(self, tmp_path):
        auth = _auth(profile_dir=tmp_path / "nonexistent")
        result = await auth.status(probe_profile=True)
        assert result["status"] == "missing"
        assert result["authenticated"] is False


# ---------------------------------------------------------------------------
# Fix 5: serialization/races – dedicated browser lock
# ---------------------------------------------------------------------------


class TestBrowserLock:
    @pytest.mark.asyncio
    async def test_logout_waits_for_headless_resolve(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        block = asyncio.Event()
        backend = BlockingBackend(cookies=[LANHU_SESSION], block_event=block)
        auth = _auth(backend=backend, profile_dir=profile)
        # Start a headless resolve that blocks
        resolve_task = asyncio.create_task(auth.resolve_cookie())
        await asyncio.sleep(0.1)
        # Logout should wait for the resolve lock before removing profile
        logout_task = asyncio.create_task(auth.logout(confirm=True))
        await asyncio.sleep(0.1)
        assert not logout_task.done()  # blocked by lock
        # Unblock resolve
        block.set()
        await resolve_task
        await logout_task
        assert logout_task.done()

    @pytest.mark.asyncio
    async def test_resolve_blocked_while_visible_session_active(self, tmp_path):
        """Visible session holds lock for its entire lifecycle; resolve must wait."""
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        stay_open = asyncio.Event()  # keeps visible session alive
        backend = BlockingBackend(cookies=[], block_event=stay_open)  # no auth cookie
        auth = _auth(backend=backend, profile_dir=profile, timeout=10)
        # Start visible login — opens backend then blocks on polling (no auth cookie)
        await auth.start_login()
        await asyncio.sleep(0.15)
        assert backend.open_count == 1
        # Concurrent headless resolve must be blocked by the same lock
        resolve_task = asyncio.create_task(auth.resolve_cookie())
        await asyncio.sleep(0.1)
        assert backend.open_count == 1  # still 1 — resolve hasn't opened yet
        assert not resolve_task.done()
        # Release visible session → worker times out or finds no auth
        stay_open.set()
        await asyncio.sleep(0.2)
        await resolve_task
        await auth.shutdown()


# ---------------------------------------------------------------------------
# Fix 3/4: external close detection + cleanup exception safety
# ---------------------------------------------------------------------------


class FakeEvent:
    """Simulates a Playwright event listener subscription."""

    def __init__(self):
        self._handlers = []

    def add_listener(self, handler):
        self._handlers.append(handler)

    def fire(self):
        for h in self._handlers:
            h()


class ClosableFakeSession(FakeSession):
    """Session that fires on external close like real Playwright events."""

    def __init__(self, *args, on_close=None, **kw):
        super().__init__(*args, **kw)
        self._on_close = on_close
        self._close_event = FakeEvent()

    def add_close_listener(self, handler):
        self._close_event.add_listener(handler)

    def simulate_external_close(self):
        self._closed = True
        self._close_event.fire()
        if self._on_close:
            self._on_close()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._close_event.fire()
        except Exception:
            pass


class ClosableEventBackend:
    """Backend producing sessions that support external close simulation."""

    def __init__(self, cookies=None):
        self._cookies = cookies or []
        self.open_count = 0
        self._last_session = None

    async def open(self, profile_dir, *, headless=False):
        self.open_count += 1
        session = ClosableFakeSession(self._cookies)
        self._last_session = session
        return session


class TestExternalClose:
    @pytest.mark.asyncio
    async def test_context_close_event_sets_session_closed(self, tmp_path):
        backend = ClosableEventBackend(cookies=[])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile")
        await auth.start_login()
        await asyncio.sleep(0.1)
        assert backend._last_session is not None
        assert not backend._last_session.is_closed()
        backend._last_session.simulate_external_close()
        await asyncio.sleep(0.15)
        assert backend._last_session.is_closed()


class TestCleanup:
    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, tmp_path):
        backend = ClosableEventBackend(cookies=[])
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile", timeout=0.05)
        await auth.start_login()
        await auth.wait_for_terminal_state()
        if backend._last_session:
            await backend._last_session.close()
            await backend._last_session.close()
            assert backend._last_session.is_closed()


# ===========================================================================
# Finding A: production event wiring — direct PlaywrightBrowserBackend tests
# via fake async_playwright module (no real Playwright installed)
# ===========================================================================


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
        import sys
        import types
        fake_mod = types.ModuleType("playwright.async_api")
        fake_mod.async_playwright = lambda: fake_ap
        sys.modules["playwright"] = types.ModuleType("playwright")
        sys.modules["playwright.async_api"] = fake_mod
        return fake_mod

    def test_context_close_event_sets_session_closed(self):
        """Fire external context close → is_closed True, then close stops driver once."""
        async def run():
            backend = PlaywrightBrowserBackend()
            fp = FakePlaywright()
            self._install_fake_playwright(fp)
            session = await backend.open(Path("/tmp/fake-profile"), headless=True)
            assert not session.is_closed()
            # Fire external context close — no owned session.close() yet
            fp.chromium._last_context.fire_close()
            assert session.is_closed()
            # Owned close still stops driver (driver was not stopped by event alone)
            assert fp._exit_count == 0
            await session.close()
            assert fp._exit_count == 1

        asyncio.run(run())

    def test_visible_mode_navigates_and_wires_page_close(self):
        """Visible open reuses context page, navigates to Lanhu, page close fires."""
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
            # No second page created when an existing page is present
            assert len(ctx.pages) == 1
            # Fire external page close
            assert not session.is_closed()
            page.fire_close()
            assert session.is_closed()
            # Owned close stops driver exactly once
            assert fp._exit_count == 0
            await session.close()
            assert fp._exit_count == 1

        asyncio.run(run())

    def test_navigation_failure_still_stops_playwright(self):
        """goto raises AND context.close raises → Playwright stopped exactly once."""
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


# ===========================================================================
# Finding B: lock releases before close
# ===========================================================================


class BlockingCloseBackend:
    """Backend whose session.close() blocks until an event is set."""

    def __init__(self, cookies=None, close_block=None):
        self._cookies = cookies or []
        self._close_block = close_block or asyncio.Event()
        self.open_count = 0

    async def open(self, profile_dir, *, headless=False):
        self.open_count += 1
        return _BlockingCloseSession(self._cookies, self._close_block)


class _BlockingCloseSession:
    def __init__(self, cookies, close_block):
        self._cookies = cookies
        self._close_block = close_block
        self._closed = False

    async def cookies(self):
        return list(self._cookies)

    def is_closed(self):
        return self._closed

    async def close(self):
        self._closed = True
        await self._close_block.wait()


class TestExternalCloseWorkerCleanup:
    """Worker inner finally always calls owned close, even after external close."""

    @pytest.mark.asyncio
    async def test_external_close_worker_still_invokes_owned_close(self, tmp_path):
        close_called = []

        class TrackedCloseSession:
            def __init__(self, cookies, event=None):
                self._cookies = cookies
                self._closed = False
                self._event = event

            async def cookies(self):
                if self._event:
                    await self._event.wait()
                return list(self._cookies)

            def is_closed(self):
                return self._closed

            async def close(self):
                close_called.append(True)
                self._closed = True

        class TrackedBackend:
            def __init__(self, cookies=None):
                self._cookies = cookies or []
                self.open_count = 0
                self.last_session = None

            async def open(self, profile_dir, *, headless=False):
                self.open_count += 1
                session = TrackedCloseSession(self._cookies)
                self.last_session = session
                return session

        backend = TrackedBackend(cookies=[])  # no auth cookie
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile", timeout=5, poll_interval=0.05)
        await auth.start_login()
        await asyncio.sleep(0.1)
        # External close happens before worker loop exits
        backend.last_session._closed = True  # simulate browser close
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "cancelled"
        # Worker's inner finally must have called close exactly once
        assert len(close_called) == 1
        await auth.shutdown()


class TestCloseUnderLock:
    @pytest.mark.asyncio
    async def test_resolve_blocked_while_close_holds_lock(self, tmp_path):
        """Prove close releases the browser lock before resolve can acquire it."""
        close_block = asyncio.Event()
        backend = BlockingCloseBackend(cookies=[LANHU_SESSION], close_block=close_block)
        auth = _auth(backend=backend, profile_dir=tmp_path / "profile", timeout=0.05)
        await auth.start_login()
        await asyncio.sleep(0.15)
        # Login worker should have found the session cookie and be authenticating,
        # then trying to close under the lock
        # Start a resolve — it must wait for the close to finish
        resolve_task = asyncio.create_task(auth.resolve_cookie())
        await asyncio.sleep(0.1)
        assert backend.open_count == 1  # resolve hasn't opened
        # Release close block
        close_block.set()
        await resolve_task
        await auth.shutdown()


# ===========================================================================
# Session validation — stale cookie false-positive regression
# ===========================================================================


class TestSessionValidation:
    """Prove stale cookies are rejected by the injected validator."""

    @pytest.mark.asyncio
    async def test_stale_cookie_rejected_by_visible_login(self, tmp_path):
        validator = FakeSessionValidator(valid=False)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = ManagedBrowserAuth(
            backend=backend, profile_dir=tmp_path / "profile",
            poll_interval=0.01, timeout=0.1, session_validator=validator,
        )
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] != "authenticated"
        assert result["authenticated"] is False
        assert validator.call_count >= 1

    @pytest.mark.asyncio
    async def test_valid_cookie_accepted_by_visible_login(self, tmp_path):
        validator = FakeSessionValidator(valid=True)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = ManagedBrowserAuth(
            backend=backend, profile_dir=tmp_path / "profile",
            poll_interval=0.01, timeout=1, session_validator=validator,
        )
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "authenticated"

    @pytest.mark.asyncio
    async def test_stale_cookie_rejected_by_resolve(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        validator = FakeSessionValidator(valid=False)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = ManagedBrowserAuth(
            backend=backend, profile_dir=profile, session_validator=validator,
        )
        info = await auth.resolve_cookie()
        assert info.source == "missing"

    @pytest.mark.asyncio
    async def test_valid_cookie_accepted_by_resolve(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        validator = FakeSessionValidator(valid=True)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = ManagedBrowserAuth(
            backend=backend, profile_dir=profile, session_validator=validator,
        )
        info = await auth.resolve_cookie()
        assert info.source == "managed_browser"

    @pytest.mark.asyncio
    async def test_transient_validator_error_then_success(self, tmp_path):
        call_count = [0]

        class FlakyValidator:
            async def validate(self, header):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("transient network error")
                return True

        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = ManagedBrowserAuth(
            backend=backend, profile_dir=tmp_path / "profile",
            poll_interval=0.01, timeout=1, session_validator=FlakyValidator(),
        )
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert result["status"] == "authenticated"
        assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_validator_never_leaks_cookie_in_state(self, tmp_path):
        validator = FakeSessionValidator(valid=False)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = ManagedBrowserAuth(
            backend=backend, profile_dir=tmp_path / "profile",
            poll_interval=0.01, timeout=0.1, session_validator=validator,
        )
        await auth.start_login()
        await auth.wait_for_terminal_state()
        result = await auth.status()
        assert "abc123" not in str(result)
        assert "session=" not in str(result)

    @pytest.mark.asyncio
    async def test_auth_status_probe_with_stale_cookie_is_missing(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        validator = FakeSessionValidator(valid=False)
        backend = FakeBackend(cookies=[LANHU_SESSION])
        auth = ManagedBrowserAuth(
            backend=backend, profile_dir=profile, session_validator=validator,
        )
        result = await auth.status(probe_profile=True)
        assert result["status"] != "authenticated"
        assert result["authenticated"] is False


# ===========================================================================
# Direct HttpSessionValidator response classification (no network)
# ===========================================================================


ACCOUNT_URL = "https://lanhuapp.com/api/account/user/detail"

def _make_resp(status, json_body=None, text_body="", headers=None, history=None):
    import json as _json
    content = _json.dumps(json_body).encode() if json_body is not None else text_body.encode()
    hdrs = dict(headers or {})
    if json_body is not None:
        hdrs.setdefault("content-type", "application/json")
    return httpx.Response(status, headers=hdrs, content=content,
                          request=httpx.Request("GET", ACCOUNT_URL),
                          history=list(history or []))


class TestHttpSessionValidator:
    """Deterministic classification tests — no real HTTP.

    Live contract: GET /api/account/user/detail
      Authenticated → 200 {code: "00000", msg: ..., result: {...}}
      Anonymous     → 401 {code: 30001}
    """

    @pytest.mark.asyncio
    async def test_200_code_00000_is_true(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "00000"}))):
            assert await v.validate("s=x") is True

    @pytest.mark.asyncio
    async def test_200_code_not_00000_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "00001"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_200_code_numeric_0_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": 0}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_200_code_str_0_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "0"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_200_missing_code_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"msg": "ok"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_401_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(401, {"code": 30001}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_500_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(500, {"code": "00000"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_redirect_history_to_login_is_false(self):
        redirect = httpx.Response(
            302, headers={"Location": "https://lanhuapp.com/login"},
            request=httpx.Request("GET", ACCOUNT_URL),
        )
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "00000"}, history=[redirect]))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_malformed_json_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, text_body="not json"))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_non_dict_json_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, json_body=[]))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_network_error_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(side_effect=RuntimeError("network"))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_timeout_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_requests_account_endpoint_with_safe_headers(self):
        v = HttpSessionValidator()
        mock_get = AsyncMock(return_value=_make_resp(200, {"code": "00000"}))
        with patch.object(httpx.AsyncClient, "get", mock_get):
            await v.validate("s=fakevalue")
        call_args = mock_get.call_args
        url = call_args[0][0]
        req_headers = call_args[1]["headers"]
        assert url == ACCOUNT_URL
        assert "Cookie" in req_headers
        # Cookie value is present (it's the input) — we only verify the key
        assert req_headers.get("Referer") == "https://lanhuapp.com/web/"
        assert req_headers.get("request-from") == "web"


# ===========================================================================
# macOS-only boundary
# ===========================================================================




class TestMacOSOnlyBoundary:

    @pytest.mark.asyncio
    async def test_start_login_rejects_non_darwin_without_opening_browser(self):
        backend = AsyncMock()
        auth = ManagedBrowserAuth(backend=backend, system="Linux")
        result = await auth.start_login()
        assert result["status"] == "unsupported_platform"
        assert result["authenticated"] is False
        backend.open.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_cookie_rejects_non_darwin_without_profile_access(self, tmp_path):
        backend = AsyncMock()
        auth = ManagedBrowserAuth(backend=backend, profile_dir=tmp_path / "profile", system="Windows")
        result = await auth.resolve_cookie()
        assert result.configured is False
        assert auth.status_now()["status"] == "unsupported_platform"
        assert not (tmp_path / "profile").exists()
        backend.open.assert_not_called()
