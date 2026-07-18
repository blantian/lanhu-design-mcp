"""Tests for LanhuClient asset source retrieval and auth classification."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from lanhu_design_mcp.client import (
    LanhuAuthError,
    LanhuAuthRequiredError,
    LanhuClient,
    raise_for_lanhu_auth,
)
from lanhu_design_mcp.config import CookieInfo, Settings


def test_client_has_get_design_asset_source():
    """Contract test: LanhuClient must expose get_design_asset_source."""
    spec = importlib.util.find_spec("lanhu_design_mcp.client")
    assert spec is not None, "lanhu_design_mcp.client module is missing"

    import lanhu_design_mcp.client as client_mod

    assert hasattr(LanhuClient, "get_design_asset_source"), (
        "LanhuClient.get_design_asset_source is missing; "
        "add the stub before proceeding to behavior tests."
    )


# ---------------------------------------------------------------------------
# Behavior tests — asset source retrieval
# ---------------------------------------------------------------------------


from unittest.mock import AsyncMock, Mock

import pytest

from lanhu_design_mcp.url_parser import LanhuUrl


def settings() -> Settings:
    return Settings("session=test", "session=test", Path("data"), 30, "stdio", "127.0.0.1", 8000,
                    "env", None, ["session"], "lanhu", None, ["session"])


@pytest.mark.asyncio
async def test_get_design_asset_source_fetches_latest_json():
    client = LanhuClient(settings())
    client.get_sketch_json = AsyncMock(return_value={"versions": [{"version_info": "v2", "json_url": "https://cdn/source.json"}]})
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"sliceScale": 2, "info": []}
    client.client.get = AsyncMock(return_value=response)
    try:
        result = await client.get_design_asset_source(LanhuUrl("p1"), "i1")
    finally:
        await client.close()
    assert result == {"source": {"sliceScale": 2, "info": []}, "version": "v2", "json_url": "https://cdn/source.json"}


@pytest.mark.asyncio
async def test_get_design_asset_source_rejects_missing_json_url():
    client = LanhuClient(settings())
    client.get_sketch_json = AsyncMock(return_value={"versions": [{"version_info": "v2"}]})
    try:
        with pytest.raises(RuntimeError, match="missing json_url"):
            await client.get_design_asset_source(LanhuUrl("p1"), "i1")
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Auth classification — method-level tests
# ---------------------------------------------------------------------------


def _resp(status, url="https://lanhuapp.com/api/project/images", headers=None, history=None):
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("GET", url), history=history or [])


class TestEmptyCookieRaisesAuthRequired:
    def test_empty_cookie_construction_raises_auth_required(self):
        with pytest.raises(LanhuAuthRequiredError):
            LanhuClient(Settings("", "", Path("data"), 30, "stdio", "127.0.0.1", 8000,
                                 "missing", None, [], "missing", None, []))

    def test_empty_cookie_error_has_safe_payload(self):
        try:
            LanhuClient(Settings("", "", Path("data"), 30, "stdio", "127.0.0.1", 8000,
                                 "missing", None, [], "missing", None, []))
        except LanhuAuthRequiredError as exc:
            d = exc.to_dict()
            assert d == {"status": "auth_required", "nextAction": "lanhu_auth_login"}


class TestMethodAuthClassification:
    """Each Lanhu/DDS API method calls raise_for_lanhu_auth before raise_for_status."""

    @pytest.mark.asyncio
    async def test_get_designs_401_raises_auth_required(self):
        client = LanhuClient(settings())
        client.client.get = AsyncMock(return_value=_resp(401))
        with pytest.raises(LanhuAuthRequiredError):
            await client.get_designs(LanhuUrl("p1"))

    @pytest.mark.asyncio
    async def test_get_version_id_418_raises_auth_required(self):
        client = LanhuClient(settings())
        client.client.get = AsyncMock(return_value=_resp(418, "https://lanhuapp.com/api/project/multi_info"))
        with pytest.raises(LanhuAuthRequiredError):
            await client.get_version_id(LanhuUrl("p1"), "i1")

    @pytest.mark.asyncio
    async def test_get_sketch_json_401_raises_auth_required(self):
        client = LanhuClient(settings())
        client.client.get = AsyncMock(return_value=_resp(401, "https://lanhuapp.com/api/project/image"))
        with pytest.raises(LanhuAuthRequiredError):
            await client.get_sketch_json(LanhuUrl("p1"), "i1")

    @pytest.mark.asyncio
    async def test_plain_403_is_still_http_error(self):
        client = LanhuClient(settings())
        client.client.get = AsyncMock(return_value=_resp(403))
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_designs(LanhuUrl("p1"))


class TestRedirectAuthDetection:
    """Redirect history with login Location is auth failure."""

    @pytest.mark.parametrize("status", [301, 302, 307])
    def test_redirect_to_login_location_is_auth_failure(self, status):
        r = httpx.Response(
            status,
            headers={"Location": "https://lanhuapp.com/login?redirect=/"},
            request=httpx.Request("GET", "https://lanhuapp.com/api/x"),
        )
        with pytest.raises(LanhuAuthRequiredError):
            raise_for_lanhu_auth(r)

    def test_followed_redirect_final_200_no_history_is_not_auth_failure(self):
        r = _resp(200, history=[])
        raise_for_lanhu_auth(r)  # no exception

    def test_followed_redirect_with_login_in_history_is_auth_failure(self):
        redirect = httpx.Response(
            302,
            headers={"Location": "https://lanhuapp.com/login"},
            request=httpx.Request("GET", "https://lanhuapp.com/api/x"),
        )
        final = _resp(200, history=[redirect])
        with pytest.raises(LanhuAuthRequiredError):
            raise_for_lanhu_auth(final)


# ---------------------------------------------------------------------------
# DesignService integration: managed cookie + 418 -> invalidate
# ---------------------------------------------------------------------------


class TestDesignServiceAuthIntegration:
    @pytest.mark.asyncio
    async def test_managed_cookie_418_triggers_invalidation(self, tmp_path):
        from lanhu_design_mcp.design_service import DesignService

        auth = AsyncMock()
        auth.resolve_cookie.return_value = CookieInfo(True, "session=managed", "managed_browser", None, ["session"])
        auth.invalidate = Mock()

        service = DesignService(managed_auth=auth)
        from lanhu_design_mcp.config import get_settings
        service.settings = get_settings(
            include_browser_fallback=False,
            lanhu_override=CookieInfo(False, "", "missing", None, []),
        )

        # Let _resolve_settings work, but make LanhuClient raise auth error
        with patch("lanhu_design_mcp.design_service.LanhuClient") as mock_client_cls:
            mock_client_cls.side_effect = LanhuAuthRequiredError()
            with pytest.raises(LanhuAuthRequiredError):
                await service.get_designs("https://lanhuapp.com/web/#/item/project/stage?pid=p1")

        auth.invalidate.assert_called_once()
