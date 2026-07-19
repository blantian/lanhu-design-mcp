"""托管认证使用的数据模型、协议来源和安全错误。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CookieSource = Literal["managed_browser", "missing"]

AuthStatus = Literal[
    "missing",
    "starting",
    "waiting_for_user",
    "authenticated",
    "expired",
    "cancelled",
    "timed_out",
    "dependency_missing",
    "profile_locked",
    "unsupported_platform",
    "failed",
]


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


class UnsafeProfileError(RuntimeError):
    """对不安全目录操作抛出的错误，防止误删非托管Profile。"""


class UnsupportedPlatformError(RuntimeError):
    """当前运行平台不在正式支持范围内时抛出的错误。"""


class AuthDependencyError(RuntimeError):
    """所需可选依赖缺失时抛出的错误，附带安装指引。"""


class AuthProfileLockedError(RuntimeError):
    """托管浏览器Profile被其他进程锁定时抛出的错误。"""


@dataclass(frozen=True)
class AuthSnapshot:
    """可安全序列化的认证状态快照，不含Cookie值。"""

    status: AuthStatus
    authenticated: bool
    source: str
    cookie_names: list[str]
    session_id: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为不含任何凭据的安全字典。"""
        result: dict[str, Any] = {
            "status": self.status,
            "authenticated": self.authenticated,
            "source": self.source,
            "cookieNames": self.cookie_names,
            "sessionId": self.session_id,
        }
        if self.message:
            result["message"] = self.message
        return result
