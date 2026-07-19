import json
import re
import tomllib
from pathlib import Path


REMOVED_TRACKED_PATHS = (
    ".env.example",
    "run-stdio.sh",
    "src/lanhu_design_mcp/browser_cookies.py",
    "tools/get_cookies.py",
    "tools/setup_cookies.py",
    "tools/test_mcp_connection.py",
)

REMOVED_CONFIG_NAMES = (
    "LANHU_COOKIE_FILE",
    "LANHU_COOKIE",
    "AUTO_BROWSER_COOKIES",
    "DDS_COOKIE_FILE",
    "DDS_COOKIE",
    "DATA_DIR",
    "MCP_TRANSPORT",
    "SERVER_HOST",
    "SERVER_PORT",
)


def test_legacy_files_are_removed():
    assert [path for path in REMOVED_TRACKED_PATHS if Path(path).exists()] == []


def test_legacy_configuration_is_absent_from_production_code():
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/lanhu_design_mcp").glob("*.py")
    )
    assert [name for name in REMOVED_CONFIG_NAMES if name in production] == []


def test_removed_dependencies_are_absent():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "python-dotenv" not in text
    assert "cryptography" not in text
    assert "playwright>=1.50.0" in text


def test_public_versions_are_0_2_0():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    server = json.loads(Path("server.json").read_text(encoding="utf-8"))
    init_text = Path("src/lanhu_design_mcp/__init__.py").read_text(encoding="utf-8")
    expected = "0.2.0"
    assert project["project"]["version"] == expected
    assert server["version"] == expected
    assert server["packages"][0]["version"] == expected
    assert f'__version__ = "{expected}"' in init_text


def test_registry_package_has_no_environment_configuration():
    server = json.loads(Path("server.json").read_text(encoding="utf-8"))
    assert "environmentVariables" not in server["packages"][0]


def test_project_declares_macos_only():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"Operating System :: MacOS"' in text


def test_readme_contains_only_current_onboarding():
    """验证 README 只包含当前正式 onboarding 内容，不含旧凭据方案。"""
    readme = Path("README.md").read_text(encoding="utf-8")

    # 精确提取所有二级标题并校验顺序
    expected = [
        "项目简介", "功能", "系统要求", "安装", "首次登录", "MCP 配置",
        "工具", "使用规范", "常见错误", "开发验证", "许可证",
    ]
    headings = re.findall(r"^## (.+)$", readme, re.MULTILINE)
    assert headings == expected, f"章节标题不匹配: {headings}"

    # 关键 onboarding 内容必须存在
    onboarding = (
        "pip install lanhu-design-mcp",
        "lanhu-design-mcp auth login",
        "macOS",
        "Google Chrome",
        "cc-switch",
        '"type": "stdio"',
        '"args": []',
    )
    assert all(item in readme for item in onboarding)

    # 八个工具名称必须全部出现
    tools = (
        "lanhu_health_check", "lanhu_get_designs", "lanhu_analyze_design",
        "lanhu_get_design_assets", "lanhu_export_ui_context",
        "lanhu_auth_login", "lanhu_auth_status", "lanhu_auth_logout",
    )
    assert all(t in readme for t in tools)

    # 旧凭据方案字符串禁止出现
    forbidden = (
        "LANHU_COOKIE", "DDS_COOKIE", "AUTO_BROWSER_COOKIES",
        "run-stdio.sh", "Cookie-Editor", "CAgent",
    )
    assert all(f not in readme for f in forbidden)

    # 提取 MCP 配置 JSON 并验证结构
    m = re.search(r"```json\n(.*?)\n```", readme, re.DOTALL)
    assert m is not None, "未找到 MCP 配置 JSON 代码块"
    cfg = json.loads(m.group(1))
    server = cfg["mcpServers"]["lanhu-design-mcp"]
    assert server["type"] == "stdio"
    assert server["command"] == "/Users/your-name/.local/bin/lanhu-design-mcp"
    assert server["args"] == []


def test_local_agent_state_is_ignored():
    ignore = Path(".gitignore").read_text(encoding="utf-8")
    for entry in (".ccb/", ".claude/", ".superpowers/"):
        assert entry in ignore
