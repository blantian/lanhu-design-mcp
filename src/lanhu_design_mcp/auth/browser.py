"""浏览器适配器：会话与后端协议、Playwright 实现及生命周期管理。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .models import AuthDependencyError, AuthProfileLockedError


class BrowserSession(Protocol):
    """蓝湖：浏览器会话协议。"""

    async def cookies(self) -> list[dict[str, Any]]:
        """蓝湖：返回当前上下文的所有Cookie。"""
        ...

    def is_closed(self) -> bool:
        """蓝湖：窗口或上下文是否已关闭。"""
        ...

    async def close(self) -> None:
        """蓝湖：关闭上下文并停止驱动。"""
        ...


class BrowserBackend(Protocol):
    """蓝湖：浏览器后端协议。"""

    async def open(self, profile_dir: Path, *, headless: bool) -> BrowserSession:
        """蓝湖：使用指定Profile打开浏览器上下文。"""
        ...


class PlaywrightBrowserBackend:
    """通过Playwright和已安装系统Chrome操作真实浏览器。"""

    async def open(self, profile_dir: Path, *, headless: bool) -> BrowserSession:
        """启动持久化Chrome上下文；可见模式导航至lanhuapp.com。"""
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-untyped]
        except ImportError as exc:
            raise AuthDependencyError(
                "Install automatic login with: pip install --upgrade lanhu-design-mcp"
            ) from exc

        pw = None
        context = None
        page = None
        try:
            pw = await async_playwright().__aenter__()
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=headless,
            )
        except Exception as exc:
            if pw is not None:
                await pw.__aexit__(None, None, None)
            msg = str(exc).lower()
            if "executable" in msg and "chrome" in msg:
                raise AuthDependencyError("Google Chrome is required for automatic login.") from exc
            if "lock" in msg or "profile" in msg:
                raise AuthProfileLockedError("The managed browser profile is locked.") from exc
            raise

        if not headless:
            try:
                pages = context.pages
                page = pages[0] if pages else await context.new_page()
                await page.goto("https://lanhuapp.com/", wait_until="domcontentloaded")
            except Exception:
                try:
                    await context.close()
                except Exception:
                    pass
                await pw.__aexit__(None, None, None)
                raise

        class _PlaywrightSession:
            """封装BrowserContext和Playwright驱动的闭包会话。"""

            def __init__(self_):
                """注册上下文与页面的关闭事件回调以同步状态。"""
                self_._closed = False
                self_._driver_stopped = False

                def on_close(*args: Any) -> None:
                    """页面或上下文关闭事件回调，同步闭包状态标记。"""
                    self_._closed = True

                context.on("close", on_close)
                if page is not None:
                    page.on("close", on_close)

            async def cookies(self_):
                """返回当前浏览器上下文的所有Cookie列表。"""
                return await context.cookies()

            def is_closed(self_):
                """上下文是否已通过外部事件或主动关闭。"""
                return self_._closed

            async def close(self_):
                """关闭上下文并停止Playwright驱动，可安全重复调用。"""
                if self_._closed and self_._driver_stopped:
                    return
                self_._closed = True
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await pw.__aexit__(None, None, None)
                except Exception:
                    pass
                self_._driver_stopped = True

        return _PlaywrightSession()
