from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .platform_units import TargetPlatform, convert_rect, get_platform_spec


@dataclass
class DesignNode:
    id: str | None
    name: str
    type: str
    text: str | None = None
    rect_px: dict[str, float] = field(default_factory=dict)
    rect_platform: dict[str, float] = field(default_factory=dict)
    styles: dict[str, Any] = field(default_factory=dict)
    children: list["DesignNode"] = field(default_factory=list)


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("px", ""))
        except ValueError:
            return None
    return None


def _style(node: dict[str, Any]) -> dict[str, Any]:
    style = node.get("style")
    return style if isinstance(style, dict) else {}


def _rect_from_style(style: dict[str, Any]) -> dict[str, float]:
    aliases = {
        "x": ("x", "left"),
        "y": ("y", "top"),
        "width": ("width", "w"),
        "height": ("height", "h"),
    }
    rect: dict[str, float] = {}
    for key, candidates in aliases.items():
        for candidate in candidates:
            value = _number(style.get(candidate))
            if value is not None:
                rect[key] = value
                break
    return rect


def _text_from_node(node: dict[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, dict):
        for key in ("text", "content", "value"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    props = node.get("props")
    if isinstance(props, dict):
        value = props.get("text") or props.get("children")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _interesting_styles(style: dict[str, Any]) -> dict[str, Any]:
    wanted = (
        "background",
        "backgroundColor",
        "backgroundImage",
        "color",
        "fontSize",
        "fontFamily",
        "fontWeight",
        "lineHeight",
        "borderRadius",
        "border",
        "opacity",
        "boxShadow",
        "overflow",
    )
    return {key: style[key] for key in wanted if key in style}


def build_design_node(
    raw: dict[str, Any],
    platform: TargetPlatform = "android",
    design_width: float = 1920.0,
    depth: int = 0,
    max_depth: int = 8,
) -> DesignNode:
    style = _style(raw)
    rect_px = _rect_from_style(style)
    name = raw.get("eleName") or raw.get("componentName") or raw.get("name") or raw.get("id") or "node"
    node_type = raw.get("type") or raw.get("uiType") or raw.get("designType") or "unknown"
    children = []
    if depth < max_depth:
        for child in raw.get("children") or []:
            if isinstance(child, dict):
                children.append(build_design_node(child, platform, design_width, depth + 1, max_depth))
    return DesignNode(
        id=raw.get("id") or raw.get("layerId"),
        name=str(name),
        type=str(node_type),
        text=_text_from_node(raw),
        rect_px=rect_px,
        rect_platform=convert_rect(rect_px, platform, design_width),
        styles=_interesting_styles(style),
        children=children,
    )


def flatten_nodes(node: DesignNode, limit: int = 120) -> list[DesignNode]:
    result: list[DesignNode] = []

    def visit(current: DesignNode) -> None:
        if len(result) >= limit:
            return
        if current.text or current.rect_px or current.styles:
            result.append(current)
        for child in current.children:
            visit(child)

    visit(node)
    return result


def node_to_dict(node: DesignNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "text": node.text,
        "rect_px": node.rect_px,
        "rect": node.rect_platform,
        "styles": node.styles,
        "children": [node_to_dict(child) for child in node.children],
    }


def summarize_schema(schema: dict[str, Any], platform: TargetPlatform = "android") -> dict[str, Any]:
    root_style = _style(schema)
    root_rect = _rect_from_style(root_style)
    design_width = root_rect.get("width") or _number(root_style.get("width")) or 1920.0
    root = build_design_node(schema, platform, design_width)
    platform_spec = get_platform_spec(platform, design_width)
    flat = flatten_nodes(root)
    texts = []
    for node in flat:
        if node.text and node.text not in texts:
            texts.append(node.text)
    return {
        "platform": platform,
        "unit": platform_spec.unit,
        "conversion_note": platform_spec.note,
        "page_px": root_rect,
        "page": convert_rect(root_rect, platform, design_width),
        "root": node_to_dict(root),
        "nodes": [node_to_dict(node) for node in flat[:80]],
        "texts": texts[:80],
    }
