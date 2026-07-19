import json
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


def test_public_versions_are_0_1_1():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    server = json.loads(Path("server.json").read_text(encoding="utf-8"))
    init_text = Path("src/lanhu_design_mcp/__init__.py").read_text(encoding="utf-8")
    assert project["project"]["version"] == "0.1.1"
    assert server["version"] == "0.1.1"
    assert server["packages"][0]["version"] == "0.1.1"
    assert '__version__ = "0.1.1"' in init_text


def test_registry_package_has_no_environment_configuration():
    server = json.loads(Path("server.json").read_text(encoding="utf-8"))
    assert "environmentVariables" not in server["packages"][0]


def test_project_declares_macos_only():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"Operating System :: MacOS"' in text


def test_readme_is_formal_managed_auth_onboarding():
    text = Path("README.md").read_text(encoding="utf-8")
    required = (
        "pip install lanhu-design-mcp",
        "lanhu-design-mcp auth login",
        '"command": "lanhu-design-mcp"',
        "lanhu_get_design_assets",
        "lanhu_auth_login",
        "macOS",
        "Google Chrome",
        "v0.1.1",
    )
    forbidden = (
        "/Users/",
        "cc-switch",
        "Cookie-Editor",
        "CAgent",
        "LANHU_COOKIE",
        "DDS_COOKIE",
        "AUTO_BROWSER_COOKIES",
        "MCP_TRANSPORT",
        "SERVER_HOST",
        "SERVER_PORT",
        "run-stdio.sh",
        "tools/setup_cookies.py",
    )
    assert [value for value in required if value not in text] == []
    assert [value for value in forbidden if value in text] == []
