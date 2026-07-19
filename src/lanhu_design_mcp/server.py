"""FastMCP 服务器：八个设计/认证工具与 stdio 启动入口。"""

from __future__ import annotations

from typing import Annotated, Literal

from fastmcp import FastMCP

from .design_service import DesignService
from .auth.manager import get_managed_auth

TargetPlatformArg = Literal["web", "android", "ios", "wechat_miniprogram"]

mcp = FastMCP("Lanhu Design MCP")


@mcp.tool()
async def lanhu_health_check() -> dict:
    """返回本地配置状态，不访问网络且不暴露 Cookie 值。"""
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
    """获取项目的所有设计图列表。"""
    return await DesignService().get_designs(url)


@mcp.tool()
async def lanhu_analyze_design(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """分析指定设计稿并返回平台调整后的 UI 结构。"""
    return await DesignService().analyze_design(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_get_design_assets(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """返回完整设计图与细粒度可下载切图资源。"""
    return await DesignService().get_design_assets(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_export_ui_context(
    url: Annotated[str, "Lanhu stage/detailDetach design URL."],
    design_name_or_index: Annotated[str | None, "Design exact name, list index, image_id, or omitted when URL contains image_id."] = None,
    target_platform: Annotated[TargetPlatformArg, "Output platform: web/android/ios/wechat_miniprogram."] = "android",
) -> dict:
    """返回包含资产和分析的完整 Agent UI 还原上下文。"""
    return await DesignService().export_ui_context(url, design_name_or_index, target_platform)


@mcp.tool()
async def lanhu_auth_login() -> dict:
    """打开专属 Chrome Profile 进行交互式 Lanhu 登录。"""
    return await get_managed_auth().start_login()


@mcp.tool()
async def lanhu_auth_status(session_id: str | None = None) -> dict:
    """报告托管认证状态，不含凭据信息。"""
    return await get_managed_auth().status(session_id, probe_profile=True)


@mcp.tool()
async def lanhu_auth_logout(confirm: bool = False) -> dict:
    """登出并删除托管 Profile，需要 confirm=true 确认。"""
    return await get_managed_auth().logout(confirm)


def main() -> None:
    """以前台 stdio 方式启动 FastMCP 服务器。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
