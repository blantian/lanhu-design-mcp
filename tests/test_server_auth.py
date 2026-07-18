"""Tests for MCP auth tools, health-check safety, and server metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from lanhu_design_mcp.managed_auth import AuthSnapshot


@pytest.mark.asyncio
async def test_auth_login_delegates_without_waiting():
    auth = AsyncMock()
    auth.start_login.return_value = {"status": "waiting_for_user", "sessionId": "id"}
    with patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth):
        from lanhu_design_mcp.server import lanhu_auth_login
        result = await lanhu_auth_login()
    assert result == {"status": "waiting_for_user", "sessionId": "id"}


@pytest.mark.asyncio
async def test_auth_status_with_session_id():
    auth = AsyncMock()
    auth.status.return_value = {"status": "authenticated", "authenticated": True, "cookieNames": ["session"]}
    with patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth):
        from lanhu_design_mcp.server import lanhu_auth_status
        result = await lanhu_auth_status(session_id="xyz")
    assert result["status"] == "authenticated"


@pytest.mark.asyncio
async def test_auth_logout_confirm_forwarded():
    auth = AsyncMock()
    auth.logout.return_value = {"status": "logged_out"}
    with patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth):
        from lanhu_design_mcp.server import lanhu_auth_logout
        result = await lanhu_auth_logout(confirm=True)
    auth.logout.assert_called_once_with(True)
    assert result == {"status": "logged_out"}


@pytest.mark.asyncio
async def test_health_lists_auth_tools_and_uses_status_now():
    auth = Mock()
    auth.status_now.return_value = AuthSnapshot("missing", False, "missing", []).to_dict()
    with (
        patch("lanhu_design_mcp.server.get_settings") as mock_settings,
        patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth),
    ):
        mock_settings.return_value.lanhu_cookie = ""
        mock_settings.return_value.lanhu_cookie_source = "missing"
        mock_settings.return_value.lanhu_cookie_names = []
        mock_settings.return_value.dds_cookie = ""
        mock_settings.return_value.dds_cookie_source = "missing"
        mock_settings.return_value.dds_cookie_names = []
        mock_settings.return_value.lanhu_cookie_file = None
        mock_settings.return_value.dds_cookie_file = None

        from lanhu_design_mcp.server import lanhu_health_check
        result = await lanhu_health_check()

    assert "lanhu_auth_login" in result["tools"]
    assert "lanhu_auth_status" in result["tools"]
    assert "lanhu_auth_logout" in result["tools"]
    assert "managedAuth" in result
    auth.resolve_cookie.assert_not_called()
    auth.status_now.assert_called_once()


@pytest.mark.asyncio
async def test_health_never_calls_legacy_or_network():
    auth = Mock()
    auth.status_now.return_value = AuthSnapshot("missing", False, "missing", []).to_dict()
    with (
        patch("lanhu_design_mcp.server.get_settings") as mock_settings,
        patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth),
    ):
        mock_settings.return_value.lanhu_cookie = ""
        mock_settings.return_value.lanhu_cookie_source = "missing"
        mock_settings.return_value.lanhu_cookie_names = []
        mock_settings.return_value.dds_cookie = ""
        mock_settings.return_value.dds_cookie_source = "missing"
        mock_settings.return_value.dds_cookie_names = []
        mock_settings.return_value.lanhu_cookie_file = None
        mock_settings.return_value.dds_cookie_file = None

        from lanhu_design_mcp.server import lanhu_health_check
        await lanhu_health_check()

    auth.resolve_cookie.assert_not_called()
    auth.status_now.assert_called_once()


# ---------------------------------------------------------------------------
# server.json contract tests
# ---------------------------------------------------------------------------


class TestServerJson:
    def test_valid_json(self):
        data = json.loads(Path("server.json").read_text())
        assert data["name"] == "io.github.buluesky/lanhu-design-mcp"
        assert data["version"] == "0.1.0"
        assert "$schema" in data

    def test_description_length(self):
        data = json.loads(Path("server.json").read_text())
        assert len(data["description"]) <= 100, f"description too long: {len(data['description'])} chars"

    def test_repository_source_is_github(self):
        data = json.loads(Path("server.json").read_text())
        assert data["repository"]["source"] == "github"
        assert data["repository"]["url"].startswith("https://github.com")

    def test_package_identifier_and_version(self):
        data = json.loads(Path("server.json").read_text())
        pkg = data["packages"][0]
        assert pkg["identifier"] == "lanhu-design-mcp"
        assert pkg["registryType"] == "pypi"
        assert pkg["version"] == "0.1.0"
        assert pkg["transport"]["type"] == "stdio"

    def test_environment_variables_array(self):
        data = json.loads(Path("server.json").read_text())
        env_vars = data["packages"][0]["environmentVariables"]
        names = {v["name"] for v in env_vars}
        assert "LANHU_COOKIE" in names
        assert "DDS_COOKIE" in names
        assert "AUTO_BROWSER_COOKIES" in names

    def test_lanhu_cookie_not_required(self):
        data = json.loads(Path("server.json").read_text())
        for v in data["packages"][0]["environmentVariables"]:
            if v["name"] == "LANHU_COOKIE":
                assert v["isRequired"] is False
                assert v["isSecret"] is True

    def test_auto_browser_cookies_default_false(self):
        data = json.loads(Path("server.json").read_text())
        for v in data["packages"][0]["environmentVariables"]:
            if v["name"] == "AUTO_BROWSER_COOKIES":
                assert v.get("default") == "false"

    def test_no_unsupported_old_fields(self):
        data = json.loads(Path("server.json").read_text())
        assert "homepage" not in data
        assert "license" not in data
        assert "author" not in data
        assert "keywords" not in data
        assert "config" not in data
        pkg = data["packages"][0]
        assert "command" not in pkg
        assert "type" not in pkg


# ---------------------------------------------------------------------------
# pyproject.toml packaging contract
# ---------------------------------------------------------------------------


class TestPyproject:
    def test_playwright_is_core_dependency(self):
        text = Path("pyproject.toml").read_text()
        deps_section = text.split("[project.optional-dependencies]")[0]
        assert "playwright" in deps_section

    def test_no_auth_extra(self):
        text = Path("pyproject.toml").read_text()
        assert "auth = [" not in text

    def test_cli_entry_point(self):
        text = Path("pyproject.toml").read_text()
        assert "lanhu-design-mcp = \"lanhu_design_mcp.cli:main\"" in text
