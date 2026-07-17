"""Tests for LanhuClient asset source retrieval."""

from __future__ import annotations

import importlib.util

from pathlib import Path

from lanhu_design_mcp.client import LanhuClient
from lanhu_design_mcp.config import Settings


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
