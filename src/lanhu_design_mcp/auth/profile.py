"""Profile 路径解析、Cookie 过滤与格式化、Profile 生命周期保护。"""

from __future__ import annotations

import os
import platform
import shutil
import stat as stat_mod
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import UnsafeProfileError, UnsupportedPlatformError

LANHU_DOMAINS: set[str] = {"lanhuapp.com", ".lanhuapp.com", "dds.lanhuapp.com", ".dds.lanhuapp.com"}

PROFILE_MARKER = ".lanhu-design-mcp-profile"


def default_profile_dir(
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """返回macOS托管Profile目录；非Darwin抛出平台不支持错误。"""
    if system is None:
        system = platform.system()
    if system != "Darwin":
        raise UnsupportedPlatformError(
            "Managed Lanhu login is supported on macOS only."
        )
    if environ is None:
        environ = os.environ
    base = Path(environ.get("HOME", Path.home())) / "Library" / "Application Support"
    return base / "lanhu-design-mcp" / "browser-profile"


def _normalize_domain(raw: str) -> str:
    """规范化Cookie域名字符串：去空格、小写、去除末尾DNS点。"""
    domain = raw.strip().lower()
    if domain.endswith(".") and not domain.startswith("."):
        domain = domain[:-1]
    elif domain.startswith(".") and domain.endswith("."):
        domain = domain[:-1]
    return domain


def filter_lanhu_cookies(cookies: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """仅返回域名在LANHU_DOMAINS白名单中的Cookie。"""
    result: list[dict[str, Any]] = []
    for c in cookies:
        domain = str(c.get("domain") or "")
        if not domain.strip():
            continue
        if _normalize_domain(domain) in LANHU_DOMAINS:
            result.append(dict(c))
    return result


def format_cookie_header(cookies: Sequence[Mapping[str, Any]]) -> str:
    """将已过滤Cookie格式化为name=value请求头，按名称排序。"""
    if not cookies:
        return ""
    sorted_cookies = sorted(cookies, key=lambda c: str(c.get("name", "")))
    parts = [f'{c["name"]}={c["value"]}' for c in sorted_cookies]
    return "; ".join(parts)


def _is_default_chrome_profile(path: Path) -> bool:
    """判断路径是否为Chrome默认Profile目录。"""
    resolved = path.resolve()
    if resolved.name == "Default":
        return True
    parts = resolved.parts
    # 蓝湖：检测 /Google/Chrome/Default
    for i, part in enumerate(parts):
        if part == "Google" and i + 2 < len(parts):
            if parts[i + 1] == "Chrome" and parts[i + 2] == "Default":
                return True
    return False


def ensure_owned_profile(profile_dir: Path) -> None:
    """创建带包标记的Profile目录，设置POSIX 0700权限。"""
    if _is_default_chrome_profile(profile_dir):
        raise UnsafeProfileError(f"Refusing to use the default Chrome profile: {profile_dir}")

    profile_dir.mkdir(parents=True, exist_ok=True)
    marker = profile_dir / PROFILE_MARKER
    marker.touch()

    # 蓝湖：POSIX仅所有者（Windows跳过）
    if os.name != "nt":
        current = stat_mod.S_IMODE(profile_dir.stat().st_mode)
        if current != 0o700:
            os.chmod(profile_dir, 0o700)


def remove_owned_profile(profile_dir: Path) -> None:
    """仅当包标记直接存在时删除Profile，拒绝符号链接。"""
    resolved = profile_dir.resolve()
    if profile_dir.is_symlink():
        raise UnsafeProfileError(f"Refusing to follow symlink for profile removal: {profile_dir}")
    marker = resolved / PROFILE_MARKER
    if not marker.is_file():
        raise UnsafeProfileError(f"Profile directory is not owned by this package: {profile_dir}")
    shutil.rmtree(resolved)
