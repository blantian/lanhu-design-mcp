import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lanhu_design_mcp.config import (
    CookieInfo,
    cookie_names_from_header,
    default_lanhu_cookie_file,
    get_settings,
    resolve_configured_lanhu_cookie,
    resolve_dds_cookie,
    resolve_lanhu_cookie,
    resolve_legacy_browser_cookie,
)


class TestCookieNamesFromHeader:
    def test_extracts_cookie_names(self):
        names = cookie_names_from_header("session=abc123; tfstk=xyz789")
        assert names == ["session", "tfstk"]

    def test_handles_empty_string(self):
        assert cookie_names_from_header("") == []

    def test_ignores_segments_without_equals(self):
        names = cookie_names_from_header("a=1; b=2; noseparator")
        assert names == ["a", "b"]

    def test_handles_whitespace(self):
        names = cookie_names_from_header("  a=1  ;  b=2  ")
        assert names == ["a", "b"]


class TestDefaultLanhuCookieFile:
    def test_default_path_ends_with_cagent_cookie_txt(self):
        p = default_lanhu_cookie_file()
        assert p.parts[-4:] == (".config", "cagent", "lanhu", "cookie.txt")


class TestResolveLanhuCookie:
    def test_explicit_file_beats_env_var(self, tmp_path, monkeypatch):
        cookie_file = tmp_path / "my_cookie.txt"
        cookie_file.write_text("session=fromfile; tfstk=ff")
        monkeypatch.setenv("LANHU_COOKIE_FILE", str(cookie_file))
        monkeypatch.setenv("LANHU_COOKIE", "session=fromenv")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")

        info = resolve_lanhu_cookie()
        assert info.configured is True
        assert info.source == "file"
        assert info.cookie_file == cookie_file
        assert info.cookie == "session=fromfile; tfstk=ff"
        assert info.cookie_names == ["session", "tfstk"]

    def test_env_var_works_when_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LANHU_COOKIE", "session=envcookie")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")
        # Ensure default file doesn't exist
        with patch.object(
            Path, "home", return_value=tmp_path
        ):
            info = resolve_lanhu_cookie()
            assert info.configured is True
            assert info.source == "env"
            assert info.cookie_file is None
            assert info.cookie == "session=envcookie"
            assert info.cookie_names == ["session"]

    def test_default_cagent_file_takes_priority_over_env(self, tmp_path, monkeypatch):
        # Simulate default CAgent file
        home = tmp_path / "home"
        cagent_file = home / ".config" / "cagent" / "lanhu" / "cookie.txt"
        cagent_file.parent.mkdir(parents=True)
        cagent_file.write_text("session=cagent; tfstk=cc")
        monkeypatch.setenv("LANHU_COOKIE", "session=envcookie")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")
        monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)

        with patch.object(Path, "home", return_value=home):
            info = resolve_lanhu_cookie()
            assert info.configured is True
            assert info.source == "file"
            assert info.cookie_file == cagent_file
            assert info.cookie == "session=cagent; tfstk=cc"

    def test_returns_missing_when_nothing_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LANHU_COOKIE", raising=False)
        monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")

        with patch.object(Path, "home", return_value=tmp_path):
            info = resolve_lanhu_cookie()
            assert info.configured is False
            assert info.source == "missing"
            assert info.cookie == ""

    def test_no_browser_fallback_when_auto_browser_not_set(self, monkeypatch, tmp_path):
        """Default AUTO_BROWSER_COOKIES is false — browser fallback must not run."""
        monkeypatch.delenv("LANHU_COOKIE", raising=False)
        monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)
        monkeypatch.delenv("AUTO_BROWSER_COOKIES", raising=False)

        with patch.object(Path, "home", return_value=tmp_path):
            info = resolve_lanhu_cookie()
            assert info.configured is False
            assert info.source == "missing"
            assert info.cookie == ""


class TestResolveDdsCookie:
    def test_dds_cookie_overrides_lanhu(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DDS_COOKIE", "dds_cookie_value")
        monkeypatch.delenv("DDS_COOKIE_FILE", raising=False)

        lanhu_info = CookieInfo(
            configured=True,
            cookie="lanhu_cookie_value",
            source="env",
            cookie_file=None,
            cookie_names=["session"],
        )
        dds_info = resolve_dds_cookie(lanhu_info)
        assert dds_info.configured is True
        assert dds_info.source == "env"
        assert dds_info.cookie == "dds_cookie_value"

    def test_dds_falls_back_to_lanhu(self, monkeypatch):
        monkeypatch.delenv("DDS_COOKIE", raising=False)
        monkeypatch.delenv("DDS_COOKIE_FILE", raising=False)

        lanhu_info = CookieInfo(
            configured=True,
            cookie="lanhu_cookie_value",
            source="env",
            cookie_file=None,
            cookie_names=["session"],
        )
        dds_info = resolve_dds_cookie(lanhu_info)
        assert dds_info.configured is True
        assert dds_info.source == "lanhu"
        assert dds_info.cookie == "lanhu_cookie_value"

    def test_dds_cookie_file_priority(self, tmp_path, monkeypatch):
        cookie_file = tmp_path / "dds_cookie.txt"
        cookie_file.write_text("dds_from_file")
        monkeypatch.setenv("DDS_COOKIE_FILE", str(cookie_file))
        monkeypatch.setenv("DDS_COOKIE", "dds_from_env")

        lanhu_info = CookieInfo(
            configured=True,
            cookie="lanhu_cookie_value",
            source="env",
            cookie_file=None,
            cookie_names=["session"],
        )
        dds_info = resolve_dds_cookie(lanhu_info)
        assert dds_info.source == "file"
        assert dds_info.cookie_file == cookie_file
        assert dds_info.cookie == "dds_from_file"


class TestGetSettings:
    def test_settings_no_cookie(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LANHU_COOKIE", raising=False)
        monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")

        with patch.object(Path, "home", return_value=tmp_path):
            settings = get_settings()
            assert settings.lanhu_cookie == ""
            assert settings.lanhu_cookie_source == "missing"
            assert settings.lanhu_cookie_names == []

    def test_settings_with_lanhu_cookie(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LANHU_COOKIE", "session=test")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")

        with patch.object(Path, "home", return_value=tmp_path):
            settings = get_settings()
            assert settings.lanhu_cookie == "session=test"
            assert settings.lanhu_cookie_source == "env"
            assert settings.lanhu_cookie_names == ["session"]

    def test_settings_dds_metadata(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LANHU_COOKIE", "session=lanhu_only")
        monkeypatch.setenv("DDS_COOKIE", "session=dds_separate")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")

        with patch.object(Path, "home", return_value=tmp_path):
            settings = get_settings()
            assert settings.dds_cookie == "session=dds_separate"
            assert settings.dds_cookie_source == "env"


class TestHealthPayloadNoValues:
    def test_settings_never_expose_cookie_values(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LANHU_COOKIE", "session=topsecret")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")

        with patch.object(Path, "home", return_value=tmp_path):
            settings = get_settings()
            # The settings have the cookie for actual use, but health metadata
            # only exposes names, not values.
            assert settings.lanhu_cookie == "session=topsecret"
            assert "topsecret" not in str(settings.lanhu_cookie_names)
            assert settings.lanhu_cookie_names == ["session"]


# ---------------------------------------------------------------------------
# Task 1 (managed auth): split explicit and legacy cookie resolution
# ---------------------------------------------------------------------------


class TestConfiguredResolver:
    def test_configured_resolver_does_not_touch_browser(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LANHU_COOKIE", raising=False)
        monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch("lanhu_design_mcp.config.resolve_legacy_browser_cookie") as browser,
        ):
            # Even with AUTO_BROWSER_COOKIES=true, the configured resolver
            # must not invoke the browser fallback.
            info = resolve_configured_lanhu_cookie()
        assert info.source == "missing"
        browser.assert_not_called()

    def test_configured_resolver_file_beats_env(self, tmp_path, monkeypatch):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("session=fromfile; tfstk=ff")
        monkeypatch.setenv("LANHU_COOKIE_FILE", str(cookie_file))
        monkeypatch.setenv("LANHU_COOKIE", "session=fromenv")
        info = resolve_configured_lanhu_cookie()
        assert info.source == "file"
        assert info.cookie_file == cookie_file
        assert info.cookie == "session=fromfile; tfstk=ff"

    def test_configured_resolver_env_only(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)
        monkeypatch.setenv("LANHU_COOKIE", "session=envval")
        with patch.object(Path, "home", return_value=tmp_path):
            info = resolve_configured_lanhu_cookie()
        assert info.source == "env"
        assert info.cookie == "session=envval"


class TestLegacyBrowserResolver:
    def test_legacy_browser_skips_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("AUTO_BROWSER_COOKIES", raising=False)
        info = resolve_legacy_browser_cookie()
        assert info.source == "missing"
        assert info.cookie == ""

    def test_legacy_browser_skips_when_set_to_false(self, monkeypatch):
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")
        info = resolve_legacy_browser_cookie()
        assert info.source == "missing"

    @patch("lanhu_design_mcp.browser_cookies.get_lanhu_cookies", return_value="session=mock; tfstk=ff")
    def test_legacy_browser_returns_browser_info(self, mock_browser, monkeypatch):
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
        info = resolve_legacy_browser_cookie()
        assert info.source == "browser"
        assert info.configured is True
        assert info.cookie == "session=mock; tfstk=ff"
        assert info.cookie_names == ["session", "tfstk"]

    @patch("lanhu_design_mcp.browser_cookies.get_lanhu_cookies", side_effect=OSError("locked"))
    def test_legacy_browser_returns_missing_on_error(self, mock_browser, monkeypatch):
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
        info = resolve_legacy_browser_cookie()
        assert info.source == "missing"
        assert info.configured is False


class TestResolveLanhuCookieCompatibility:
    """Backward-compatibility: resolve_lanhu_cookie delegates to the new resolvers."""

    def test_configured_beats_legacy(self, tmp_path, monkeypatch):
        cookie_file = tmp_path / "cfg.txt"
        cookie_file.write_text("session=cfg")
        monkeypatch.setenv("LANHU_COOKIE_FILE", str(cookie_file))
        monkeypatch.setenv("LANHU_COOKIE", "session=env")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch("lanhu_design_mcp.browser_cookies.get_lanhu_cookies", return_value="session=db"),
        ):
            info = resolve_lanhu_cookie()
        assert info.source == "file"
        assert info.cookie == "session=cfg"


class TestGetSettingsWithManagedBrowser:
    def test_settings_accept_managed_browser_override(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DDS_COOKIE", raising=False)
        monkeypatch.delenv("DDS_COOKIE_FILE", raising=False)
        info = CookieInfo(True, "session=fake", "managed_browser", None, ["session"])
        with patch.object(Path, "home", return_value=tmp_path):
            settings = get_settings(include_browser_fallback=False, lanhu_override=info)
        assert settings.lanhu_cookie_source == "managed_browser"
        assert settings.lanhu_cookie == "session=fake"
        assert settings.dds_cookie == "session=fake"
        assert settings.dds_cookie_source == "lanhu"

    def test_settings_include_browser_fallback_controls_legacy(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LANHU_COOKIE", raising=False)
        monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch("lanhu_design_mcp.browser_cookies.get_lanhu_cookies", return_value="session=dbval"),
        ):
            settings_false = get_settings(include_browser_fallback=False)
            settings_true = get_settings(include_browser_fallback=True)
        assert settings_false.lanhu_cookie_source == "missing"
        assert settings_true.lanhu_cookie_source == "browser"

    def test_settings_lanhu_override_beats_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LANHU_COOKIE", "session=env")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
        info = CookieInfo(True, "session=override", "managed_browser", None, ["session"])
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch("lanhu_design_mcp.browser_cookies.get_lanhu_cookies", return_value="session=db"),
        ):
            settings = get_settings(include_browser_fallback=True, lanhu_override=info)
        assert settings.lanhu_cookie_source == "managed_browser"
        assert settings.lanhu_cookie == "session=override"

    def test_get_settings_without_args_preserves_full_backward_compat(self, tmp_path, monkeypatch):
        """No-arg get_settings() must still resolve through legacy fallback."""
        monkeypatch.setenv("LANHU_COOKIE", "session=backward")
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "false")
        with patch.object(Path, "home", return_value=tmp_path):
            settings = get_settings()
        assert settings.lanhu_cookie_source == "env"
        assert settings.lanhu_cookie == "session=backward"
