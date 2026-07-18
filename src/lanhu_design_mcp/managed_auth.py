"""Managed browser authentication foundations — pure functions only.

This module owns profile paths, cookie filtering/formatting, safe result
serialization, and marker-guarded profile lifecycle.  It does NOT import
Playwright or launch a browser.  The async state machine is in a later task.
"""

from __future__ import annotations

import os
import shutil
import stat as stat_mod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

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
        system = os.uname().sysname if hasattr(os, "uname") else os.name

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


def filter_lanhu_cookies(cookies: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only cookies whose normalized domain is in the Lanhu allowlist.

    Uses exact set membership, never substring matching.
    """
    result: list[dict[str, Any]] = []
    for c in cookies:
        domain = str(c.get("domain") or "")
        if domain in LANHU_DOMAINS:
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

    # POSIX owner-only
    if hasattr(stat_mod, "S_IRWXU"):
        current = stat_mod.S_IMODE(profile_dir.stat().st_mode)
        if current != 0o700:
            os.chmod(profile_dir, 0o700)


def remove_owned_profile(profile_dir: Path) -> None:
    """Delete *profile_dir* only if it contains the package marker as a direct child.

    Raises :exc:`UnsafeProfileError` when the marker is absent or nested deeper.
    """
    marker = profile_dir / PROFILE_MARKER
    if not marker.is_file():
        raise UnsafeProfileError(f"Profile directory is not owned by this package: {profile_dir}")
    shutil.rmtree(profile_dir)
