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


def _frame(obj: dict[str, Any]) -> dict[str, Any]:
    for key in ("frame", "bounds", "layerOriginFrame", "ddsOriginFrame"):
        value = obj.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _metadata(obj: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if obj.get("fills"): result["fills"] = obj["fills"]
    if obj.get("borders") or obj.get("strokes"): result["borders"] = obj.get("borders") or obj.get("strokes")
    if "opacity" in obj: result["opacity"] = obj["opacity"]
    if obj.get("rotation"): result["rotation"] = obj["rotation"]
    if obj.get("textStyle"): result["text_style"] = obj["textStyle"]
    if obj.get("shadows"): result["shadows"] = obj["shadows"]
    if obj.get("radius") or obj.get("cornerRadius"): result["border_radius"] = obj.get("radius") or obj.get("cornerRadius")
    return result


def _normalized_slice(
    obj: dict[str, Any], image: dict[str, Any], slice_scale: int,
    parent_name: str, layer_path: str, include_metadata: bool,
) -> dict[str, Any] | None:
    png_url = image.get("imageUrl")
    svg_url = image.get("svgUrl")
    remote_url = png_url or svg_url
    if not remote_url:
        return None
    frame = _frame(obj)
    image_size = image.get("size") if isinstance(image.get("size"), dict) else {}
    width = _number(image_size.get("width") or frame.get("width"))
    height = _number(image_size.get("height") or frame.get("height"))
    asset: dict[str, Any] = {
        "kind": "slice", "id": obj.get("id"), "name": obj.get("name") or "slice",
        "type": obj.get("type") or obj.get("layerType") or obj.get("ddsType") or "bitmap",
        "format": "png" if png_url else "svg", "remote_url": remote_url,
        "layer_path": layer_path,
    }
    if svg_url and png_url: asset["svg_url"] = svg_url
    if png_url and width and height:
        asset["scale_urls"] = build_scale_urls(png_url, width, height, slice_scale)
    if width and height:
        asset["logical_size"] = {"width": int(round(width)), "height": int(round(height))}
    x = frame.get("x", frame.get("left", obj.get("left")))
    y = frame.get("y", frame.get("top", obj.get("top")))
    if x is not None and y is not None:
        asset["position_px"] = {"x": int(round(_number(x))), "y": int(round(_number(y)))}
    if parent_name: asset["parent_name"] = parent_name
    metadata = _metadata(obj) if include_metadata else {}
    if metadata: asset["metadata"] = metadata
    return asset


def extract_design_slices(source: dict[str, Any], design_id: str, include_metadata: bool = True) -> dict[str, Any]:
    meta = source.get("meta") if isinstance(source.get("meta"), dict) else {}
    slice_scale = int(source.get("sliceScale") or source.get("exportScale") or meta.get("sliceScale") or 2)
    is_figma = ((meta.get("host") or {}).get("name") or "").lower() == "figma"
    slices: list[dict[str, Any]] = []
    warnings: list[str] = []
    skipped_candidates = 0
    flat_names = {
        item.get("id"): str(item.get("name") or "")
        for item in source.get("info") or []
        if isinstance(item, dict) and item.get("id") is not None
    }

    def visit(obj: dict[str, Any], parent_name: str = "", parent_path: str = "") -> None:
        nonlocal skipped_candidates
        name = str(obj.get("name") or "")
        path = f"{parent_path}/{name}" if parent_path and name else name or parent_path
        resolved_parent = parent_name or flat_names.get(obj.get("parentID"), "")
        image = obj.get("image") if isinstance(obj.get("image"), dict) else None
        if image and (not is_figma or obj.get("hasExportImage") is True):
            asset = _normalized_slice(obj, image, slice_scale, resolved_parent, path, include_metadata)
            if asset:
                slices.append(asset)
            else:
                skipped_candidates += 1
        elif not is_figma and isinstance(obj.get("ddsImage"), dict):
            asset = _normalized_slice(obj, obj["ddsImage"], slice_scale, resolved_parent, path, include_metadata)
            if asset:
                slices.append(asset)
            else:
                skipped_candidates += 1
        elif "image" in obj and not isinstance(obj.get("image"), dict):
            skipped_candidates += 1
        for key in ("layers", "children"):
            for child in obj.get(key) or []:
                if isinstance(child, dict): visit(child, name or resolved_parent, path)

    artboard = source.get("artboard") if isinstance(source.get("artboard"), dict) else {}
    roots = (artboard.get("layers") or []) if artboard else (source.get("info") or [])
    for root in roots:
        if isinstance(root, dict): visit(root)
    if skipped_candidates:
        warnings.append(f"Skipped {skipped_candidates} malformed slice candidate(s)")
    assign_suggested_paths(slices, design_id)
    return {"slice_scale": slice_scale, "total_slices": len(slices), "slices": slices, "warnings": warnings}
