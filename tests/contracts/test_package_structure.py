"""验证 v0.2.0 的领域包结构，不允许旧模块重新出现。"""

from importlib.util import find_spec

import pytest


def test_auth_manager_module_exists():
    assert find_spec("lanhu_design_mcp.auth.manager") is not None


def test_auth_foundation_modules_exist():
    assert find_spec("lanhu_design_mcp.auth.models") is not None
    assert find_spec("lanhu_design_mcp.auth.profile") is not None


def test_auth_runtime_modules_exist():
    assert find_spec("lanhu_design_mcp.auth.validator") is not None
    assert find_spec("lanhu_design_mcp.auth.browser") is not None


def test_old_auth_module_is_removed():
    assert find_spec("lanhu_design_mcp.managed_auth") is None


def test_design_package_modules_exist():
    modules = ("url", "units", "ir", "assets", "service")
    assert all(find_spec(f"lanhu_design_mcp.design.{name}") is not None for name in modules)


def test_design_exports_match_all():
    import lanhu_design_mcp.design as d
    assert d.__all__ == ["DesignService", "LanhuUrl", "parse_lanhu_url"]
    assert d.DesignService is not None
    assert d.LanhuUrl is not None
    assert d.parse_lanhu_url is not None


@pytest.mark.parametrize("name", [
    "url_parser", "platform_units", "design_ir", "design_assets", "design_service",
])
def test_old_design_modules_are_removed(name):
    assert find_spec(f"lanhu_design_mcp.{name}") is None
