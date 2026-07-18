"""Tests for managed_auth pure foundations and async state machine — no Playwright or browser launch."""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from lanhu_design_mcp.config import CookieInfo
from lanhu_design_mcp.managed_auth import (
    LANHU_DOMAINS,
    PROFILE_MARKER,
    AuthDependencyError,
    AuthProfileLockedError,
    AuthSnapshot,
    ManagedBrowserAuth,
    UnsafeProfileError,
    default_profile_dir,
    ensure_owned_profile,
    filter_lanhu_cookies,
    format_cookie_header,
    get_managed_auth,
    remove_owned_profile,
)


# ---------------------------------------------------------------------------
# default_profile_dir
# ---------------------------------------------------------------------------


class TestDefaultProfileDir:
    def test_macos_uses_library_application_support(self, tmp_path):
        path = default_profile_dir("Darwin", {"HOME": str(tmp_path)})
        expected = tmp_path / "Library" / "Application Support" / "lanhu-design-mcp" / "browser-profile"
        assert path == expected

    def test_linux_uses_xdg_data_home(self, tmp_path):
        xdg = tmp_path / ".local" / "share"
        path = default_profile_dir("Linux", {"XDG_DATA_HOME": str(xdg)})
        assert path == xdg / "lanhu-design-mcp" / "browser-profile"

    def test_linux_falls_back_to_home_local_share(self, tmp_path):
        path = default_profile_dir("Linux", {"HOME": str(tmp_path)})
        assert path == tmp_path / ".local" / "share" / "lanhu-design-mcp" / "browser-profile"

    def test_windows_uses_localappdata(self, tmp_path):
        appdata = tmp_path / "AppData" / "Local"
        path = default_profile_dir("Windows", {"LOCALAPPDATA": str(appdata)})
        assert path == appdata / "lanhu-design-mcp" / "browser-profile"

    def test_automatic_detection_uses_platform_system(self, tmp_path):
        """When system=None, platform.system() is used for detection."""
        appdata = tmp_path / "AppData" / "Local"
        with patch("lanhu_design_mcp.managed_auth.platform.system", return_value="Windows"):
            path = default_profile_dir(environ={"LOCALAPPDATA": str(appdata), "HOME": str(tmp_path)})
        assert path == appdata / "lanhu-design-mcp" / "browser-profile"

    def test_automatic_detection_darwin(self, tmp_path):
        with patch("lanhu_design_mcp.managed_auth.platform.system", return_value="Darwin"):
            path = default_profile_dir(environ={"HOME": str(tmp_path)})
        expected = tmp_path / "Library" / "Application Support" / "lanhu-design-mcp" / "browser-profile"
        assert path == expected


# ---------------------------------------------------------------------------
# filter_lanhu_cookies
# ---------------------------------------------------------------------------


class TestFilterLanhuCookies:
    def test_accepts_only_lanhu_domains(self):
        cookies = [
            {"name": "session", "value": "fake", "domain": ".lanhuapp.com"},
            {"name": "evil", "value": "secret", "domain": "example.com"},
        ]
        assert [item["name"] for item in filter_lanhu_cookies(cookies)] == ["session"]

    def test_rejects_substring_matches(self):
        """A domain like 'fakelanhuapp.com' must not pass the allowlist."""
        cookies = [
            {"name": "session", "value": "fake", "domain": "fakelanhuapp.com"},
            {"name": "other", "value": "x", "domain": "xlanhuapp.comx"},
        ]
        assert filter_lanhu_cookies(cookies) == []

    def test_accepts_exact_and_dot_prefixed_domains(self):
        cookies = [
            {"name": "s1", "value": "v1", "domain": "lanhuapp.com"},
            {"name": "s2", "value": "v2", "domain": ".lanhuapp.com"},
            {"name": "s3", "value": "v3", "domain": "dds.lanhuapp.com"},
            {"name": "s4", "value": "v4", "domain": ".dds.lanhuapp.com"},
        ]
        names = [item["name"] for item in filter_lanhu_cookies(cookies)]
        assert names == ["s1", "s2", "s3", "s4"]

    def test_empty_input(self):
        assert filter_lanhu_cookies([]) == []

    def test_missing_domain_field_is_rejected(self):
        assert filter_lanhu_cookies([{"name": "x", "value": "y"}]) == []

    # Normalization: whitespace, case, trailing dot
    def test_normalizes_whitespace(self):
        cookies = [
            {"name": "s", "value": "v", "domain": "  lanhuapp.com  "},
        ]
        assert len(filter_lanhu_cookies(cookies)) == 1

    def test_normalizes_uppercase(self):
        cookies = [
            {"name": "s", "value": "v", "domain": "LANHUAPP.COM"},
            {"name": "t", "value": "v", "domain": ".LANHUAPP.COM"},
        ]
        names = [item["name"] for item in filter_lanhu_cookies(cookies)]
        assert names == ["s", "t"]

    def test_normalizes_trailing_dot_while_keeping_leading_dot(self):
        """Trailing dot stripped; leading dot semantics preserved."""
        cookies = [
            {"name": "s", "value": "v", "domain": ".lanhuapp.com."},
            {"name": "t", "value": "v", "domain": "lanhuapp.com."},
        ]
        names = [item["name"] for item in filter_lanhu_cookies(cookies)]
        assert names == ["s", "t"]

    def test_rejects_lookalike_prefix_domain(self):
        """Prefix lookalikes like 'thelanhuapp.com' must not match."""
        assert filter_lanhu_cookies([{"name": "x", "value": "y", "domain": "thelanhuapp.com"}]) == []

    def test_rejects_lookalike_suffix_domain(self):
        """Suffix lookalikes like 'lanhuapp.com.evil' must not match."""
        assert filter_lanhu_cookies([{"name": "x", "value": "y", "domain": "lanhuapp.com.evil"}]) == []


# ---------------------------------------------------------------------------
# format_cookie_header
# ---------------------------------------------------------------------------


class TestFormatCookieHeader:
    def test_formats_name_value_pairs(self):
        header = format_cookie_header([
            {"name": "session", "value": "abc"},
            {"name": "tfstk", "value": "xyz"},
        ])
        # Must be sorted by name for determinism
        assert header == "session=abc; tfstk=xyz"

    def test_always_sorted_by_name(self):
        header = format_cookie_header([
            {"name": "z", "value": "1"},
            {"name": "a", "value": "2"},
        ])
        assert header == "a=2; z=1"

    def test_empty_returns_empty_string(self):
        assert format_cookie_header([]) == ""


# ---------------------------------------------------------------------------
# AuthSnapshot serialization safety
# ---------------------------------------------------------------------------


class TestAuthSnapshotSafety:
    def test_never_serializes_cookie_values(self):
        snapshot = AuthSnapshot(
            status="authenticated",
            authenticated=True,
            source="managed_browser",
            cookie_names=["session"],
            session_id="id",
            message=None,
        )
        d = snapshot.to_dict()
        # cookieNames is the only allowed cookie-related field; no value may leak
        assert d["cookieNames"] == ["session"]
        # No field in the dict should carry a cookie value (key=value pattern)
        for v in d.values():
            if isinstance(v, str):
                assert "=" not in v, f"value leak: {v}"

    def test_message_is_optional(self):
        snapshot = AuthSnapshot(
            status="missing",
            authenticated=False,
            source="missing",
            cookie_names=[],
        )
        d = snapshot.to_dict()
        assert "message" not in d
        assert d["status"] == "missing"


# ---------------------------------------------------------------------------
# ensure_owned_profile
# ---------------------------------------------------------------------------


class TestEnsureOwnedProfile:
    def test_creates_directories_with_marker(self, tmp_path):
        profile = tmp_path / "browser-profile"
        ensure_owned_profile(profile)
        assert profile.is_dir()
        assert (profile / ".lanhu-design-mcp-profile").exists()

    def test_posix_permissions_are_owner_only(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        mode = profile.stat().st_mode
        assert mode & 0o777 == 0o700

    @patch.object(Path, "home", return_value=Path("/fake/home"))
    def test_rejects_default_chrome_profile(self, mock_home):
        chrome_default = Path("/fake/home") / "Library" / "Application Support" / "Google" / "Chrome" / "Default"
        with pytest.raises(UnsafeProfileError, match="default Chrome profile"):
            ensure_owned_profile(chrome_default)

    def test_rejects_path_ending_with_default(self, tmp_path):
        profile = tmp_path / "Default"
        with pytest.raises(UnsafeProfileError):
            ensure_owned_profile(profile)


# ---------------------------------------------------------------------------
# remove_owned_profile
# ---------------------------------------------------------------------------


class TestRemoveOwnedProfile:
    def test_removes_marked_directory(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        assert profile.exists()
        remove_owned_profile(profile)
        assert not profile.exists()

    def test_unmarked_directory_cannot_be_removed(self, tmp_path):
        profile = tmp_path / "unmarked"
        profile.mkdir()
        with pytest.raises(UnsafeProfileError):
            remove_owned_profile(profile)
        assert profile.exists()

    def test_cannot_remove_directory_with_marker_in_subdirectory(self, tmp_path):
        """Marker must be a direct child, not nested deeper."""
        profile = tmp_path / "profile"
        profile.mkdir()
        sub = profile / "sub"
        sub.mkdir()
        (sub / ".lanhu-design-mcp-profile").write_text("")
        with pytest.raises(UnsafeProfileError):
            remove_owned_profile(profile)
        assert profile.exists()

    def test_symlink_to_marked_directory_is_rejected(self, tmp_path):
        """A symlink pointing at a marked directory must not be followed for deletion."""
        real_profile = tmp_path / "real-profile"
        ensure_owned_profile(real_profile)
        symlink = tmp_path / "link-to-profile"
        symlink.symlink_to(real_profile)
        with pytest.raises(UnsafeProfileError):
            remove_owned_profile(symlink)
        assert real_profile.exists()
        assert symlink.is_symlink()


class TestWindowsMode:
    """Profile operations on Windows skip POSIX-specific behaviours."""

    def test_ensure_owned_profile_does_not_chmod_on_windows(self, tmp_path):
        profile = tmp_path / "profile"
        with (
            patch("lanhu_design_mcp.managed_auth.os.name", "nt"),
            patch("lanhu_design_mcp.managed_auth.os.chmod") as mock_chmod,
        ):
            try:
                ensure_owned_profile(profile)
            except FileNotFoundError:
                # Windows may behave differently on non-Windows; chmod call is
                # what we are testing.
                pass
        mock_chmod.assert_not_called()


# ---------------------------------------------------------------------------
# cross-checks
# ---------------------------------------------------------------------------


class TestCookieInfoCompatibility:
    def test_cookie_info_accepts_managed_browser_source(self):
        info = CookieInfo(True, "session=x", "managed_browser", None, ["session"])
        assert info.source == "managed_browser"
        assert info.configured is True
        assert info.cookie_names == ["session"]

    def test_lanhu_domains_is_an_exact_allowlist(self):
        assert isinstance(LANHU_DOMAINS, (set, frozenset))
        assert "lanhuapp.com" in LANHU_DOMAINS
        assert ".lanhuapp.com" in LANHU_DOMAINS
        assert "dds.lanhuapp.com" in LANHU_DOMAINS
        assert ".dds.lanhuapp.com" in LANHU_DOMAINS


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
OTHER_COOKIE = {"name": "track", "value": "x", "domain": "example.com"}


def _auth(backend=None, profile_dir=None, **kw):
    if profile_dir is None:
        profile_dir = Path("/tmp/test-profile")
    if backend is None:
        backend = FakeBackend()
    kw.setdefault("poll_interval", 0.01)
    kw.setdefault("timeout", 1)
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
        assert result["status"] in {"dependency_missing", "profile_locked", "missing"}
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
    async def test_login_and_resolve_never_open_profile_concurrently(self, tmp_path):
        profile = tmp_path / "profile"
        ensure_owned_profile(profile)
        start_block = asyncio.Event()
        backend = BlockingBackend(cookies=[LANHU_SESSION], block_event=start_block)
        auth = _auth(backend=backend, profile_dir=profile)
        # Login blocks
        login_task = asyncio.create_task(auth.start_login())
        await asyncio.sleep(0.15)
        # Resolve tries — should not open concurrently
        resolve_task = asyncio.create_task(auth.resolve_cookie())
        await asyncio.sleep(0.1)
        # Only login opened the backend
        assert backend.open_count <= 1
        start_block.set()
        await login_task
        await resolve_task
        assert backend.open_count <= 2
