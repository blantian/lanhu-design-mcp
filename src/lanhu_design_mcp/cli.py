"""CLI 入口：无参数启动 MCP 服务器；auth login|status|logout 管理托管 Chrome 认证。"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Sequence

from .auth.manager import get_managed_auth


def main(argv: Sequence[str] | None = None) -> int | None:
    """无参数启动服务器，auth 子命令管理托管 Chrome 登录。"""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        from .server import main as server_main
        server_main()
        return None

    cmd = argv[0]

    if cmd == "auth":
        return _auth_cmd(argv[1:])

    if cmd in ("-h", "--help"):
        print("Usage: lanhu-design-mcp [auth login|status|logout [--confirm]]")
        return 0

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


def _auth_cmd(argv: Sequence[str]) -> int:
    """将 auth 子命令分派到登录、状态或登出，并校验参数数量。"""
    if not argv:
        print("Usage: lanhu-design-mcp auth [login|status|logout]", file=sys.stderr)
        return 2

    sub = argv[0]
    rest = list(argv[1:])

    if sub == "login":
        if rest:
            print("Usage: lanhu-design-mcp auth login", file=sys.stderr)
            return 2
        return _run_async(_auth_login())
    elif sub == "status":
        if rest:
            print("Usage: lanhu-design-mcp auth status", file=sys.stderr)
            return 2
        return _run_async(_auth_status())
    elif sub == "logout":
        confs = [a for a in rest if a == "--confirm"]
        extras = [a for a in rest if a != "--confirm"]
        if extras or len(confs) > 1:
            print("Usage: lanhu-design-mcp auth logout [--confirm]", file=sys.stderr)
            return 2
        return _run_async(_auth_logout(bool(confs)))
    else:
        print(f"Unknown auth command: {sub}", file=sys.stderr)
        return 2


def _run_async(coro) -> int:
    """安全运行异步协程，失败时向 stderr 输出固定安全 JSON 并返回 1。"""
    try:
        return asyncio.run(coro)
    except Exception:
        print(
            json.dumps({"status": "failed", "message": "Authentication command failed."}),
            file=sys.stderr,
        )
        return 1


async def _auth_login() -> int:
    """启动可见登录、等待结束、输出状态 JSON；成功返回 0，否则 1。"""
    auth = get_managed_auth()
    await auth.start_login()
    await auth.wait_for_terminal_state()
    result = await auth.status(probe_profile=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("authenticated") else 1


async def _auth_status() -> int:
    """探测托管认证并打印安全状态 JSON；仅 authenticated 返回 0。"""
    auth = get_managed_auth()
    result = await auth.status(probe_profile=True)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("authenticated") else 1


async def _auth_logout(confirm: bool) -> int:
    """调用登出并打印结果 JSON；无 confirm 返回 1，成功登出返回 0。"""
    auth = get_managed_auth()
    result = await auth.logout(confirm)
    print(json.dumps(result, ensure_ascii=False))
    if not confirm:
        return 1
    return 0 if result.get("status") == "logged_out" else 1
