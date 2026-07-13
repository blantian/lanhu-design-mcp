from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:
    pass

CookieSource = Literal["file", "env", "browser", "lanhu", "missing"]


@dataclass(frozen=True)
class CookieInfo:
    configured: bool
    cookie: str
    source: CookieSource
    cookie_file: Path | None
    cookie_names: list[str]


def cookie_names_from_header(cookie: str) -> list[str]:
    names: list[str] = []
    for segment in cookie.split(";"):
        part = segment.strip()
        if "=" not in part:
            continue
        name = part.split("=", 1)[0].strip()
        if name:
            names.append(name)
    return names


def default_lanhu_cookie_file() -> Path:
    return Path.home() / ".config" / "cagent" / "lanhu" / "cookie.txt"


def _read_cookie_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def resolve_lanhu_cookie() -> CookieInfo:
    # 1. LANHU_COOKIE_FILE
    cookie_file_path = os.getenv("LANHU_COOKIE_FILE", "").strip()
    if cookie_file_path:
        p = Path(cookie_file_path)
        cookie = _read_cookie_file(p)
        if cookie:
            return CookieInfo(
                configured=True,
                cookie=cookie,
                source="file",
                cookie_file=p,
                cookie_names=cookie_names_from_header(cookie),
            )

    # 2. Default CAgent file
    default_file = default_lanhu_cookie_file()
    cookie = _read_cookie_file(default_file)
    if cookie:
        return CookieInfo(
            configured=True,
            cookie=cookie,
            source="file",
            cookie_file=default_file,
            cookie_names=cookie_names_from_header(cookie),
        )

    # 3. LANHU_COOKIE env var
    cookie = os.getenv("LANHU_COOKIE", "").strip()
    if cookie:
        return CookieInfo(
            configured=True,
            cookie=cookie,
            source="env",
            cookie_file=None,
            cookie_names=cookie_names_from_header(cookie),
        )

    # 4. Browser auto-cookie fallback
    auto_browser = os.getenv("AUTO_BROWSER_COOKIES", "false").lower()
    if auto_browser in ("true", "1", "yes"):
        try:
            from .browser_cookies import get_lanhu_cookies

            cookie = get_lanhu_cookies()
            if cookie:
                return CookieInfo(
                    configured=True,
                    cookie=cookie,
                    source="browser",
                    cookie_file=None,
                    cookie_names=cookie_names_from_header(cookie),
                )
        except Exception:
            import sys

            print(
                "警告: 自动获取浏览器 Cookies 失败",
                file=sys.stderr,
            )
            print(
                "提示: 请在 .env 文件中手动配置 LANHU_COOKIE 或设置 LANHU_COOKIE_FILE",
                file=sys.stderr,
            )

    # 5. Missing
    return CookieInfo(
        configured=False,
        cookie="",
        source="missing",
        cookie_file=None,
        cookie_names=[],
    )


def resolve_dds_cookie(lanhu_info: CookieInfo) -> CookieInfo:
    # 1. DDS_COOKIE_FILE
    cookie_file_path = os.getenv("DDS_COOKIE_FILE", "").strip()
    if cookie_file_path:
        p = Path(cookie_file_path)
        cookie = _read_cookie_file(p)
        if cookie:
            return CookieInfo(
                configured=True,
                cookie=cookie,
                source="file",
                cookie_file=p,
                cookie_names=cookie_names_from_header(cookie),
            )

    # 2. DDS_COOKIE env var
    cookie = os.getenv("DDS_COOKIE", "").strip()
    if cookie:
        return CookieInfo(
            configured=True,
            cookie=cookie,
            source="env",
            cookie_file=None,
            cookie_names=cookie_names_from_header(cookie),
        )

    # 3. Resolved Lanhu cookie
    return CookieInfo(
        configured=lanhu_info.configured,
        cookie=lanhu_info.cookie,
        source="lanhu",
        cookie_file=None,
        cookie_names=lanhu_info.cookie_names,
    )


@dataclass(frozen=True)
class Settings:
    lanhu_cookie: str
    dds_cookie: str
    data_dir: Path
    http_timeout: float
    transport: str
    host: str
    port: int
    lanhu_cookie_source: CookieSource
    lanhu_cookie_file: Path | None
    lanhu_cookie_names: list[str]
    dds_cookie_source: CookieSource
    dds_cookie_file: Path | None
    dds_cookie_names: list[str]


def get_settings() -> Settings:
    lanhu_info = resolve_lanhu_cookie()
    dds_info = resolve_dds_cookie(lanhu_info)

    return Settings(
        lanhu_cookie=lanhu_info.cookie,
        dds_cookie=dds_info.cookie,
        data_dir=Path(os.getenv("DATA_DIR", "./data")),
        http_timeout=float(os.getenv("HTTP_TIMEOUT", "30")),
        transport=os.getenv("MCP_TRANSPORT", "stdio").lower(),
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
        lanhu_cookie_source=lanhu_info.source,
        lanhu_cookie_file=lanhu_info.cookie_file,
        lanhu_cookie_names=lanhu_info.cookie_names,
        dds_cookie_source=dds_info.source,
        dds_cookie_file=dds_info.cookie_file,
        dds_cookie_names=dds_info.cookie_names,
    )
