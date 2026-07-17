"""Tests for DesignService fine-grained asset integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from lanhu_design_mcp.design_service import DesignService

URL = "https://lanhuapp.com/web/#/item/project/stage?pid=p1&image_id=i1"
DESIGNS = {"status": "success", "project_id": "p1", "project_name": "Demo", "designs": [
    {"index": 1, "id": "i1", "name": "Home", "url": "https://cdn/design.png?query=1"}
]}


@pytest.mark.asyncio
async def test_get_design_assets_combines_full_image_and_slices(monkeypatch):
    client = AsyncMock()
    client.get_designs.return_value = DESIGNS
    client.get_design_asset_source.return_value = {
        "version": "v2", "json_url": "https://cdn/source.json",
        "source": {"sliceScale": 2, "info": [{
            "id": "s1", "name": "Icon", "type": "slice",
            "image": {"imageUrl": "https://cdn/icon.png", "size": {"width": 16, "height": 16}},
        }]},
    }
    context = AsyncMock()
    context.__aenter__.return_value = client
    context.__aexit__.return_value = None
    with patch("lanhu_design_mcp.design_service.LanhuClient", return_value=context):
        result = await DesignService().get_design_assets(URL)
    assert result["status"] == "success"
    assert result["slice_scale"] == 2
    assert result["total_assets"] == 2
    assert result["total_slices"] == 1
    assert [item["kind"] for item in result["assets"]] == ["design_image", "slice"]
    assert result["assets"][0]["remote_url"] == "https://cdn/design.png"


@pytest.mark.asyncio
async def test_get_design_assets_returns_partial_success_when_source_fails():
    client = AsyncMock()
    client.get_designs.return_value = DESIGNS
    client.get_design_asset_source.side_effect = RuntimeError("missing json_url")
    context = AsyncMock()
    context.__aenter__.return_value = client
    context.__aexit__.return_value = None
    with patch("lanhu_design_mcp.design_service.LanhuClient", return_value=context):
        result = await DesignService().get_design_assets(URL)
    assert result["status"] == "partial_success"
    assert result["total_assets"] == 1
    assert result["total_slices"] == 0
    assert result["warnings"] == ["Fine-grained assets unavailable: missing json_url"]


@pytest.mark.asyncio
async def test_get_design_assets_succeeds_when_design_has_no_slices():
    client = AsyncMock()
    client.get_designs.return_value = DESIGNS
    client.get_design_asset_source.return_value = {
        "version": "v2", "json_url": "https://cdn/source.json", "source": {"sliceScale": 2, "info": []}
    }
    context = AsyncMock()
    context.__aenter__.return_value = client
    context.__aexit__.return_value = None
    with patch("lanhu_design_mcp.design_service.LanhuClient", return_value=context):
        result = await DesignService().get_design_assets(URL)
    assert result["status"] == "success"
    assert result["total_assets"] == 1
    assert result["total_slices"] == 0
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_get_design_assets_avoids_full_image_slice_path_collision():
    client = AsyncMock()
    client.get_designs.return_value = DESIGNS
    client.get_design_asset_source.return_value = {
        "version": "v2", "json_url": "https://cdn/source.json",
        "source": {"info": [{
            "id": "same-name", "name": "Home",
            "image": {"imageUrl": "https://cdn/home-slice.png", "size": {"width": 16, "height": 16}},
        }]},
    }
    context = AsyncMock()
    context.__aenter__.return_value = client
    context.__aexit__.return_value = None
    with patch("lanhu_design_mcp.design_service.LanhuClient", return_value=context):
        result = await DesignService().get_design_assets(URL)
    assert result["assets"][0]["suggested_local_path"].endswith("/Home.png")
    assert result["assets"][1]["suggested_local_path"].endswith("/Home_2.png")


@pytest.mark.asyncio
async def test_export_ui_context_propagates_enhanced_assets():
    service = DesignService()
    service.analyze_design = AsyncMock(return_value={"status": "success", "design": {"id": "i1"}})
    expected_assets = [{"kind": "design_image"}, {"kind": "slice", "id": "s1"}]
    service.get_design_assets = AsyncMock(return_value={"assets": expected_assets})
    result = await service.export_ui_context(URL)
    assert result["assets"] == expected_assets
