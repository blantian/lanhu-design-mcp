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
