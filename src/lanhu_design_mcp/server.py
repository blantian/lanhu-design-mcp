from __future__ import annotations

from typing import Annotated, Literal

from fastmcp import FastMCP

from .config import default_lanhu_cookie_file, get_settings
from .design_service import DesignService

TargetPlatformArg = Literal["web", "android", "ios", "wechat_miniprogram"]

mcp = FastMCP("Lanhu Design MCP")


@mcp.tool()
async def lanhu_health_check() -> dict:
    """Return local configuration status without accessing the network or exposing cookie values."""
    settings = get_settings()
    return {
        "configured": bool(settings.lanhu_cookie),
        "cookieSource": settings.lanhu_cookie_source,
        "cookieFile": str(settings.lanhu_cookie_file) if settings.lanhu_cookie_file else None,
        "cookieNames": settings.lanhu_cookie_names,
        "ddsCookieSource": settings.dds_cookie_source,
        "ddsCookieFile": str(settings.dds_cookie_file) if settings.dds_cookie_file else None,
        "ddsCookieNames": settings.dds_cookie_names,
        "defaultCookieFile": str(default_lanhu_cookie_file()),
        "sdk": "fastmcp",
        "tools": [
            "lanhu_health_check",
            "lanhu_get_designs",
            "lanhu_analyze_design",
            "lanhu_get_design_assets",
            "lanhu_export_ui_context",
        ],
    }


@mcp.tool()
async def lanhu_get_designs(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
) -> dict:
    """List Lanhu design images for a project."""
    return await DesignService().get_designs(url)


@mcp.tool()
async def lanhu_analyze_design(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """Analyze one Lanhu design and return platform-adjusted UI structure."""
    return await DesignService().analyze_design(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_get_design_assets(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """Return asset download mapping for a Lanhu design."""
    return await DesignService().get_design_assets(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_export_ui_context(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """Return complete Agent-facing context for UI restoration."""
    return await DesignService().export_ui_context(url, design_name_or_index, target_platform)


def main() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", path="/mcp", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
