"""Tests for MCP auth tools, health-check safety, and server metadata."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from lanhu_design_mcp.auth.manager import AuthSnapshot


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
async def test_health_reports_only_managed_auth_metadata():
    auth = Mock()
    auth.status_now.return_value = AuthSnapshot("missing", False, "missing", []).to_dict()
    with patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth):
        from lanhu_design_mcp.server import lanhu_health_check
        result = await lanhu_health_check()
    assert set(result) == {"sdk", "tools", "managedAuth"}
    assert result["sdk"] == "fastmcp"
    assert "lanhu_auth_login" in result["tools"]
    assert "lanhu_auth_status" in result["tools"]
    assert "lanhu_auth_logout" in result["tools"]
    auth.status_now.assert_called_once()


def test_main_always_runs_stdio():
    with patch("lanhu_design_mcp.server.mcp.run") as run:
        from lanhu_design_mcp.server import main
        main()
    run.assert_called_once_with(transport="stdio")


# ---------------------------------------------------------------------------
# server.json contract tests
# ---------------------------------------------------------------------------


class TestServerJson:
    def test_valid_json(self):
        data = json.loads(Path("server.json").read_text())
        assert data["name"] == "io.github.blantian/lanhu-design-mcp"
        assert data["version"] == "0.2.0"
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
        assert pkg["version"] == "0.2.0"
        assert pkg["transport"]["type"] == "stdio"

    def test_package_has_no_environment_variables(self):
        data = json.loads(Path("server.json").read_text())
        assert "environmentVariables" not in data["packages"][0]

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


# ---------------------------------------------------------------------------
# Documentation contract tests
# ---------------------------------------------------------------------------


class TestDocs:
    def test_readme_has_managed_login_workflow(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "lanhu-design-mcp auth login" in readme
        assert "lanhu_auth_login" in readme
        assert "auth_required" in readme

    def test_readme_no_auth_extra_syntax(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "lanhu-design-mcp[auth]" not in readme

    def test_readme_has_managed_profile_reference(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "Chrome 配置" in readme or "Chrome Profile" in readme


# ---------------------------------------------------------------------------
# Release identity contract tests
# ---------------------------------------------------------------------------


class TestReleaseIdentity:
    def test_public_metadata_uses_blantian(self):
        server = json.loads(Path("server.json").read_text())
        assert server["name"] == "io.github.blantian/lanhu-design-mcp"
        assert server["repository"]["url"] == "https://github.com/blantian/lanhu-design-mcp"

        readme = Path("README.md").read_text()
        assert "<!-- mcp-name: io.github.blantian/lanhu-design-mcp -->" in readme

        pyproject = Path("pyproject.toml").read_text()
        assert 'Homepage = "https://github.com/blantian/lanhu-design-mcp"' in pyproject
        assert 'Repository = "https://github.com/blantian/lanhu-design-mcp"' in pyproject
        assert 'Issues = "https://github.com/blantian/lanhu-design-mcp/issues"' in pyproject
        assert "buluesky@example.com" not in pyproject

        changelog = Path("CHANGELOG.md").read_text()
        assert "https://github.com/blantian/lanhu-design-mcp/releases/tag/v0.1.0" in changelog
