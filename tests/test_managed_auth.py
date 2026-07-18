"""Tests for managed_auth pure foundations — no Playwright or browser launch."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from lanhu_design_mcp.config import CookieInfo
from lanhu_design_mcp.managed_auth import (
    LANHU_DOMAINS,
    AuthSnapshot,
    default_profile_dir,
    ensure_owned_profile,
    filter_lanhu_cookies,
    format_cookie_header,
    remove_owned_profile,
    UnsafeProfileError,
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

    def test_defaults_to_linux_behavior(self, tmp_path):
        path = default_profile_dir("Linux", {"HOME": str(tmp_path)})
        assert path == tmp_path / ".local" / "share" / "lanhu-design-mcp" / "browser-profile"


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
        # Verify the allowlist is a set for O(1) membership
        assert isinstance(LANHU_DOMAINS, (set, frozenset))
        assert "lanhuapp.com" in LANHU_DOMAINS
        assert ".lanhuapp.com" in LANHU_DOMAINS
        assert "dds.lanhuapp.com" in LANHU_DOMAINS
        assert ".dds.lanhuapp.com" in LANHU_DOMAINS
