from __future__ import annotations

import math
import re
from typing import Any


def _js_round(value: float) -> int:
    return math.floor(value + 0.5)


def _resize_url(image_url: str, width: int, height: int) -> str:
    return f"{image_url}?x-oss-process=image/resize,w_{max(1, width)},h_{max(1, height)}/format,png"


def build_scale_urls(image_url: str, logical_width: float, logical_height: float, slice_scale: int) -> dict[str, str]:
    if not image_url or not logical_width or not logical_height:
        return {}
    width = max(1, int(round(logical_width)))
    height = max(1, int(round(logical_height)))
    scale = max(1, int(slice_scale or 2))
    stored_width = width * scale
    stored_height = height * scale

    def make_url(output_width: int, output_height: int) -> str:
        output_width = max(1, output_width)
        output_height = max(1, output_height)
        if output_width == stored_width and output_height == stored_height:
            return image_url
        return _resize_url(image_url, output_width, output_height)

    ios_base_width = stored_width / 4
    ios_base_height = stored_height / 4
    return {
        "1x": make_url(width, height),
        "2x": make_url(width * 2, height * 2),
        "3x": make_url(width * 3, height * 3),
        "ios_1x": make_url(_js_round(ios_base_width), _js_round(ios_base_height)),
        "ios_2x": make_url(_js_round(ios_base_width * 2), _js_round(ios_base_height * 2)),
        "ios_3x": make_url(_js_round(ios_base_width * 3), _js_round(ios_base_height * 3)),
        "android_mdpi": make_url(_js_round(stored_width / 4), _js_round(stored_height / 4)),
        "android_hdpi": make_url(_js_round(stored_width / 4 * 1.5), _js_round(stored_height / 4 * 1.5)),
        "android_xhdpi": make_url(_js_round(stored_width / 4 * 2), _js_round(stored_height / 4 * 2)),
        "android_xxhdpi": make_url(_js_round(stored_width / 4 * 3), _js_round(stored_height / 4 * 3)),
        "android_xxxhdpi": make_url(stored_width, stored_height),
    }


def build_ps_scale_urls(image_url: str, base_width: float, base_height: float) -> dict[str, str]:
    if not image_url or not base_width or not base_height:
        return {}
    width = max(1, int(round(base_width)))
    height = max(1, int(round(base_height)))
    one_width = width / 2
    one_height = height / 2

    def make(multiplier: float) -> str:
        return _resize_url(image_url, _js_round(one_width * multiplier), _js_round(one_height * multiplier))

    return {
        "1x": make(1), "2x": make(2), "3x": make(3),
        "ios_1x": make(1), "ios_2x": make(2), "ios_3x": make(3),
        "android_mdpi": make(1), "android_hdpi": make(1.5),
        "android_xhdpi": make(2), "android_xxhdpi": make(3), "android_xxxhdpi": make(4),
    }


def sanitize_asset_name(name: str, fallback: str = "slice") -> str:
    clean = re.sub(r"[\\/\x00-\x1f\x7f]+", "_", str(name or "")).strip(" ._")
    clean = clean.replace("..", "_").strip(" ._")
    return clean or fallback


def assign_suggested_paths(assets: list[dict[str, Any]], design_id: str) -> None:
    counts: dict[str, int] = {}
    for asset in assets:
        stem = sanitize_asset_name(asset.get("name") or "slice")
        extension = "svg" if asset.get("format") == "svg" else "png"
        counts[stem] = counts.get(stem, 0) + 1
        suffix = "" if counts[stem] == 1 else f"_{counts[stem]}"
        asset["suggested_local_path"] = f"assets/lanhu/{design_id}/{stem}{suffix}.{extension}"
