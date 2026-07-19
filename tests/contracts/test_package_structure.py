"""验证 v0.2.0 的领域包结构，不允许旧模块重新出现。"""

from importlib.util import find_spec


def test_auth_manager_module_exists():
    assert find_spec("lanhu_design_mcp.auth.manager") is not None
