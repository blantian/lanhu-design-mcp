from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:
    pass


@dataclass(frozen=True)
class Settings:
    lanhu_cookie: str
    dds_cookie: str
    data_dir: Path
    http_timeout: float
    transport: str
    host: str
    port: int


def get_settings() -> Settings:
    lanhu_cookie = os.getenv("LANHU_COOKIE", "").strip()

    # 如果没有手动配置 Cookie，尝试自动从浏览器读取
    if not lanhu_cookie:
        auto_browser = os.getenv("AUTO_BROWSER_COOKIES", "true").lower()
        if auto_browser in ("true", "1", "yes"):
            try:
                from .browser_cookies import get_lanhu_cookies
                lanhu_cookie = get_lanhu_cookies()
            except Exception as e:
                # 自动获取失败，继续使用空字符串（后续会在 client 中抛出错误）
                import sys
                print(f"警告: 自动获取浏览器 Cookies 失败: {e}", file=sys.stderr)
                print("提示: 请在 .env 文件中手动配置 LANHU_COOKIE", file=sys.stderr)

    dds_cookie = os.getenv("DDS_COOKIE", "").strip() or lanhu_cookie
    return Settings(
        lanhu_cookie=lanhu_cookie,
        dds_cookie=dds_cookie,
        data_dir=Path(os.getenv("DATA_DIR", "./data")),
        http_timeout=float(os.getenv("HTTP_TIMEOUT", "30")),
        transport=os.getenv("MCP_TRANSPORT", "stdio").lower(),
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
    )
