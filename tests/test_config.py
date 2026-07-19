from lanhu_design_mcp.config import CookieInfo, Settings, settings_from_cookie


def test_settings_from_managed_cookie_reuses_cookie_for_dds():
    info = CookieInfo(True, "session=managed", "managed_browser", ["session"])
    settings = settings_from_cookie(info)
    assert settings == Settings(
        lanhu_cookie="session=managed",
        dds_cookie="session=managed",
        http_timeout=30.0,
        lanhu_cookie_source="managed_browser",
        lanhu_cookie_names=["session"],
    )


def test_settings_from_missing_cookie_is_empty():
    settings = settings_from_cookie(CookieInfo(False, "", "missing", []))
    assert settings.lanhu_cookie == ""
    assert settings.dds_cookie == ""
    assert settings.lanhu_cookie_source == "missing"
