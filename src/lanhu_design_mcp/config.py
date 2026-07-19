"""托管认证与蓝湖客户端的最小配置模型，只含 managed_browser 与 missing 两种来源。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CookieSource = Literal["managed_browser", "missing"]


@dataclass(frozen=True)
class CookieInfo:
    """托管浏览器解析出的会话头与安全诊断 Cookie 名称。"""

    configured: bool
    cookie: str
    source: CookieSource
    cookie_names: list[str]


@dataclass(frozen=True)
class Settings:
    """蓝湖 API 与 DDS 请求共享的客户端配置，DDS 复用托管 Cookie。"""

    lanhu_cookie: str
    dds_cookie: str
    http_timeout: float
    lanhu_cookie_source: CookieSource
    lanhu_cookie_names: list[str]


def settings_from_cookie(info: CookieInfo) -> Settings:
    """把已验证的托管会话转换为 LanhuClient 配置，DDS 复用同一 Cookie。"""
    return Settings(
        lanhu_cookie=info.cookie,
        dds_cookie=info.cookie,
        http_timeout=30.0,
        lanhu_cookie_source=info.source,
        lanhu_cookie_names=list(info.cookie_names),
    )
