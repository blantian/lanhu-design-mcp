"""托管浏览器认证：协议、会话验证、Playwright 生命周期与状态机。"""

from __future__ import annotations

import asyncio
import platform
import uuid
from pathlib import Path
from typing import Any, Protocol

from .models import (
    AuthDependencyError,
    AuthProfileLockedError,
    AuthSnapshot,
    AuthStatus,
    CookieInfo,
    UnsafeProfileError,
)
from .profile import (
    PROFILE_MARKER,
    default_profile_dir,
    ensure_owned_profile,
    filter_lanhu_cookies,
    format_cookie_header,
    remove_owned_profile,
)

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


class SessionValidator(Protocol):
    """蓝湖：会话验证协议。"""

    async def validate(self, cookie_header: str) -> bool:
        """蓝湖：验证Cookie头是否有效。"""
        ...


# ---- 认证状态机与内部方法 ----
# 托管浏览器认证——异步状态机
# ---- 认证状态机与内部方法 ----

AUTH_COOKIE_NAMES = {"session", "user_token"}


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


class ManagedBrowserAuth:
    """拥有托管Chrome Profile登录状态机与生命周期。"""

    def __init__(
        self,
        *,
        backend: BrowserBackend | None = None,
        profile_dir: Path | None = None,
        timeout: float = 300,
        poll_interval: float = 1.0,
        session_validator: SessionValidator | None = None,
        system: str | None = None,
    ):
        """注入后端、Profile路径、超时、轮询、验证器与系统标识。"""
        self._backend_impl = backend
        self._profile_path = profile_dir
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._validator_impl = session_validator
        self._system = system
        self._state_lock = asyncio.Lock()
        self._browser_lock = asyncio.Lock()
        self._session_id: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._cached_header: str | None = None
        self._cached_names: list[str] = []
        self._state: AuthStatus = "missing"
        self._message: str | None = None

# ---- 认证状态机与内部方法 ----
# 内部辅助方法
# ---- 认证状态机与内部方法 ----

    def _is_supported_platform(self) -> bool:
        """判断当前进程是否运行在正式支持的macOS系统上。"""
        return (self._system or platform.system()) == "Darwin"

    @staticmethod
    def _safe_unsupported_platform_message() -> str:
        """返回不含本机细节的平台安全错误固定文本。"""
        return "Managed Lanhu login is supported on macOS only."

    def _reject_unsupported_platform(self) -> bool:
        """非Darwin设置固定失败状态并阻止后续浏览器操作。"""
        if self._is_supported_platform():
            return False
        self._state = "unsupported_platform"
        self._message = self._safe_unsupported_platform_message()
        return True

    def _resolve_profile(self) -> Path:
        """懒解析或返回已注入的托管Profile目录路径。"""
        if self._profile_path is None:
            self._profile_path = default_profile_dir()
        return self._profile_path

    def _resolve_backend(self) -> BrowserBackend:
        """懒解析或返回已注入的浏览器后端实例。"""
        if self._backend_impl is None:
            self._backend_impl = PlaywrightBrowserBackend()
        return self._backend_impl

    def _resolve_validator(self) -> SessionValidator:
        """懒解析或返回已注入的会话验证器实例。"""
        if self._validator_impl is None:
            self._validator_impl = HttpSessionValidator()
        return self._validator_impl

    def _snapshot(self) -> AuthSnapshot:
        """构建当前状态的安全AuthSnapshot快照。"""
        return AuthSnapshot(
            status=self._state,
            authenticated=self._state == "authenticated",
            source="managed_browser" if self._state == "authenticated" else self._state,
            cookie_names=list(self._cached_names),
            session_id=self._session_id,
            message=self._message,
        )

    def _has_auth_cookie(self, cookies: list[dict[str, Any]]) -> bool:
        """判断Cookie列表中是否包含有效session或user_token。"""
        allowed = filter_lanhu_cookies(cookies)
        return any(c["name"].lower() in AUTH_COOKIE_NAMES for c in allowed)

    @staticmethod
    def _safe_dependency_message() -> str:
        """依赖缺失时的固定安全提示文本。"""
        return "Automatic login dependencies are not available. Install with: pip install --upgrade lanhu-design-mcp"

    @staticmethod
    def _safe_profile_locked_message() -> str:
        """Profile被锁时的固定安全提示文本。"""
        return "The managed browser profile is locked by another process."

    @staticmethod
    def _safe_failure_message() -> str:
        """意外故障时的固定安全提示文本。"""
        return "An unexpected error occurred during login."

# ---- 认证状态机与内部方法 ----
# ---- 认证状态机与内部方法 ----
# ---- 认证状态机与内部方法 ----

    def status_now(self) -> dict[str, Any]:
        """返回当前认证状态的纯本地安全快照。"""
        return self._snapshot().to_dict()

    async def status(self, session_id: str | None = None, *, probe_profile: bool = False) -> dict[str, Any]:
        """报告状态；支持sessionId校验与Profile探测。"""
        if session_id is not None and session_id != self._session_id:
            return AuthSnapshot("missing", False, "missing", [], session_id=session_id).to_dict()
        if probe_profile and self._state == "missing" and not self._cached_header:
            await self.resolve_cookie()
        return self._snapshot().to_dict()

    async def start_login(self) -> dict[str, Any]:
        """非阻塞启动可见登录worker；幂等，返回sessionId。"""
        if self._reject_unsupported_platform():
            return self._snapshot().to_dict()
        async with self._state_lock:
            if self._task and not self._task.done():
                return self._snapshot().to_dict()
            self._session_id = uuid.uuid4().hex
            self._state = "starting"
            self._message = None
            self._task = asyncio.create_task(self._login_worker())
            await asyncio.sleep(0)
            return self._snapshot().to_dict()

    async def resolve_cookie(self) -> CookieInfo:
        """返回已验证CookieInfo：内存优先，其次无头Profile提取。"""
        if self._reject_unsupported_platform():
            return CookieInfo(False, "", "missing", [])
        if self._cached_header:
            return CookieInfo(True, self._cached_header, "managed_browser", list(self._cached_names))

        async with self._browser_lock:
            if self._cached_header:
                return CookieInfo(True, self._cached_header, "managed_browser", list(self._cached_names))

            profile = self._resolve_profile()
            if not (profile / PROFILE_MARKER).is_file():
                return CookieInfo(False, "", "missing", [])

            try:
                ensure_owned_profile(profile)
                session = await self._resolve_backend().open(profile, headless=True)
                try:
                    cookies = await session.cookies()
                finally:
                    await session.close()
            except AuthDependencyError:
                self._state = "dependency_missing"
                self._message = self._safe_dependency_message()
                return CookieInfo(False, "", "missing", [])
            except AuthProfileLockedError:
                self._state = "profile_locked"
                self._message = self._safe_profile_locked_message()
                return CookieInfo(False, "", "missing", [])
            except Exception:
                self._state = "failed"
                self._message = self._safe_failure_message()
                return CookieInfo(False, "", "missing", [])

            allowed = filter_lanhu_cookies(cookies)
            if not self._has_auth_cookie(cookies) or not allowed:
                return CookieInfo(False, "", "missing", [])

            header = format_cookie_header(allowed)
            try:
                if not await self._resolve_validator().validate(header):
                    return CookieInfo(False, "", "missing", [])
            except Exception:
                return CookieInfo(False, "", "missing", [])

            self._cached_header = header
            self._cached_names = [c["name"] for c in allowed]
            self._state = "authenticated"
            self._message = None
            return CookieInfo(True, header, "managed_browser", list(self._cached_names))

    def invalidate(self) -> None:
        """仅清除内存缓存；不触碰磁盘Profile。"""
        self._cached_header = None
        self._cached_names = []
        if self._state == "authenticated":
            self._state = "expired"

    async def logout(self, confirm: bool = False) -> dict[str, Any]:
        """取消worker、清除内存；confirm=true时删除拥有标记的Profile。"""
        if not confirm:
            return {"status": "confirmation_required", "message": "Set confirm=true to delete the managed profile."}

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._cached_header = None
        self._cached_names = []

        async with self._browser_lock:
            profile = self._resolve_profile()
            try:
                remove_owned_profile(profile)
            except UnsafeProfileError:
                pass

        self._state = "missing"
        self._session_id = None
        self._message = None
        return {"status": "logged_out"}

    async def wait_for_terminal_state(self) -> None:
        """等待后台登录worker进入终态。"""
        if self._task and not self._task.done():
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def shutdown(self) -> None:
        """取消worker并将状态重置为missing。"""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._state = "missing"

# ---- 认证状态机与内部方法 ----
# 内部登录worker
# ---- 认证状态机与内部方法 ----

    async def _login_worker(self) -> None:
        """打开可见Chrome、轮询Cookie、通过蓝湖账号端点验证并缓存会话头。"""
        session: BrowserSession | None = None
        try:
            profile = self._resolve_profile()
            ensure_owned_profile(profile)
            async with self._browser_lock:
                try:
                    session = await self._resolve_backend().open(profile, headless=False)
                    self._state = "waiting_for_user"
                    deadline = asyncio.get_event_loop().time() + self._timeout

                    while True:
                        remaining = deadline - asyncio.get_event_loop().time()
                        if remaining <= 0:
                            self._state = "timed_out"
                            self._message = "Login timed out."
                            return

                        try:
                            cookies = await asyncio.wait_for(session.cookies(), min(self._poll_interval, remaining))
                        except asyncio.TimeoutError:
                            continue

                        if session.is_closed():
                            self._state = "cancelled"
                            self._message = "Browser window was closed before login."
                            return

                        if self._has_auth_cookie(cookies):
                            allowed = filter_lanhu_cookies(cookies)
                            header = format_cookie_header(allowed)
                            try:
                                if await self._resolve_validator().validate(header):
                                    self._cached_header = header
                                    self._cached_names = [c["name"] for c in allowed]
                                    self._state = "authenticated"
                                    self._message = None
                                    return
                            except Exception:
                                pass  # 蓝湖：验证器错误——继续轮询
                            # 蓝湖：过期或否定——继续轮询

                        await asyncio.sleep(self._poll_interval)
                finally:
                    # 蓝湖：在持有锁期间始终调用close — even if externally
                    # 蓝湖：已关闭但驱动可能尚未停止
                    if session is not None:
                        try:
                            await session.close()
                        except Exception:
                            pass

        except AuthDependencyError:
            self._state = "dependency_missing"
            self._message = self._safe_dependency_message()
        except AuthProfileLockedError:
            self._state = "profile_locked"
            self._message = self._safe_profile_locked_message()
        except asyncio.CancelledError:
            self._state = "cancelled"
            self._message = "Login was cancelled."
        except Exception:
            self._state = "failed"
            self._message = self._safe_failure_message()


# ---- 认证状态机与内部方法 ----
# 进程级单例
# ---- 认证状态机与内部方法 ----

_managed_auth: ManagedBrowserAuth | None = None


def get_managed_auth() -> ManagedBrowserAuth:
    """返回进程级ManagedBrowserAuth单例。"""
    global _managed_auth
    if _managed_auth is None:
        _managed_auth = ManagedBrowserAuth()
    return _managed_auth
