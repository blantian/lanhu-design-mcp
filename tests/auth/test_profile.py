"""auth.profile 的 Profile 路径、Cookie 过滤和生命周期安全测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lanhu_design_mcp.auth.models import UnsafeProfileError, UnsupportedPlatformError
from lanhu_design_mcp.auth.profile import (
    default_profile_dir,
    ensure_owned_profile,
    filter_lanhu_cookies,
    format_cookie_header,
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

    def test_automatic_detection_darwin(self, tmp_path):
        with patch("lanhu_design_mcp.auth.profile.platform.system", return_value="Darwin"):
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


# ---------------------------------------------------------------------------
# Windows mode (chmod guard)
# ---------------------------------------------------------------------------


class TestWindowsMode:
    """Profile operations on Windows skip POSIX-specific behaviours."""

    def test_ensure_owned_profile_does_not_chmod_on_windows(self, tmp_path):
        profile = tmp_path / "profile"
        with (
            patch("lanhu_design_mcp.auth.profile.os.name", "nt"),
            patch("lanhu_design_mcp.auth.profile.os.chmod") as mock_chmod,
        ):
            try:
                ensure_owned_profile(profile)
            except FileNotFoundError:
                pass
        mock_chmod.assert_not_called()


# ---------------------------------------------------------------------------
# macOS-only boundary — profile path tests
# ---------------------------------------------------------------------------


class TestMacOSOnlyBoundary:
    def test_default_profile_dir_rejects_non_darwin(self):
        with pytest.raises(UnsupportedPlatformError):
            default_profile_dir(system="Linux", environ={"HOME": "/tmp/user"})

    def test_default_profile_dir_uses_macos_application_support(self):
        path = default_profile_dir(system="Darwin", environ={"HOME": "/Users/tester"})
        assert path == Path(
            "/Users/tester/Library/Application Support/lanhu-design-mcp/browser-profile"
        )
