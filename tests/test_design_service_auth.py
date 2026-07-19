"""Tests for DesignService managed-only auth resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from lanhu_design_mcp.client import LanhuAuthRequiredError
from lanhu_design_mcp.auth.models import CookieInfo
from lanhu_design_mcp.design_service import DesignService
from lanhu_design_mcp.auth.manager import ManagedBrowserAuth


@pytest.mark.asyncio
async def test_design_service_always_resolves_managed_cookie():
    auth = AsyncMock(spec=ManagedBrowserAuth)
    auth.resolve_cookie.return_value = CookieInfo(
        True, "session=managed", "managed_browser", ["session"]
    )
    service = DesignService(managed_auth=auth)
    settings = await service._resolve_settings()
    auth.resolve_cookie.assert_awaited_once()
    assert settings.lanhu_cookie == settings.dds_cookie == "session=managed"


@pytest.mark.asyncio
async def test_design_service_missing_managed_cookie_requires_login():
    auth = AsyncMock(spec=ManagedBrowserAuth)
    auth.resolve_cookie.return_value = CookieInfo(False, "", "missing", [])
    service = DesignService(managed_auth=auth)
    with pytest.raises(LanhuAuthRequiredError):
        await service._resolve_settings()
