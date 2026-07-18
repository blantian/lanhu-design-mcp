"""Tests for DesignService managed auth resolution and safe auth classification."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from lanhu_design_mcp.client import LanhuAuthRequiredError, raise_for_lanhu_auth
from lanhu_design_mcp.config import CookieInfo, get_settings
from lanhu_design_mcp.design_service import DesignService
from lanhu_design_mcp.managed_auth import ManagedBrowserAuth

URL = "https://lanhuapp.com/web/#/item/project/stage?pid=p1&image_id=i1"


# ---------------------------------------------------------------------------
# Safe auth classification
# ---------------------------------------------------------------------------


class TestLanhuAuthRequiredError:
    def test_has_safe_structured_payload(self):
        error = LanhuAuthRequiredError()
        d = error.to_dict()
        assert d == {"status": "auth_required", "nextAction": "lanhu_auth_login"}
        assert "cookie" not in str(d).lower()
        assert "session" not in str(error).lower()

    def test_is_compatible_runtime_error_subtype(self):
        assert issubclass(LanhuAuthRequiredError, RuntimeError)


class TestRaiseForLanhuAuth:
    def test_401_is_auth_failure(self):
        response = httpx.Response(401, request=httpx.Request("GET", "https://lanhuapp.com/api/x"))
        with pytest.raises(LanhuAuthRequiredError):
            raise_for_lanhu_auth(response)

    def test_418_is_auth_failure(self):
        response = httpx.Response(418, request=httpx.Request("GET", "https://lanhuapp.com/api/x"))
        with pytest.raises(LanhuAuthRequiredError):
            raise_for_lanhu_auth(response)

    def test_login_redirect_is_auth_failure(self):
        response = httpx.Response(
            302, headers={"location": "https://lanhuapp.com/login"},
            request=httpx.Request("GET", "https://lanhuapp.com/api/x"),
        )
        with pytest.raises(LanhuAuthRequiredError):
            raise_for_lanhu_auth(response)

    def test_plain_403_is_not_assumed_to_be_auth_failure(self):
        response = httpx.Response(403, request=httpx.Request("GET", "https://lanhuapp.com/api/x"))
        raise_for_lanhu_auth(response)  # no exception expected


# ---------------------------------------------------------------------------
# Credential precedence and resolution
# ---------------------------------------------------------------------------


def explicit_settings(cookie="session=explicit"):
    return get_settings(
        include_browser_fallback=False,
        lanhu_override=CookieInfo(True, cookie, "env", None, ["session"]),
    )


def missing_settings(tmp_path):
    return get_settings(
        include_browser_fallback=False,
        lanhu_override=CookieInfo(False, "", "missing", None, []),
    )


class TestCredentialPrecedence:
    @pytest.mark.asyncio
    async def test_explicit_beats_managed_and_legacy(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        service = DesignService(managed_auth=auth)
        service.settings = explicit_settings()
        resolved = await service._resolve_settings()
        assert resolved.lanhu_cookie == "session=explicit"
        auth.resolve_cookie.assert_not_called()

    @pytest.mark.asyncio
    async def test_managed_beats_legacy(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        auth.resolve_cookie.return_value = CookieInfo(True, "session=managed", "managed_browser", None, ["session"])
        service = DesignService(managed_auth=auth)
        service.settings = missing_settings(tmp_path)
        with patch("lanhu_design_mcp.design_service.resolve_legacy_browser_cookie") as legacy:
            resolved = await service._resolve_settings()
        assert resolved.lanhu_cookie_source == "managed_browser"
        legacy.assert_not_called()

    @pytest.mark.asyncio
    async def test_legacy_is_last_resort(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        auth.resolve_cookie.return_value = CookieInfo(False, "", "missing", None, [])
        service = DesignService(managed_auth=auth)
        service.settings = missing_settings(tmp_path)
        with patch("lanhu_design_mcp.design_service.resolve_legacy_browser_cookie",
                   return_value=CookieInfo(True, "session=legacy", "browser", None, ["session"])):
            resolved = await service._resolve_settings()
        assert resolved.lanhu_cookie_source == "browser"

    @pytest.mark.asyncio
    async def test_missing_all_raises_structured_error(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        auth.resolve_cookie.return_value = CookieInfo(False, "", "missing", None, [])
        service = DesignService(managed_auth=auth)
        service.settings = missing_settings(tmp_path)
        with patch("lanhu_design_mcp.design_service.resolve_legacy_browser_cookie",
                   return_value=CookieInfo(False, "", "missing", None, [])):
            with pytest.raises(LanhuAuthRequiredError):
                await service._resolve_settings()

    @pytest.mark.asyncio
    async def test_dds_explicit_still_wins(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        auth.resolve_cookie.return_value = CookieInfo(True, "session=managed", "managed_browser", None, ["session"])
        with patch.dict("os.environ", {"DDS_COOKIE": "session=dds_explicit"}, clear=False):
            service = DesignService(managed_auth=auth)
            service.settings = missing_settings(tmp_path)
            resolved = await service._resolve_settings()
        assert resolved.dds_cookie == "session=dds_explicit"
        assert resolved.dds_cookie_source == "env"


# ---------------------------------------------------------------------------
# Construction never calls legacy
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_construction_never_calls_legacy(self, monkeypatch):
        monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
        with patch("lanhu_design_mcp.design_service.resolve_legacy_browser_cookie") as legacy:
            DesignService()
        legacy.assert_not_called()


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


class TestInvalidation:
    @pytest.mark.asyncio
    async def test_managed_auth_rejection_invalidates_cache(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        auth.resolve_cookie.return_value = CookieInfo(True, "session=managed", "managed_browser", None, ["session"])
        auth.invalidate = Mock()
        service = DesignService(managed_auth=auth)
        service.settings = missing_settings(tmp_path)
        # Patch LanhuClient to raise auth error after settings are resolved
        with patch("lanhu_design_mcp.design_service.LanhuClient", side_effect=LanhuAuthRequiredError()):
            with pytest.raises(LanhuAuthRequiredError):
                await service.get_designs(URL)
        auth.invalidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_explicit_auth_rejection_does_not_invalidate(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        auth.invalidate = Mock()
        service = DesignService(managed_auth=auth)
        service.settings = explicit_settings()
        with patch("lanhu_design_mcp.design_service.LanhuClient", side_effect=LanhuAuthRequiredError()):
            with pytest.raises(LanhuAuthRequiredError):
                await service.get_designs(URL)
        auth.invalidate.assert_not_called()


# ---------------------------------------------------------------------------
# Asset auth not partial_success
# ---------------------------------------------------------------------------


class TestAssetAuthNotSwallowed:
    @pytest.mark.asyncio
    async def test_asset_auth_error_propagates_not_partial_success(self, tmp_path):
        auth = AsyncMock(spec=ManagedBrowserAuth)
        auth.resolve_cookie.return_value = CookieInfo(True, "session=x", "managed_browser", None, ["session"])
        service = DesignService(managed_auth=auth)
        service.settings = missing_settings(tmp_path)
        with patch("lanhu_design_mcp.design_service.LanhuClient", side_effect=LanhuAuthRequiredError()):
            with pytest.raises(LanhuAuthRequiredError):
                await service.get_design_assets(URL)
