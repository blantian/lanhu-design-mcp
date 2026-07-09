from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TargetPlatform = Literal["web", "android", "ios", "wechat_miniprogram"]


@dataclass(frozen=True)
class PlatformSpec:
    name: TargetPlatform
    unit: str
    scale: float
    note: str


def get_platform_spec(platform: TargetPlatform, design_width: float = 1920.0) -> PlatformSpec:
    if platform == "web":
        return PlatformSpec("web", "px", 1.0, "Lanhu original Web annotation units.")
    if platform == "android":
        return PlatformSpec("android", "dp", 0.5, "Verified Lanhu rule: 1920x1080px -> 960x540dp.")
    if platform == "ios":
        return PlatformSpec("ios", "pt", 0.5, "Default Lanhu-like logical point conversion; verify per design team if needed.")
    if platform == "wechat_miniprogram":
        width = design_width or 1920.0
        return PlatformSpec("wechat_miniprogram", "rpx", 750.0 / width, "Mini Program width-based rpx conversion.")
    raise ValueError(f"Unsupported target platform: {platform}")


def convert_value(value: float | int | None, platform: TargetPlatform, design_width: float = 1920.0) -> float | None:
    if value is None:
        return None
    return round(float(value) * get_platform_spec(platform, design_width).scale, 4)


def convert_rect(rect: dict, platform: TargetPlatform, design_width: float = 1920.0) -> dict:
    return {
        key: convert_value(rect.get(key), platform, design_width)
        for key in ("x", "y", "width", "height")
        if rect.get(key) is not None
    }


def format_value(value: float | int | None, platform: TargetPlatform, design_width: float = 1920.0) -> str:
    converted = convert_value(value, platform, design_width)
    if converted is None:
        return ""
    unit = get_platform_spec(platform, design_width).unit
    if float(converted).is_integer():
        return f"{int(converted)}{unit}"
    return f"{converted}{unit}"
