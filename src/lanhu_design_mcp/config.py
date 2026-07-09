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
