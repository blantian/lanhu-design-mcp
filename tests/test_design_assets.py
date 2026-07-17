"""Tests for lanhu_design_mcp.design_assets."""

from __future__ import annotations

import importlib.util

from lanhu_design_mcp.design_assets import (
    assign_suggested_paths,
    build_ps_scale_urls,
    build_scale_urls,
    sanitize_asset_name,
)


def test_module_exists_and_exports_all_interfaces():
    """Contract test: the module must exist and export all four required signatures."""
    spec = importlib.util.find_spec("lanhu_design_mcp.design_assets")
    assert spec is not None, (
        "lanhu_design_mcp.design_assets module is missing; "
        "create it before proceeding to behavior tests."
    )

    from lanhu_design_mcp.design_assets import (
        assign_suggested_paths,
        build_ps_scale_urls,
        build_scale_urls,
        sanitize_asset_name,
    )

    # Verify they are callable (NotImplementedError is acceptable at this stage).
    assert callable(build_scale_urls)
    assert callable(build_ps_scale_urls)
    assert callable(sanitize_asset_name)
    assert callable(assign_suggested_paths)


# ---------------------------------------------------------------------------
# Behavior tests — ported from upstream scale and safe-name semantics
# ---------------------------------------------------------------------------


def test_build_scale_urls_preserves_original_at_stored_size():
    urls = build_scale_urls("https://cdn/slice.png", 22, 22, 2)
    assert urls["1x"].endswith("resize,w_22,h_22/format,png")
    assert urls["2x"] == "https://cdn/slice.png"
    assert urls["3x"].endswith("resize,w_66,h_66/format,png")
    assert urls["android_hdpi"].endswith("resize,w_17,h_17/format,png")
    assert urls["android_xxxhdpi"] == "https://cdn/slice.png"


def test_build_ps_scale_urls_uses_base_as_2x():
    urls = build_ps_scale_urls("https://cdn/ps.png", 40, 40)
    assert urls["1x"].endswith("resize,w_20,h_20/format,png")
    assert urls["2x"].endswith("resize,w_40,h_40/format,png")
    assert urls["android_hdpi"].endswith("resize,w_30,h_30/format,png")
    assert urls["android_xxxhdpi"].endswith("resize,w_80,h_80/format,png")


def test_safe_names_and_collisions_are_deterministic():
    assert sanitize_asset_name("../菜单/切换\\图标") == "菜单_切换_图标"
    assets = [
        {"name": "切换", "format": "png"},
        {"name": "切换", "format": "png"},
    ]
    assign_suggested_paths(assets, "design-1")
    assert assets[0]["suggested_local_path"] == "assets/lanhu/design-1/切换.png"
    assert assets[1]["suggested_local_path"] == "assets/lanhu/design-1/切换_2.png"
