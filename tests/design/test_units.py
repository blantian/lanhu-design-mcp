from lanhu_design_mcp.design.units import convert_rect, convert_value, format_value, get_platform_spec


def test_android_matches_verified_lanhu_rule():
    assert get_platform_spec("android").unit == "dp"
    assert convert_value(1920, "android") == 960
    assert convert_value(1080, "android") == 540
    assert format_value(1579, "android") == "789.5dp"


def test_web_keeps_px():
    assert convert_rect({"x": 341, "y": 120, "width": 1579, "height": 74}, "web") == {
        "x": 341,
        "y": 120,
        "width": 1579,
        "height": 74,
    }


def test_wechat_uses_750_rpx_width_basis():
    assert get_platform_spec("wechat_miniprogram", design_width=1920).unit == "rpx"
    assert convert_value(1920, "wechat_miniprogram", design_width=1920) == 750
