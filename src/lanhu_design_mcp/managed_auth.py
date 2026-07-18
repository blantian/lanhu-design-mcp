"""Managed browser authentication — profiles, cookie safety, login state machine."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import stat as stat_mod
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, Sequence

from .config import CookieInfo

AuthStatus = Literal[
    "missing",
    "starting",
    "waiting_for_user",
    "authenticated",
    "expired",
    "cancelled",
    "timed_out",
    "dependency_missing",
    "profile_locked",
    "failed",
]

LANHU_DOMAINS: set[str] = {"lanhuapp.com", ".lanhuapp.com", "dds.lanhuapp.com", ".dds.lanhuapp.com"}

PROFILE_MARKER = ".lanhu-design-mcp-profile"


class UnsafeProfileError(RuntimeError):
    """Raised when a profile operation targets an unsafe directory."""


@dataclass(frozen=True)
class AuthSnapshot:
    status: AuthStatus
    authenticated: bool
    source: str
    cookie_names: list[str]
    session_id: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "authenticated": self.authenticated,
            "source": self.source,
            "cookieNames": self.cookie_names,
            "sessionId": self.session_id,
        }
        if self.message:
            result["message"] = self.message
        return result


# ---------------------------------------------------------------------------
# profile directory resolution
# ---------------------------------------------------------------------------


def default_profile_dir(
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the platform-appropriate managed browser profile directory."""
    if system is None:
        system = platform.system()  # "Darwin", "Linux", "Windows", etc.

    if environ is None:
        environ = os.environ

    if system == "Darwin":
        base = Path(environ.get("HOME", Path.home())) / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:  # Linux / other POSIX
        xdg = environ.get("XDG_DATA_HOME")
        if xdg:
            base = Path(xdg)
        else:
            base = Path(environ.get("HOME", Path.home())) / ".local" / "share"

    return base / "lanhu-design-mcp" / "browser-profile"


# ---------------------------------------------------------------------------
# cookie filtering and formatting
# ---------------------------------------------------------------------------


def _normalize_domain(raw: str) -> str:
    """Normalize a cookie domain for exact allowlist membership.

    Strips whitespace, lowercases, removes one trailing DNS dot (but preserves
    a leading dot for subdomain wildcard semantics).
    """
    domain = raw.strip().lower()
    if domain.endswith(".") and not domain.startswith("."):
        domain = domain[:-1]
    elif domain.startswith(".") and domain.endswith("."):
        domain = domain[:-1]
    return domain


def filter_lanhu_cookies(cookies: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only cookies whose normalized domain is in the Lanhu allowlist.

    Uses exact set membership after normalization, never substring matching.
    """
    result: list[dict[str, Any]] = []
    for c in cookies:
        domain = str(c.get("domain") or "")
        if not domain.strip():
            continue
        if _normalize_domain(domain) in LANHU_DOMAINS:
            result.append(dict(c))
    return result


def format_cookie_header(cookies: Sequence[Mapping[str, Any]]) -> str:
    """Format an already-filtered cookie list into a ``name=value; ...`` header.

    Cookies are sorted by name for deterministic output.
    """
    if not cookies:
        return ""
    sorted_cookies = sorted(cookies, key=lambda c: str(c.get("name", "")))
    parts = [f'{c["name"]}={c["value"]}' for c in sorted_cookies]
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# profile lifecycle (marker-guarded)
# ---------------------------------------------------------------------------


def _is_default_chrome_profile(path: Path) -> bool:
    """Return True if *path* appears to be Chrome's ordinary default profile."""
    resolved = path.resolve()
    if resolved.name == "Default":
        return True
    parts = resolved.parts
    # Check for ... /Google/Chrome/Default
    for i, part in enumerate(parts):
        if part == "Google" and i + 2 < len(parts):
            if parts[i + 1] == "Chrome" and parts[i + 2] == "Default":
                return True
    return False


def ensure_owned_profile(profile_dir: Path) -> None:
    """Create the profile directory with a package marker.

    Sets POSIX owner-only permissions (``0700``).  Rejects paths that resolve
    to Chrome's ordinary default profile.
    """
    if _is_default_chrome_profile(profile_dir):
        raise UnsafeProfileError(f"Refusing to use the default Chrome profile: {profile_dir}")

    profile_dir.mkdir(parents=True, exist_ok=True)
    marker = profile_dir / PROFILE_MARKER
    marker.touch()

    # POSIX owner-only (skip on Windows)
    if os.name != "nt":
        current = stat_mod.S_IMODE(profile_dir.stat().st_mode)
        if current != 0o700:
            os.chmod(profile_dir, 0o700)


def remove_owned_profile(profile_dir: Path) -> None:
    """Delete *profile_dir* only if it contains the package marker as a direct child.

    Resolves the target path and rejects symlinks.  Raises
    :exc:`UnsafeProfileError` when the marker is absent, nested deeper, or the
    path is a symlink.
    """
    resolved = profile_dir.resolve()
    if profile_dir.is_symlink():
        raise UnsafeProfileError(f"Refusing to follow symlink for profile removal: {profile_dir}")
    marker = resolved / PROFILE_MARKER
    if not marker.is_file():
        raise UnsafeProfileError(f"Profile directory is not owned by this package: {profile_dir}")
    shutil.rmtree(resolved)


# =============================================================================
# Async browser protocols and error types
# =============================================================================


class AuthDependencyError(RuntimeError):
    """Raised when a required optional dependency is missing."""


class AuthProfileLockedError(RuntimeError):
    """Raised when the managed browser profile is locked by another process."""


class BrowserSession(Protocol):
    async def cookies(self) -> list[dict[str, Any]]: ...
    def is_closed(self) -> bool: ...
    async def close(self) -> None: ...


class BrowserBackend(Protocol):
    async def open(self, profile_dir: Path, *, headless: bool) -> BrowserSession: ...


# =============================================================================
# ManagedBrowserAuth — async state machine
# =============================================================================

AUTH_COOKIE_NAMES = {"session", "user_token"}


class PlaywrightBrowserBackend:
    """Real browser backend using Playwright + installed Chrome (channel)."""

    async def open(self, profile_dir: Path, *, headless: bool) -> BrowserSession:
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-untyped]
        except ImportError as exc:
            raise AuthDependencyError(
                "Install automatic login with: pip install --upgrade lanhu-design-mcp"
            ) from exc

        pw = None
        context = None
        page = None
        try:
            pw = await async_playwright().__aenter__()
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=headless,
            )
        except Exception as exc:
            if pw is not None:
                await pw.__aexit__(None, None, None)
            msg = str(exc).lower()
            if "executable" in msg and "chrome" in msg:
                raise AuthDependencyError("Google Chrome is required for automatic login.") from exc
            if "lock" in msg or "profile" in msg:
                raise AuthProfileLockedError("The managed browser profile is locked.") from exc
            raise

        if not headless:
            try:
                pages = context.pages
                page = pages[0] if pages else await context.new_page()
                await page.goto("https://lanhuapp.com/", wait_until="domcontentloaded")
            except Exception:
                try:
                    await context.close()
                except Exception:
                    pass
                await pw.__aexit__(None, None, None)
                raise

        class _PlaywrightSession:
            def __init__(self_):
                self_._closed = False
                self_._driver_stopped = False

                def on_close(*args: Any) -> None:
                    self_._closed = True

                context.on("close", on_close)
                if page is not None:
                    page.on("close", on_close)

            async def cookies(self_):
                return await context.cookies()

            def is_closed(self_):
                return self_._closed

            async def close(self_):
                if self_._closed and self_._driver_stopped:
                    return
                self_._closed = True
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await pw.__aexit__(None, None, None)
                except Exception:
                    pass
                self_._driver_stopped = True

        return _PlaywrightSession()


class ManagedBrowserAuth:
    """Owns the managed Chrome profile login lifecycle."""

    def __init__(
        self,
        *,
        backend: BrowserBackend | None = None,
        profile_dir: Path | None = None,
        timeout: float = 300,
        poll_interval: float = 1.0,
    ):
        self._backend_impl = backend
        self._profile_path = profile_dir
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._state_lock = asyncio.Lock()
        self._browser_lock = asyncio.Lock()
        self._session_id: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._cached_header: str | None = None
        self._cached_names: list[str] = []
        self._state: AuthStatus = "missing"
        self._message: str | None = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _resolve_profile(self) -> Path:
        if self._profile_path is None:
            self._profile_path = default_profile_dir()
        return self._profile_path

    def _resolve_backend(self) -> BrowserBackend:
        if self._backend_impl is None:
            self._backend_impl = PlaywrightBrowserBackend()
        return self._backend_impl

    def _snapshot(self) -> AuthSnapshot:
        return AuthSnapshot(
            status=self._state,
            authenticated=self._state == "authenticated",
            source="managed_browser" if self._state == "authenticated" else self._state,
            cookie_names=list(self._cached_names),
            session_id=self._session_id,
            message=self._message,
        )

    def _has_auth_cookie(self, cookies: list[dict[str, Any]]) -> bool:
        allowed = filter_lanhu_cookies(cookies)
        return any(c["name"].lower() in AUTH_COOKIE_NAMES for c in allowed)

    @staticmethod
    def _safe_dependency_message() -> str:
        return "Automatic login dependencies are not available. Install with: pip install --upgrade lanhu-design-mcp"

    @staticmethod
    def _safe_profile_locked_message() -> str:
        return "The managed browser profile is locked by another process."

    @staticmethod
    def _safe_failure_message() -> str:
        return "An unexpected error occurred during login."

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def status_now(self) -> dict[str, Any]:
        return self._snapshot().to_dict()

    async def status(self, session_id: str | None = None, *, probe_profile: bool = False) -> dict[str, Any]:
        if session_id is not None and session_id != self._session_id:
            return AuthSnapshot("missing", False, "missing", [], session_id=session_id).to_dict()
        if probe_profile and self._state == "missing" and not self._cached_header:
            await self.resolve_cookie()
        return self._snapshot().to_dict()

    async def start_login(self) -> dict[str, Any]:
        async with self._state_lock:
            if self._task and not self._task.done():
                return self._snapshot().to_dict()
            self._session_id = uuid.uuid4().hex
            self._state = "starting"
            self._message = None
            self._task = asyncio.create_task(self._login_worker())
            await asyncio.sleep(0)
            return self._snapshot().to_dict()

    async def resolve_cookie(self) -> CookieInfo:
        if self._cached_header:
            return CookieInfo(True, self._cached_header, "managed_browser", None, list(self._cached_names))

        async with self._browser_lock:
            if self._cached_header:
                return CookieInfo(True, self._cached_header, "managed_browser", None, list(self._cached_names))

            profile = self._resolve_profile()
            if not (profile / PROFILE_MARKER).is_file():
                return CookieInfo(False, "", "missing", None, [])

            try:
                ensure_owned_profile(profile)
                session = await self._resolve_backend().open(profile, headless=True)
                try:
                    cookies = await session.cookies()
                finally:
                    await session.close()
            except AuthDependencyError:
                self._state = "dependency_missing"
                self._message = self._safe_dependency_message()
                return CookieInfo(False, "", "missing", None, [])
            except AuthProfileLockedError:
                self._state = "profile_locked"
                self._message = self._safe_profile_locked_message()
                return CookieInfo(False, "", "missing", None, [])
            except Exception:
                self._state = "failed"
                self._message = self._safe_failure_message()
                return CookieInfo(False, "", "missing", None, [])

            allowed = filter_lanhu_cookies(cookies)
            if not self._has_auth_cookie(cookies) or not allowed:
                return CookieInfo(False, "", "missing", None, [])

            header = format_cookie_header(allowed)
            self._cached_header = header
            self._cached_names = [c["name"] for c in allowed]
            self._state = "authenticated"
            self._message = None
            return CookieInfo(True, header, "managed_browser", None, list(self._cached_names))

    def invalidate(self) -> None:
        self._cached_header = None
        self._cached_names = []
        if self._state == "authenticated":
            self._state = "expired"

    async def logout(self, confirm: bool = False) -> dict[str, Any]:
        if not confirm:
            return {"status": "confirmation_required", "message": "Set confirm=true to delete the managed profile."}

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._cached_header = None
        self._cached_names = []

        async with self._browser_lock:
            profile = self._resolve_profile()
            try:
                remove_owned_profile(profile)
            except UnsafeProfileError:
                pass

        self._state = "missing"
        self._session_id = None
        self._message = None
        return {"status": "logged_out"}

    async def wait_for_terminal_state(self) -> None:
        if self._task and not self._task.done():
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def shutdown(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._state = "missing"

    # ------------------------------------------------------------------
    # internal worker
    # ------------------------------------------------------------------

    async def _login_worker(self) -> None:
        session: BrowserSession | None = None
        try:
            profile = self._resolve_profile()
            ensure_owned_profile(profile)
            async with self._browser_lock:
                try:
                    session = await self._resolve_backend().open(profile, headless=False)
                    self._state = "waiting_for_user"
                    deadline = asyncio.get_event_loop().time() + self._timeout

                    while True:
                        remaining = deadline - asyncio.get_event_loop().time()
                        if remaining <= 0:
                            self._state = "timed_out"
                            self._message = "Login timed out."
                            return

                        try:
                            cookies = await asyncio.wait_for(session.cookies(), min(self._poll_interval, remaining))
                        except asyncio.TimeoutError:
                            continue

                        if session.is_closed():
                            self._state = "cancelled"
                            self._message = "Browser window was closed before login."
                            return

                        if self._has_auth_cookie(cookies):
                            allowed = filter_lanhu_cookies(cookies)
                            self._cached_header = format_cookie_header(allowed)
                            self._cached_names = [c["name"] for c in allowed]
                            self._state = "authenticated"
                            self._message = None
                            return

                        await asyncio.sleep(self._poll_interval)
                finally:
                    # Always call close while holding the lock — even if externally
                    # closed (is_closed=True), the driver may not yet be stopped.
                    if session is not None:
                        try:
                            await session.close()
                        except Exception:
                            pass

        except AuthDependencyError:
            self._state = "dependency_missing"
            self._message = self._safe_dependency_message()
        except AuthProfileLockedError:
            self._state = "profile_locked"
            self._message = self._safe_profile_locked_message()
        except asyncio.CancelledError:
            self._state = "cancelled"
            self._message = "Login was cancelled."
        except Exception:
            self._state = "failed"
            self._message = self._safe_failure_message()


# =============================================================================
# singleton
# =============================================================================

_managed_auth: ManagedBrowserAuth | None = None


def get_managed_auth() -> ManagedBrowserAuth:
    global _managed_auth
    if _managed_auth is None:
        _managed_auth = ManagedBrowserAuth()
    return _managed_auth
