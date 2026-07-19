"""Tests for lanhu_design_mcp.design.assets."""

from __future__ import annotations

import importlib.util

from lanhu_design_mcp.design.assets import (
    assign_suggested_paths,
    build_ps_scale_urls,
    build_scale_urls,
    sanitize_asset_name,
)


def test_module_exists_and_exports_all_interfaces():
    """Contract test: the module must exist and export all four required signatures."""
    spec = importlib.util.find_spec("lanhu_design_mcp.design.assets")
    assert spec is not None, (
        "lanhu_design_mcp.design.assets module is missing; "
        "create it before proceeding to behavior tests."
    )

    from lanhu_design_mcp.design.assets import (
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

    # Task 2: extract_design_slices must be present.
    import lanhu_design_mcp.design.assets as da

    assert hasattr(da, "extract_design_slices"), (
        "design_assets.extract_design_slices is missing; "
        "add the stub before proceeding to behavior tests."
    )


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


# ---------------------------------------------------------------------------
# Task 2: Sketch and Figma slice extraction
# ---------------------------------------------------------------------------

from lanhu_design_mcp.design.assets import extract_design_slices


def test_extracts_sketch_png_and_svg_slice():
    source = {
        "sliceScale": 2,
        "info": [{
            "id": "slice-1", "name": "切换", "type": "slice", "parentID": "group-1",
            "layerOriginFrame": {"x": 1241, "y": 66, "width": 22, "height": 22},
            "image": {
                "imageUrl": "https://cdn/slice.png", "svgUrl": "https://cdn/slice.svg",
                "size": {"width": 22, "height": 22},
            },
        }],
    }
    result = extract_design_slices(source, "design-1")
    asset = result["slices"][0]
    assert result["slice_scale"] == 2
    assert asset["kind"] == "slice"
    assert asset["remote_url"] == "https://cdn/slice.png"
    assert asset["svg_url"] == "https://cdn/slice.svg"
    assert asset["logical_size"] == {"width": 22, "height": 22}
    assert asset["position_px"] == {"x": 1241, "y": 66}


def test_figma_requires_exported_bitmap_and_ignores_fill():
    source = {
        "meta": {"host": {"name": "figma"}, "sliceScale": 2},
        "artboard": {"layers": [
            {"id": "real", "name": "icon", "type": "bitmapLayer", "hasExportImage": True,
             "frame": {"x": 1, "y": 2, "width": 20, "height": 10},
             "image": {"imageUrl": "https://cdn/real.png"}},
            {"id": "fill", "name": "photo-fill", "type": "shapeLayer", "hasExportImage": False,
             "image": {"imageUrl": "https://cdn/fill.png"},
             "ddsImage": {"imageUrl": "https://cdn/fill-dds.png"}},
        ]},
    }
    result = extract_design_slices(source, "design-1")
    assert [item["id"] for item in result["slices"]] == ["real"]
    assert result["slices"][0]["layer_path"] == "icon"


def test_legacy_sketch_dds_image_uses_frame_fallback():
    source = {"info": [{
        "id": "legacy", "name": "legacy/icon", "left": 3, "top": 4,
        "frame": {"width": 12, "height": 8},
        "ddsImage": {"imageUrl": "https://cdn/legacy.png"},
    }]}
    asset = extract_design_slices(source, "design-1")["slices"][0]
    assert asset["logical_size"] == {"width": 12, "height": 8}
    assert asset["position_px"] == {"x": 3, "y": 4}
    assert asset["suggested_local_path"].endswith("legacy_icon.png")


def test_nested_layer_path_parent_and_metadata_are_preserved():
    source = {"info": [{"name": "Toolbar", "children": [{
        "id": "icon", "name": "Search", "opacity": 0.5,
        "fills": [{"color": "#fff"}],
        "image": {"imageUrl": "https://cdn/search.png", "size": {"width": 10, "height": 10}},
    }]}]}
    asset = extract_design_slices(source, "design-1")["slices"][0]
    assert asset["parent_name"] == "Toolbar"
    assert asset["layer_path"] == "Toolbar/Search"
    assert asset["metadata"] == {"fills": [{"color": "#fff"}], "opacity": 0.5}


def test_svg_only_slice_has_no_raster_scale_urls():
    source = {"info": [{
        "id": "vector", "name": "Vector", "image": {
            "svgUrl": "https://cdn/vector.svg", "size": {"width": 12, "height": 12}
        }
    }]}
    asset = extract_design_slices(source, "design-1")["slices"][0]
    assert asset["format"] == "svg"
    assert asset["remote_url"] == "https://cdn/vector.svg"
    assert "scale_urls" not in asset


# ---------------------------------------------------------------------------
# Task 3: Photoshop, deduplication, and malformed candidates
# ---------------------------------------------------------------------------


def test_extracts_photoshop_asset_and_deduplicates_ids():
    source = {
        "type": "ps",
        "board": {"layers": [{
            "id": "ps-1", "name": "背景", "type": "bitmap", "left": 10, "top": 20,
            "width": 40, "height": 20,
            "images": {"png_xxxhd": "https://cdn/ps.png", "svg": "https://cdn/ps.svg"},
        }]},
        "assets": [
            {"id": "ps-1", "name": "背景", "isSlice": True, "scaleType": 2},
            {"id": "ps-1", "name": "背景", "isSlice": True, "scaleType": 2},
        ],
    }
    result = extract_design_slices(source, "design-ps")
    assert result["total_slices"] == 1
    asset = result["slices"][0]
    assert asset["logical_size"] == {"width": 20, "height": 10}
    assert asset["base_size"] == {"width": 40, "height": 20}
    assert asset["metadata"] == {"source": "photoshop", "asset_id": "ps-1", "scaleType": 2}


def test_duplicate_sketch_records_and_malformed_children_do_not_abort():
    repeated = {"id": "same", "name": "icon", "image": {"imageUrl": "https://cdn/a.png", "size": {"width": 8, "height": 8}}}
    source = {"info": [repeated, repeated, {"name": "bad", "image": "not-a-dict", "children": [None, "bad"]}]}
    result = extract_design_slices(source, "design-1")
    assert result["total_slices"] == 1
    assert result["warnings"] == ["Skipped 1 malformed slice candidate(s)"]
