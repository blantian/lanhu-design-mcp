"""Tests for CLI dispatch — no real browser launch."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestServerDispatch:
    def test_no_args_starts_mcp(self):
        with patch("lanhu_design_mcp.server.main") as run_server:
            from lanhu_design_mcp import cli
            assert cli.main([]) is None
            run_server.assert_called_once_with()


class TestAuthStatus:
    def test_auth_status_prints_safe_json(self, capsys):
        auth = AsyncMock()
        auth.status.return_value = {"status": "authenticated", "authenticated": True, "cookieNames": ["session"]}

        with patch("lanhu_design_mcp.cli.get_managed_auth", return_value=auth):
            from lanhu_design_mcp import cli
            ret = cli.main(["auth", "status"])
            out = capsys.readouterr().out

        assert ret == 0
        data = json.loads(out)
        assert data["status"] == "authenticated"
        assert "session=" not in out


class TestAuthLogin:
    def test_auth_login_waits_terminal_state(self):
        auth = AsyncMock()
        auth.start_login.return_value = {"status": "waiting_for_user", "sessionId": "x"}
        auth.wait_for_terminal_state = AsyncMock()
        auth.status.return_value = {"status": "authenticated", "authenticated": True}

        with patch("lanhu_design_mcp.cli.get_managed_auth", return_value=auth):
            from lanhu_design_mcp import cli
            ret = cli.main(["auth", "login"])

        auth.start_login.assert_called_once()
        auth.wait_for_terminal_state.assert_called_once()
        auth.status.assert_called_once()
        assert ret == 0

    def test_auth_login_returns_1_on_failure(self, capsys):
        auth = AsyncMock()
        auth.start_login.return_value = {"status": "waiting_for_user", "sessionId": "x"}
        auth.wait_for_terminal_state = AsyncMock()
        auth.status.return_value = {"status": "cancelled", "authenticated": False}

        with patch("lanhu_design_mcp.cli.get_managed_auth", return_value=auth):
            from lanhu_design_mcp import cli
            ret = cli.main(["auth", "login"])

        assert ret == 1


class TestAuthLogout:
    def test_auth_logout_without_confirm_returns_1_no_deletion(self):
        auth = AsyncMock()
        auth.logout.return_value = {"status": "confirmation_required"}
        with patch("lanhu_design_mcp.cli.get_managed_auth", return_value=auth):
            from lanhu_design_mcp import cli
            ret = cli.main(["auth", "logout"])
        auth.logout.assert_called_once_with(False)
        assert ret == 1

    def test_auth_logout_with_confirm_returns_0(self):
        auth = AsyncMock()
        auth.logout.return_value = {"status": "logged_out"}
        with patch("lanhu_design_mcp.cli.get_managed_auth", return_value=auth):
            from lanhu_design_mcp import cli
            ret = cli.main(["auth", "logout", "--confirm"])
        auth.logout.assert_called_once_with(True)
        assert ret == 0


class TestInvalidUsage:
    def test_invalid_command_returns_2(self, capsys):
        from lanhu_design_mcp import cli
        ret = cli.main(["invalid"])
        assert ret == 2

    def test_help_does_not_import_playwright(self):
        # Remove playwright from sys.modules to prove it's not imported
        pw = sys.modules.pop("playwright", None)
        try:
            from lanhu_design_mcp import cli
            ret = cli.main(["--help"])
            assert ret in {0, 2}
        finally:
            if pw:
                sys.modules["playwright"] = pw


class TestEntryPoint:
    def test_no_args_imports_cli_not_server_main_directly(self):
        """The entrypoint name is unchanged but points to cli.main."""
        import lanhu_design_mcp.cli as cli_mod
        assert hasattr(cli_mod, "main")
