"""Tests for MCP auth tools and health-check safety."""

from __future__ import annotations

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
