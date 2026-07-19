"""auth.models 的数据模型、安全错误和序列化测试。"""

from __future__ import annotations

from lanhu_design_mcp.auth.models import (
    AuthSnapshot,
    CookieInfo,
    Settings,
    settings_from_cookie,
)
from lanhu_design_mcp.auth.profile import LANHU_DOMAINS


# ---------------------------------------------------------------------------
# AuthSnapshot serialization safety
# ---------------------------------------------------------------------------


class TestAuthSnapshotSafety:
    def test_never_serializes_cookie_values(self):
        snapshot = AuthSnapshot(
            status="authenticated",
            authenticated=True,
            source="managed_browser",
            cookie_names=["session"],
            session_id="id",
            message=None,
        )
        d = snapshot.to_dict()
        # cookieNames is the only allowed cookie-related field; no value may leak
        assert d["cookieNames"] == ["session"]
        # No field in the dict should carry a cookie value (key=value pattern)
        for v in d.values():
            if isinstance(v, str):
                assert "=" not in v, f"value leak: {v}"

    def test_message_is_optional(self):
        snapshot = AuthSnapshot(
            status="missing",
            authenticated=False,
            source="missing",
            cookie_names=[],
        )
        d = snapshot.to_dict()
        assert "message" not in d
        assert d["status"] == "missing"


# ---------------------------------------------------------------------------
# cross-checks
# ---------------------------------------------------------------------------


class TestCookieInfoCompatibility:
    def test_cookie_info_accepts_managed_browser_source(self):
        info = CookieInfo(True, "session=x", "managed_browser", ["session"])
        assert info.source == "managed_browser"
        assert info.configured is True
        assert info.cookie_names == ["session"]

    def test_lanhu_domains_is_an_exact_allowlist(self):
        assert isinstance(LANHU_DOMAINS, (set, frozenset))
        assert "lanhuapp.com" in LANHU_DOMAINS


# ---------------------------------------------------------------------------
# Settings factory contract
# ---------------------------------------------------------------------------


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
