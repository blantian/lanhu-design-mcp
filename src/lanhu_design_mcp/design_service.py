"""蓝湖。"""

from contextlib import asynccontextmanager
from typing import Any

import httpx

from .client import LanhuAuthRequiredError, LanhuClient
from .config import settings_from_cookie
from .design_assets import assign_suggested_paths, extract_design_slices, sanitize_asset_name
from .design_ir import summarize_schema
from .platform_units import TargetPlatform
from .url_parser import LanhuUrl, parse_lanhu_url


def resolve_design(designs: list[dict[str, Any]], ref: LanhuUrl, selector: str | int | None) -> dict[str, Any]:
    """蓝湖。"""
    if selector is None and ref.image_id:
        selector = ref.image_id
    if selector is None:
        if len(designs) == 1:
            return designs[0]
        raise ValueError("design_name_or_index is required when URL does not contain image_id")

    selector_text = str(selector).strip()
    if selector_text.isdigit():
        index = int(selector_text)
        for design in designs:
            if design.get("index") == index:
                return design
    for design in designs:
        if selector_text in {str(design.get("id")), str(design.get("name"))}:
            return design
    matches = [design for design in designs if selector_text and selector_text in str(design.get("name"))]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"Design not found: {selector_text}")


class DesignService:
    """蓝湖。"""
    def __init__(self, managed_auth=None):
        """蓝湖。"""
        self.managed_auth = managed_auth  # 蓝湖：测试注入点，生产环境延迟加载

    # ------------------------------------------------------------------ 蓝湖
# 异步凭证解析
    # ------------------------------------------------------------------ 蓝湖

    async def _resolve_settings(self):
        """蓝湖。"""
        if self.managed_auth is None:
            from .managed_auth import get_managed_auth
            self.managed_auth = get_managed_auth()
        info = await self.managed_auth.resolve_cookie()
        if not info.configured:
            raise LanhuAuthRequiredError()
        return settings_from_cookie(info)

    @asynccontextmanager
    async def _client(self):
        """蓝湖。"""
        settings = await self._resolve_settings()
        try:
            async with LanhuClient(settings) as client:
                yield client
        except LanhuAuthRequiredError:
            if settings.lanhu_cookie_source == "managed_browser" and self.managed_auth is not None:
                self.managed_auth.invalidate()
            raise

    # ------------------------------------------------------------------ 蓝湖
# 公开操作——全部通过_client()路由
    # ------------------------------------------------------------------ 蓝湖

    async def get_designs(self, url: str) -> dict[str, Any]:
        """蓝湖。"""
        ref = parse_lanhu_url(url)
        async with self._client() as client:
            return await client.get_designs(ref)

    async def analyze_design(
        self,
        url: str,
        design_name_or_index: str | int | None = None,
        target_platform: TargetPlatform = "android",
    ) -> dict[str, Any]:
        """蓝湖。"""
        ref = parse_lanhu_url(url)
        async with self._client() as client:
            design_data = await client.get_designs(ref)
            design = resolve_design(design_data["designs"], ref, design_name_or_index)
            schema = await client.get_design_schema(ref, design["id"])
        summary = summarize_schema(schema, target_platform)
        return {
            "status": "success",
            "project": {
                "id": ref.project_id,
                "name": design_data.get("project_name"),
            },
            "design": design,
            "spec": summary,
            "implementation_guidance": {
                "priority": "Use structured rect/styles first; use image only for visual verification.",
                "android": "For Android TV, treat dp values as the primary layout numbers. Preserve focusable card bounds and image assets.",
                "assets": "Download remote Lanhu assets into the target app; generated UI code should not depend on remote Lanhu URLs.",
            },
        }

    async def get_design_assets(
        self,
        url: str,
        design_name_or_index: str | int | None = None,
        target_platform: TargetPlatform = "android",
    ) -> dict[str, Any]:
        """蓝湖。"""
        ref = parse_lanhu_url(url)
        warnings: list[str] = []
        async with self._client() as client:
            design_data = await client.get_designs(ref)
            design = resolve_design(design_data["designs"], ref, design_name_or_index)
            design_name = sanitize_asset_name(str(design.get("name") or "design"), "design")
            design_asset = {
                "kind": "design_image",
                "name": design_name,
                "format": "png",
                "remote_url": (design.get("url") or "").split("?", 1)[0],
            }
            try:
                source_data = await client.get_design_asset_source(ref, design["id"])
                extracted = extract_design_slices(source_data["source"], str(design["id"]))
                slices = extracted["slices"]
                warnings.extend(extracted["warnings"])
                slice_scale = extracted["slice_scale"]
                version = source_data.get("version")
                status = "success"
            except LanhuAuthRequiredError:
                raise
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
                slices, slice_scale, version = [], None, None
                warnings.append(f"Fine-grained assets unavailable: {exc}")
                status = "partial_success"

        assets = [design_asset, *slices]
        assign_suggested_paths(assets, str(design["id"]))
        design_asset["name"] = f"{design_name}.png"
        design_asset.pop("format")
        return {
            "status": status,
            "project": {"id": ref.project_id, "name": design_data.get("project_name")},
            "design": design,
            "target_platform": target_platform,
            "version": version,
            "slice_scale": slice_scale,
            "total_assets": len(assets),
            "total_slices": len(slices),
            "assets": assets,
            "warnings": warnings,
        }

    async def export_ui_context(
        self,
        url: str,
        design_name_or_index: str | int | None = None,
        target_platform: TargetPlatform = "android",
    ) -> dict[str, Any]:
        """蓝湖。"""
        analysis = await self.analyze_design(url, design_name_or_index, target_platform)
        assets = await self.get_design_assets(url, design_name_or_index, target_platform)
        return {
            **analysis,
            "assets": assets["assets"],
            "agent_prompt": (
                "Implement this Lanhu design in the target project. Use the platform rect values and styles as the source of truth. "
                "For Android, map width/height/x/y to dp, font px to sp only when implementing text, and preserve local image assets."
            ),
        }
