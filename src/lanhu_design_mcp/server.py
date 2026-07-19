"""蓝湖。"""

from typing import Annotated, Literal

from fastmcp import FastMCP

from .design_service import DesignService
from .managed_auth import get_managed_auth

TargetPlatformArg = Literal["web", "android", "ios", "wechat_miniprogram"]

mcp = FastMCP("Lanhu Design MCP")


@mcp.tool()
async def lanhu_health_check() -> dict:
    """蓝湖：Return local configuration status without accessing the network or exposing cookie values."""
    return {
        "sdk": "fastmcp",
        "tools": [
            "lanhu_health_check",
            "lanhu_get_designs",
            "lanhu_analyze_design",
            "lanhu_get_design_assets",
            "lanhu_export_ui_context",
            "lanhu_auth_login",
            "lanhu_auth_status",
            "lanhu_auth_logout",
        ],
        "managedAuth": get_managed_auth().status_now(),
    }


@mcp.tool()
async def lanhu_get_designs(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
) -> dict:
    """蓝湖：List Lanhu design images for a project."""
    return await DesignService().get_designs(url)


@mcp.tool()
async def lanhu_analyze_design(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """蓝湖：Analyze one Lanhu design and return platform-adjusted UI structure."""
    return await DesignService().analyze_design(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_get_design_assets(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """蓝湖：Return the full design image and fine-grained downloadable slice assets."""
    return await DesignService().get_design_assets(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_export_ui_context(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """蓝湖：Return complete Agent-facing context for UI restoration."""
    return await DesignService().export_ui_context(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_auth_login() -> dict:
    """蓝湖：Open a dedicated Chrome profile for interactive Lanhu sign-in."""
    return await get_managed_auth().start_login()


@mcp.tool()
async def lanhu_auth_status(session_id: str | None = None) -> dict:
    """蓝湖：Report managed authentication state without exposing credentials."""
    return await get_managed_auth().status(session_id, probe_profile=True)


@mcp.tool()
async def lanhu_auth_logout(confirm: bool = False) -> dict:
    """蓝湖：Sign out and remove the managed browser profile (requires confirm=true)."""
    return await get_managed_auth().logout(confirm)


def main() -> None:
    """蓝湖：Start the FastMCP server in foreground stdio mode."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
