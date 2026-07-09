from __future__ import annotations

from typing import Any

from .client import LanhuClient
from .config import get_settings
from .design_ir import summarize_schema
from .platform_units import TargetPlatform
from .url_parser import LanhuUrl, parse_lanhu_url


def resolve_design(designs: list[dict[str, Any]], ref: LanhuUrl, selector: str | int | None) -> dict[str, Any]:
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
    def __init__(self):
        self.settings = get_settings()

    async def get_designs(self, url: str) -> dict[str, Any]:
        ref = parse_lanhu_url(url)
        async with LanhuClient(self.settings) as client:
            return await client.get_designs(ref)

    async def analyze_design(
        self,
        url: str,
        design_name_or_index: str | int | None = None,
        target_platform: TargetPlatform = "android",
    ) -> dict[str, Any]:
        ref = parse_lanhu_url(url)
        async with LanhuClient(self.settings) as client:
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
        analysis = await self.analyze_design(url, design_name_or_index, target_platform)
        design = analysis["design"]
        original_url = (design.get("url") or "").split("?", 1)[0]
        return {
            "status": "success",
            "project": analysis["project"],
            "design": design,
            "target_platform": target_platform,
            "assets": [
                {
                    "kind": "design_image",
                    "name": f"{design.get('name')}.png",
                    "remote_url": original_url,
                    "suggested_local_path": f"assets/lanhu/{design.get('id')}/{design.get('name')}.png",
                }
            ],
            "note": "Fine-grained slice export will be added after the compact DesignIR MVP is verified.",
        }

    async def export_ui_context(
        self,
        url: str,
        design_name_or_index: str | int | None = None,
        target_platform: TargetPlatform = "android",
    ) -> dict[str, Any]:
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
