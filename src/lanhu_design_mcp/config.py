"""Minimal settings model for managed Lanhu authentication results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CookieSource = Literal["managed_browser", "missing"]


@dataclass(frozen=True)
class CookieInfo:
    """Resolved session header and safe diagnostic names from the managed browser."""

    configured: bool
    cookie: str
    source: CookieSource
    cookie_names: list[str]


@dataclass(frozen=True)
class Settings:
    """Client configuration shared by Lanhu API and DDS requests."""

    lanhu_cookie: str
    dds_cookie: str
    http_timeout: float
    lanhu_cookie_source: CookieSource
    lanhu_cookie_names: list[str]


def settings_from_cookie(info: CookieInfo) -> Settings:
    """Convert a validated managed session into Lanhu client configuration."""
    return Settings(
        lanhu_cookie=info.cookie,
        dds_cookie=info.cookie,
        http_timeout=30.0,
        lanhu_cookie_source=info.source,
        lanhu_cookie_names=list(info.cookie_names),
    )
