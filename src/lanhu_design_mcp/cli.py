"""CLI entry point for lanhu-design-mcp.

No-argument invocation starts the MCP server.  ``auth login|status|logout``
manage the local Chrome authentication profile.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Sequence

from .managed_auth import get_managed_auth


def main(argv: Sequence[str] | None = None) -> int | None:
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
    if not argv:
        print("Usage: lanhu-design-mcp auth [login|status|logout]", file=sys.stderr)
        return 2

    sub = argv[0]
    if sub == "login":
        return _run_async(_auth_login())
    elif sub == "status":
        return _run_async(_auth_status())
    elif sub == "logout":
        confirm = "--confirm" in argv
        return _run_async(_auth_logout(confirm))
    else:
        print(f"Unknown auth command: {sub}", file=sys.stderr)
        return 2


def _run_async(coro) -> int:
    try:
        return asyncio.run(coro)
    except Exception:
        return 1


async def _auth_login() -> int:
    auth = get_managed_auth()
    await auth.start_login()
    await auth.wait_for_terminal_state()
    result = await auth.status(probe_profile=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("authenticated") else 1


async def _auth_status() -> int:
    auth = get_managed_auth()
    result = await auth.status(probe_profile=True)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") in {"authenticated", "missing"} else 1


async def _auth_logout(confirm: bool) -> int:
    auth = get_managed_auth()
    result = await auth.logout(confirm)
    print(json.dumps(result, ensure_ascii=False))
    if not confirm:
        return 1
    return 0 if result.get("status") == "logged_out" else 1
