"""会话验证：协议定义与基于蓝湖账号端点的 HTTP 验证器。"""

from __future__ import annotations

from typing import Protocol


class SessionValidator(Protocol):
    """蓝湖：会话验证协议。"""

    async def validate(self, cookie_header: str) -> bool:
        """蓝湖：验证Cookie头是否有效。"""
        ...


class HttpSessionValidator:
    """通过请求蓝湖账号端点验证Cookie头有效性。"""

    def __init__(self, timeout: float = 10.0) -> None:
        """使用可配置HTTP超时进行初始化。"""
        self._timeout = timeout

    async def validate(self, cookie_header: str) -> bool:
        """向蓝湖账号端点发送请求验证Cookie会话有效性。"""
        import httpx

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True,
            ) as client:
                response = await client.get(
                    "https://lanhuapp.com/api/account/user/detail",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Accept": "application/json, text/plain, */*",
                        "Referer": "https://lanhuapp.com/web/",
                        "request-from": "web",
                        "Cookie": cookie_header,
                    },
                )
        except Exception:
            return False

        # 蓝湖：仅2xx响应有资格进入正向分类
        if response.status_code < 200 or response.status_code >= 300:
            return False

        # 蓝湖：响应本身的认证失败证据
        if response.status_code in {401, 418}:
            return False
        location = response.headers.get("location", "")
        if response.is_redirect and "login" in location.lower():
            return False
        for h in response.history or ():
            loc = h.headers.get("location", "")
            if h.is_redirect and "login" in loc.lower():
                return False

        try:
            data = response.json()
        except Exception:
            return False

        if not isinstance(data, dict):
            return False

        # 蓝湖：显式成功契约——code=="00000"
        return data.get("code") == "00000"
