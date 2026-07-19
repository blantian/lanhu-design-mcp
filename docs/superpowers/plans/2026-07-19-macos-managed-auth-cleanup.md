# macOS Managed Authentication Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `lanhu-design-mcp==0.1.1` as a macOS-only, stdio-only MCP server whose sole Lanhu credential path is the managed Chrome profile, with Chinese production-code documentation and a formal public README.

**Architecture:** `ManagedBrowserAuth` is the only credential provider. It validates a dedicated macOS Chrome Profile and builds the minimal `Settings` consumed by `LanhuClient`; `DesignService` has no file, environment, CAgent, DDS, or default-browser fallback. The release keeps `v0.1.0` immutable and creates `v0.1.1` only after code review, macOS smoke verification, package validation, and Registry validation.

**Tech Stack:** Python 3.10+, FastMCP, Playwright with installed Google Chrome, httpx, pytest, Ruff, AST/tokenize contract tests, GitHub Actions, PyPI Trusted Publishing, MCP Publisher.

## Global Constraints

- Official runtime support is macOS only; non-Darwin authentication returns the exact status `unsupported_platform` without opening a browser or creating a profile.
- The only credential source is the package-owned managed Chrome Profile; remove Cookie files, Cookie environment variables, CAgent, Chrome/Safari database extraction, and separate DDS credentials.
- The MCP server always starts with stdio; remove HTTP transport and its environment configuration.
- Preserve managed-profile ownership markers, owner-only permissions, symlink/default-profile rejection, browser serialization locks, session validation, fixed safe messages, and Cookie-value redaction.
- Every module, class, function, async function, method, nested function, Protocol method, and callback under `src/lanhu_design_mcp/` has a concise Chinese docstring.
- Every non-directive Python comment under `src/lanhu_design_mcp/` contains Chinese explanatory text; identifiers, JSON keys, protocol values, URLs, and status codes remain English.
- Keep valid regression tests; delete tests only when their feature is removed, coverage is exactly duplicated, or they assert obsolete implementation details.
- Version is exactly `0.1.1` in `pyproject.toml`, `src/lanhu_design_mcp/__init__.py`, `server.json` server metadata, and `server.json` package metadata.
- README is a formal macOS `v0.1.1` project page and contains no local absolute path, cc-switch, Cookie-Editor, CAgent, `.env`, manual Cookie, legacy browser database, or HTTP-mode instructions.
- Remove `python-dotenv` and `cryptography`; keep Playwright as a lazily imported core dependency and require installed Google Chrome.
- Keep `.github/workflows/release.yml` release-only, OIDC-only, and pinned exactly as reviewed; do not add `workflow_dispatch`.
- Do not move, delete, or recreate `v0.1.0`; its peeled commit remains `eef3cd31268e91e8aebc5925161331911319a2a4`.
- Preserve historical plans, specs, prompts, CCB artifacts, the user's unrelated prompt change, and the user's `uv.lock` change.
- Replacing the current README content and deleting `PUBLISHING_GUIDE.md`, `PUBLISHING_CHECKLIST.md`, and `publish.sh` are explicitly authorized by the user.
- Do not create or push `v0.1.1`, publish a GitHub Release, upload to PyPI, or publish MCP Registry metadata until Task 5 is approved.

## Execution Setup

Before Task 1, create the isolated implementation branch from the approved plan commit without changing the dirty primary worktree:

```bash
cd /Users/buluesky/mcp/lanhu-design-mcp
test ! -e .worktrees/macos-managed-auth-cleanup
git worktree add .worktrees/macos-managed-auth-cleanup \
  -b feat/macos-managed-auth-cleanup HEAD
cd .worktrees/macos-managed-auth-cleanup
test "$(git branch --show-current)" = "feat/macos-managed-auth-cleanup"
```

Run Tasks 1-6 from this isolated worktree. The primary worktree is consulted only for the explicit dirty-state checks and the three authorized untracked-file deletions in Task 4.

---

### Task 1: Enforce the macOS-Only Managed Authentication Boundary

**Files:**
- Modify: `src/lanhu_design_mcp/managed_auth.py`
- Modify: `tests/test_managed_auth.py`

**Interfaces:**
- Consumes: existing `ManagedBrowserAuth`, `AuthSnapshot`, browser backend protocols, profile safety functions.
- Produces: `UnsupportedPlatformError`, `AuthStatus` value `unsupported_platform`, Darwin-only `default_profile_dir()`, and non-Darwin fail-closed behavior used by Tasks 2-6.

- [ ] **Step 1: Add failing non-Darwin contract tests**

Append focused tests using the existing fake backend conventions:

```python
class TestMacOSOnlyBoundary:
    def test_default_profile_dir_rejects_non_darwin(self):
        with pytest.raises(UnsupportedPlatformError):
            default_profile_dir(system="Linux", environ={"HOME": "/tmp/user"})

    def test_default_profile_dir_uses_macos_application_support(self):
        path = default_profile_dir(system="Darwin", environ={"HOME": "/Users/tester"})
        assert path == Path(
            "/Users/tester/Library/Application Support/lanhu-design-mcp/browser-profile"
        )

    @pytest.mark.asyncio
    async def test_start_login_rejects_non_darwin_without_opening_browser(self):
        backend = AsyncMock()
        auth = ManagedBrowserAuth(backend=backend, system="Linux")
        result = await auth.start_login()
        assert result["status"] == "unsupported_platform"
        assert result["authenticated"] is False
        backend.open.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_cookie_rejects_non_darwin_without_profile_access(self, tmp_path):
        backend = AsyncMock()
        auth = ManagedBrowserAuth(backend=backend, profile_dir=tmp_path / "profile", system="Windows")
        result = await auth.resolve_cookie()
        assert result.configured is False
        assert auth.status_now()["status"] == "unsupported_platform"
        assert not (tmp_path / "profile").exists()
        backend.open.assert_not_called()
```

Import `UnsupportedPlatformError` from `lanhu_design_mcp.managed_auth`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_managed_auth.py::TestMacOSOnlyBoundary -q
```

Expected: collection or assertion failures because `UnsupportedPlatformError`, `system=`, and `unsupported_platform` do not exist.

- [ ] **Step 3: Implement the minimal platform gate**

Add the exact public status and error contract:

```python
AuthStatus = Literal[
    "missing",
    "starting",
    "waiting_for_user",
    "authenticated",
    "expired",
    "cancelled",
    "timed_out",
    "dependency_missing",
    "profile_locked",
    "unsupported_platform",
    "failed",
]


class UnsupportedPlatformError(RuntimeError):
    """表示当前操作系统不在正式支持范围内。"""
```

Change `default_profile_dir()` so it raises on every system except `Darwin` and returns only:

```python
base = Path(environ.get("HOME", Path.home())) / "Library" / "Application Support"
return base / "lanhu-design-mcp" / "browser-profile"
```

Add `system: str | None = None` to `ManagedBrowserAuth.__init__`, store it as `_system`, and add:

```python
def _is_supported_platform(self) -> bool:
    """判断当前进程是否运行在正式支持的 macOS。"""
    return (self._system or platform.system()) == "Darwin"

@staticmethod
def _safe_unsupported_platform_message() -> str:
    """返回不包含本机细节的平台错误提示。"""
    return "Managed Lanhu login is supported on macOS only."

def _reject_unsupported_platform(self) -> bool:
    """在非 macOS 环境设置固定失败状态并阻止后续浏览器操作。"""
    if self._is_supported_platform():
        return False
    self._state = "unsupported_platform"
    self._message = self._safe_unsupported_platform_message()
    return True
```

Call `_reject_unsupported_platform()` at the beginning of `start_login()` and `resolve_cookie()`. `start_login()` returns the current snapshot; `resolve_cookie()` returns an unconfigured `CookieInfo` without resolving the Profile or backend.

- [ ] **Step 4: Remove non-macOS path branches without weakening path safety**

Delete Windows/Linux Profile selection tests and implementation branches. Keep marker checks, symlink rejection, Chrome-default rejection, and unconditional macOS/POSIX `0700` permission enforcement.

- [ ] **Step 5: Run focused and managed-auth suites**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_managed_auth.py::TestMacOSOnlyBoundary -q
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest tests/test_managed_auth.py -q
```

Expected: all remaining managed-auth tests pass with no pending-task warnings.

- [ ] **Step 6: Commit Task 1**

```bash
git add -- src/lanhu_design_mcp/managed_auth.py tests/test_managed_auth.py
git diff --cached --check
git commit -m "refactor: support managed login on macOS only"
```

---

### Task 2: Remove Legacy Credentials, Configuration, HTTP Mode, and Local Helper Scripts

**Files:**
- Rewrite: `src/lanhu_design_mcp/config.py`
- Modify: `src/lanhu_design_mcp/managed_auth.py`
- Modify: `src/lanhu_design_mcp/design_service.py`
- Modify: `src/lanhu_design_mcp/server.py`
- Modify: `src/lanhu_design_mcp/client.py`
- Delete: `src/lanhu_design_mcp/browser_cookies.py`
- Delete: `.env.example`
- Delete: `run-stdio.sh`
- Delete: `tools/get_cookies.py`
- Delete: `tools/setup_cookies.py`
- Delete: `tools/test_mcp_connection.py`
- Modify: `pyproject.toml`
- Rewrite: `tests/test_config.py`
- Modify: `tests/test_design_service_auth.py`
- Modify: `tests/test_client_assets.py`
- Modify: `tests/test_server_auth.py`
- Create: `tests/test_product_contract.py`

**Interfaces:**
- Consumes: Task 1 `ManagedBrowserAuth.resolve_cookie()` and `CookieInfo` results.
- Produces: `CookieInfo(configured, cookie, source, cookie_names)`, `Settings(lanhu_cookie, dds_cookie, http_timeout, lanhu_cookie_source, lanhu_cookie_names)`, `settings_from_cookie(info)`, managed-only `DesignService`, and stdio-only server startup.

- [ ] **Step 1: Write failing managed-only configuration tests**

Replace legacy resolver tests in `tests/test_config.py` with:

```python
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
```

Add managed-only service tests:

```python
@pytest.mark.asyncio
async def test_design_service_always_resolves_managed_cookie():
    auth = AsyncMock(spec=ManagedBrowserAuth)
    auth.resolve_cookie.return_value = CookieInfo(
        True, "session=managed", "managed_browser", ["session"]
    )
    service = DesignService(managed_auth=auth)
    settings = await service._resolve_settings()
    auth.resolve_cookie.assert_awaited_once()
    assert settings.lanhu_cookie == settings.dds_cookie == "session=managed"


@pytest.mark.asyncio
async def test_design_service_missing_managed_cookie_requires_login():
    auth = AsyncMock(spec=ManagedBrowserAuth)
    auth.resolve_cookie.return_value = CookieInfo(False, "", "missing", [])
    service = DesignService(managed_auth=auth)
    with pytest.raises(LanhuAuthRequiredError):
        await service._resolve_settings()
```

Delete credential-precedence tests for explicit, file, environment, legacy browser, and separate DDS sources.

- [ ] **Step 2: Write failing file/configuration removal contracts**

Create `tests/test_product_contract.py`:

```python
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
```

- [ ] **Step 3: Write failing stdio-only server tests**

Change the health test to require exactly the safe product fields:

```python
@pytest.mark.asyncio
async def test_health_reports_only_managed_auth_metadata():
    auth = Mock()
    auth.status_now.return_value = AuthSnapshot("missing", False, "missing", []).to_dict()
    with patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth):
        result = await lanhu_health_check()
    assert set(result) == {"sdk", "tools", "managedAuth"}
    assert result["sdk"] == "fastmcp"
    auth.status_now.assert_called_once()


def test_main_always_runs_stdio():
    with patch("lanhu_design_mcp.server.mcp.run") as run:
        main()
    run.assert_called_once_with(transport="stdio")
```

- [ ] **Step 4: Run new contracts and verify RED**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_config.py tests/test_design_service_auth.py \
  tests/test_server_auth.py tests/test_product_contract.py -q
```

Expected: failures for old dataclass shape, legacy precedence, existing files/config names, old health payload, and configurable transport.

- [ ] **Step 5: Replace `config.py` with the minimal settings model**

Use this complete public contract:

```python
"""定义托管认证结果与蓝湖客户端所需的最小配置。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CookieSource = Literal["managed_browser", "missing"]


@dataclass(frozen=True)
class CookieInfo:
    """保存托管浏览器解析出的会话头及安全诊断名称。"""

    configured: bool
    cookie: str
    source: CookieSource
    cookie_names: list[str]


@dataclass(frozen=True)
class Settings:
    """保存蓝湖 API 与 DDS 请求共享的客户端配置。"""

    lanhu_cookie: str
    dds_cookie: str
    http_timeout: float
    lanhu_cookie_source: CookieSource
    lanhu_cookie_names: list[str]


def settings_from_cookie(info: CookieInfo) -> Settings:
    """把已验证的托管会话转换为蓝湖客户端配置。"""
    return Settings(
        lanhu_cookie=info.cookie,
        dds_cookie=info.cookie,
        http_timeout=30.0,
        lanhu_cookie_source=info.source,
        lanhu_cookie_names=list(info.cookie_names),
    )
```

Update every `CookieInfo(...)` call to the four-field contract and every direct `Settings(...)` test fixture to named arguments matching the five-field contract.

- [ ] **Step 6: Make `DesignService` managed-only**

Remove `self.settings`, `get_settings`, and `resolve_legacy_browser_cookie`. Implement:

```python
async def _resolve_settings(self) -> Settings:
    """从唯一的托管浏览器认证源构建客户端配置。"""
    if self.managed_auth is None:
        from .managed_auth import get_managed_auth

        self.managed_auth = get_managed_auth()
    info = await self.managed_auth.resolve_cookie()
    if not info.configured:
        raise LanhuAuthRequiredError()
    return settings_from_cookie(info)
```

Because managed auth is the only source, `_client()` invalidates `self.managed_auth` on every `LanhuAuthRequiredError` after settings resolution.

- [ ] **Step 7: Make health and startup stdio-only**

Remove all `config` imports from `server.py`. `lanhu_health_check()` returns:

```python
return {
    "sdk": "fastmcp",
    "tools": [
        "lanhu_health_check",
        "lanhu_get_designs",
        "lanhu_analyze_design",
        "lanhu_get_design_assets",
        "lanhu_export_ui_context",
        "lanhu_auth_login",
        "lanhu_auth_status",
        "lanhu_auth_logout",
    ],
    "managedAuth": get_managed_auth().status_now(),
}
```

`main()` contains only:

```python
def main() -> None:
    """以前台 stdio 方式启动 FastMCP 服务器。"""
    mcp.run(transport="stdio")
```

- [ ] **Step 8: Delete legacy files and dependencies**

Delete the six tracked legacy paths listed in `REMOVED_TRACKED_PATHS`. Remove `python-dotenv>=1.0.0` and `cryptography>=41.0.0` from `pyproject.toml`. Preserve `httpx`, `fastmcp`, and `playwright`.

Do not touch the primary-worktree-only untracked publishing files in this task; the controller removes those in Task 4 after recording their names.

- [ ] **Step 9: Run focused and full tests**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_config.py tests/test_design_service_auth.py \
  tests/test_client_assets.py tests/test_server_auth.py \
  tests/test_product_contract.py -q
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest -q
```

Expected: all retained tests pass; total count may decrease only by the explicitly removed legacy tests.

- [ ] **Step 10: Commit Task 2**

```bash
git add -- \
  src/lanhu_design_mcp tests pyproject.toml \
  .env.example run-stdio.sh tools
git diff --cached --check
git commit -m "refactor: use managed Lanhu authentication only"
```

---

### Task 3: Require Chinese Purpose Documentation Across Production Code

**Files:**
- Create: `tests/test_source_documentation.py`
- Modify: every remaining `src/lanhu_design_mcp/*.py`
- Modify: tests containing Ruff-reported unused imports

**Interfaces:**
- Consumes: Task 2's final production source tree.
- Produces: AST/tokenize documentation contract that later code must satisfy without changing runtime APIs.

- [ ] **Step 1: Add the failing source-documentation contract**

Create `tests/test_source_documentation.py`:

```python
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

SOURCE_ROOT = Path("src/lanhu_design_mcp")
CHINESE = re.compile(r"[\u3400-\u9fff]")
COMMENT_DIRECTIVES = ("# type:", "# noqa", "# pragma:")


def source_files() -> list[Path]:
    """返回需要执行中文文档契约的生产源码文件。"""
    return sorted(SOURCE_ROOT.glob("*.py"))


def test_modules_classes_and_functions_have_chinese_docstrings():
    missing: list[str] = []
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes = list(ast.walk(tree))
        for node in nodes:
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node, clean=True) or ""
            if not CHINESE.search(doc):
                name = getattr(node, "name", "<module>")
                line = getattr(node, "lineno", 1)
                missing.append(f"{path}:{line}:{name}")
    assert missing == []


def test_non_directive_comments_contain_chinese_explanation():
    invalid: list[str] = []
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type != tokenize.COMMENT:
                continue
            comment = token.string.strip()
            if comment.startswith(COMMENT_DIRECTIVES):
                continue
            if not CHINESE.search(comment):
                invalid.append(f"{path}:{token.start[0]}:{comment}")
    assert invalid == []
```

- [ ] **Step 2: Run the contract and verify RED**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_source_documentation.py -q
```

Expected: failures listing English/missing module, class, function, nested-function, callback, and Protocol docstrings plus English-only section comments.

- [ ] **Step 3: Add concise Chinese docstrings by responsibility**

Use one-sentence purpose docstrings unless a security invariant needs a second sentence. Cover every definition reported by the failing test. The wording must follow these responsibilities:

| File | Required purpose coverage |
|---|---|
| `__init__.py` | 包入口与版本号 |
| `cli.py` | 参数分派、认证子命令、异步执行、登录/状态/注销退出码 |
| `client.py` | 认证异常、响应分类、客户端生命周期、设计列表/版本/schema/源 JSON 请求 |
| `config.py` | 托管会话类型、客户端配置、配置构建 |
| `design_assets.py` | JS 舍入、倍率 URL、命名清理、路径分配、Sketch/Figma/Photoshop 提取、去重、遍历 |
| `design_ir.py` | 数值/样式/矩形/文本提取、节点构建、扁平化、序列化、schema 摘要 |
| `design_service.py` | 设计选择、托管设置解析、客户端上下文、四个服务操作 |
| `managed_auth.py` | 平台门、Profile 安全、Cookie 白名单、协议、会话验证、Playwright 生命周期、状态机、锁和 worker |
| `platform_units.py` | 平台规格、数值/矩形转换、格式化 |
| `prompts.py` | MCP 提示文本职责 |
| `server.py` | 八个工具、健康检查和 stdio 启动 |
| `url_parser.py` | 蓝湖 URL 校验与标识解析 |

For example:

```python
def parse_lanhu_url(value: str) -> LanhuUrl:
    """校验蓝湖设计链接并提取项目、图片和团队标识。"""


async def close(self) -> None:
    """关闭 HTTP 客户端并释放连接池资源。"""


def on_close(*_args: Any) -> None:
    """在页面或上下文关闭时同步会话关闭状态。"""
```

Rename intentionally unused callback/context-manager parameters to `_args`, `_exc_type`, and `_tb` where protocol signatures allow it; do not change external behavior.

- [ ] **Step 4: Translate explanatory comments and MCP schema descriptions**

Replace English-only section comments with Chinese labels such as `# Profile 生命周期保护`, `# 异步浏览器协议与错误类型`, `# 公开状态机接口`, and `# 内部登录工作协程`. Translate MCP tool docstrings and `Annotated` parameter descriptions to Chinese. Keep terms such as Chrome, HTTP, JSON, DDS, PNG, SVG, OIDC, and API when embedded in a Chinese explanation.

- [ ] **Step 5: Remove verified unused imports without deleting tests**

Run:

```bash
uvx ruff check src/lanhu_design_mcp tests --select F401,F841
```

Remove each reported unused import or local variable. Known baseline findings include `json` in the deleted browser module and unused imports in `test_cli.py`, `test_client_assets.py`, `test_config.py`, `test_design_service_auth.py`, `test_managed_auth.py`, and `test_server_auth.py`. Do not use `--fix` across unrelated rule families.

- [ ] **Step 6: Run documentation, lint, and full tests**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_source_documentation.py -q
uvx ruff check src/lanhu_design_mcp tests --select F401,F841
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest -q
```

Expected: documentation contract passes, Ruff reports `All checks passed!`, and all retained tests pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add -- src/lanhu_design_mcp tests
git diff --cached --check
git commit -m "docs: add Chinese source documentation"
```

---

### Task 4: Publish-Ready README, Metadata, Changelog, and Version 0.1.1

**Files:**
- Rewrite: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `src/lanhu_design_mcp/__init__.py`
- Modify: `server.json`
- Modify: `tests/test_server_auth.py`
- Modify: `tests/test_product_contract.py`
- Delete from primary worktree only: `PUBLISHING_GUIDE.md`
- Delete from primary worktree only: `PUBLISHING_CHECKLIST.md`
- Delete from primary worktree only: `publish.sh`

**Interfaces:**
- Consumes: Tasks 1-3 final behavior and the existing OIDC workflow.
- Produces: one consistent public version `0.1.1`, Registry metadata with no environment variables, and the public onboarding contract used for release notes.

- [ ] **Step 1: Add failing release metadata and README contracts**

Add to `tests/test_product_contract.py`:

```python
import json
import tomllib


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
```

Update existing `server.json` tests to require version `0.1.1` and absence of `environmentVariables`.

- [ ] **Step 2: Run metadata tests and verify RED**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_product_contract.py tests/test_server_auth.py -q
```

Expected: failures for old version, old README, missing macOS classifier, and Registry environment variables.

- [ ] **Step 3: Rewrite README as the formal product page**

The README must contain these sections in this order, with concise Chinese prose and the exact commands shown:

````markdown
<!-- mcp-name: io.github.blantian/lanhu-design-mcp -->

# 蓝湖设计 MCP

`v0.1.1` 是面向 macOS 的蓝湖设计读取与细粒度 UI 资源导出 MCP 服务器。

## 功能
## 系统要求
## 安装

```bash
pip install lanhu-design-mcp
```

## 首次登录

```bash
lanhu-design-mcp auth login
lanhu-design-mcp auth status
```

## MCP 配置

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "lanhu-design-mcp"
    }
  }
}
```

## MCP 工具
## 细粒度切图
## 平台单位
## 托管认证与安全
## 故障排查
## 开发与测试
## v0.1.1 兼容性说明
## 许可证
````

The tools section lists all eight exact tool names and their current parameters. The fine-grained asset section retains one compact JSON example covering `design_image`, `slice`, `remote_url`, `svg_url`, `scale_urls`, `logical_size`, `position_px`, `layer_path`, and `suggested_local_path`. The troubleshooting section covers `auth_required`, `unsupported_platform`, `dependency_missing`, `profile_locked`, `cancelled`, and `timed_out` without describing old credential alternatives.

- [ ] **Step 4: Update version, package metadata, and Registry metadata**

Set version `0.1.1` in the four required locations. Add `"Operating System :: MacOS"` to classifiers. Remove `environmentVariables` entirely from `server.json`; keep its stdio transport and existing Registry schema/name/repository.

- [ ] **Step 5: Add the exact 0.1.1 changelog entry**

Insert above `0.1.0`:

```markdown
## [0.1.1] - 2026-07-19

### Changed
- 认证统一为 macOS 专用托管 Chrome Profile，不再读取 Cookie 文件、环境变量或默认浏览器数据库。
- MCP 启动方式统一为 stdio，并重写正式安装与使用文档。
- 所有生产代码函数和方法增加中文用途说明。

### Added
- 支持 Sketch、Figma、Photoshop 细粒度切图及多倍率资源地址。
- 增加 PyPI Trusted Publishing、会话有效性验证和 macOS 平台边界。

### Removed
- 删除旧 Cookie 配置链、HTTP 模式、本地辅助脚本和过时发布文档。
```

Add `[0.1.1]: https://github.com/blantian/lanhu-design-mcp/releases/tag/v0.1.1` at the bottom.

- [ ] **Step 6: Remove primary-worktree-only obsolete publishing files**

Before deletion, verify all three paths are untracked with:

```bash
git -C /Users/buluesky/mcp/lanhu-design-mcp status --short -- \
  PUBLISHING_GUIDE.md PUBLISHING_CHECKLIST.md publish.sh
for path in PUBLISHING_GUIDE.md PUBLISHING_CHECKLIST.md publish.sh; do
  test -z "$(git -C /Users/buluesky/mcp/lanhu-design-mcp ls-files -- "$path")"
done
```

Expected: status shows `??` for each and `git ls-files` fails. The controller then deletes exactly those three user-authorized files with `apply_patch`; no wildcard or recursive deletion is allowed. Record that untracked deletion is not recoverable from Git.

- [ ] **Step 7: Regenerate the lockfile only in the isolated worktree**

Run:

```bash
uv lock
```

Verify the resulting `uv.lock` removes `python-dotenv` and `cryptography` only when they are no longer transitive dependencies. Do not overwrite the primary worktree's pre-existing user-owned `uv.lock`; carry the reviewed lockfile as part of the feature branch and resolve primary integration explicitly.

- [ ] **Step 8: Run focused and full verification**

Run:

```bash
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest \
  tests/test_product_contract.py tests/test_server_auth.py \
  tests/test_release_workflow.py -q
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest -q
mcp-publisher validate
git diff --check
```

Expected: all tests pass, Registry validates, and no stale public version/configuration remains.

- [ ] **Step 9: Commit Task 4**

```bash
git add -- README.md CHANGELOG.md pyproject.toml uv.lock \
  src/lanhu_design_mcp/__init__.py server.json \
  tests/test_product_contract.py tests/test_server_auth.py
git diff --cached --check
git commit -m "release: prepare macOS-only v0.1.1"
```

---

### Task 5: Release Candidate Verification and Real macOS Smoke Test

**Files:**
- Verify only: committed source, tests, metadata, build artifacts, and local managed Profile
- Create untracked report: `.superpowers/sdd/task-5-report.md`

**Interfaces:**
- Consumes: Tasks 1-4 reviewed commits and an operator-supplied real Lanhu design URL in `LANHU_SMOKE_URL`.
- Produces: release approval evidence; no source commit and no external publication.

- [ ] **Step 1: Verify source and Git scope**

Run:

```bash
git status --short
git diff --check
git grep -nE 'LANHU_COOKIE|DDS_COOKIE|AUTO_BROWSER_COOKIES|MCP_TRANSPORT|SERVER_HOST|SERVER_PORT|cc-switch|Cookie-Editor|CAgent' -- \
  'src/**' README.md server.json pyproject.toml || true
```

Expected: no forbidden public/runtime references; only explicitly preserved unrelated primary-worktree changes remain outside the isolated checkout.

- [ ] **Step 2: Run automated quality gates once**

Run:

```bash
uvx ruff check src/lanhu_design_mcp tests --select F401,F841
/Users/buluesky/mcp/lanhu-design-mcp/.venv/bin/python -m pytest -q
mcp-publisher validate
uvx zizmor --offline --strict-collection --collect=workflows .github/workflows/release.yml
```

Expected: Ruff, pytest, Registry, and zizmor all pass with pristine output.

- [ ] **Step 3: Build from a clean detached worktree**

Run:

```bash
LANHU_RC_ROOT=$(git rev-parse --show-toplevel)
LANHU_RC_BUILD_DIR=$(mktemp -d)
LANHU_RC_ARTIFACT_DIR="$LANHU_RC_ROOT/dist"
test ! -e "$LANHU_RC_ARTIFACT_DIR"
git worktree add --detach "$LANHU_RC_BUILD_DIR" HEAD
(
  cd "$LANHU_RC_BUILD_DIR"
  uv build --no-sources --out-dir "$LANHU_RC_ARTIFACT_DIR"
  uvx twine check "$LANHU_RC_ARTIFACT_DIR"/*
)
git worktree remove "$LANHU_RC_BUILD_DIR"
```

Expected: `lanhu_design_mcp-0.1.1.tar.gz` and `lanhu_design_mcp-0.1.1-py3-none-any.whl` build; both pass Twine; the temporary worktree is removed.

- [ ] **Step 4: Verify clean wheel installation and CLI**

Run:

```bash
LANHU_RC_ROOT=$(git rev-parse --show-toplevel)
LANHU_RC_ARTIFACT_DIR="$LANHU_RC_ROOT/dist"
LANHU_RC_INSTALL_DIR="$LANHU_RC_ARTIFACT_DIR/install"
test -f "$LANHU_RC_ARTIFACT_DIR/lanhu_design_mcp-0.1.1-py3-none-any.whl"
test ! -e "$LANHU_RC_INSTALL_DIR"
uv venv "$LANHU_RC_INSTALL_DIR/.venv"
uv pip install --python "$LANHU_RC_INSTALL_DIR/.venv/bin/python" \
  "$LANHU_RC_ARTIFACT_DIR/lanhu_design_mcp-0.1.1-py3-none-any.whl"
"$LANHU_RC_INSTALL_DIR/.venv/bin/lanhu-design-mcp" --help
```

Expected: the wheel installs without the source tree and CLI help works without importing any removed legacy Cookie module.

- [ ] **Step 5: Run real managed-auth and fine-grained asset smoke**

Require `LANHU_SMOKE_URL` to contain a real user-authorized Lanhu design URL known to include at least one declared slice. Run the exact smoke from the clean wheel environment:

```bash
LANHU_RC_ROOT=$(git rev-parse --show-toplevel)
LANHU_RC_INSTALL_DIR="$LANHU_RC_ROOT/dist/install"
test -x "$LANHU_RC_INSTALL_DIR/.venv/bin/python"
LANHU_SMOKE_URL="$LANHU_SMOKE_URL" \
  "$LANHU_RC_INSTALL_DIR/.venv/bin/python" - <<'PY'
import asyncio
import os

import httpx

from lanhu_design_mcp.design_service import DesignService


async def main() -> None:
    result = await DesignService().get_design_assets(os.environ["LANHU_SMOKE_URL"])
    assert result["status"] == "success"
    assert result["total_assets"] >= 2
    assert result["total_slices"] >= 1
    assert result["assets"][0]["kind"] == "design_image"
    slice_asset = next(asset for asset in result["assets"] if asset["kind"] == "slice")
    asset_url = slice_asset.get("svg_url") or slice_asset.get("remote_url")
    assert asset_url
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(asset_url)
        assert response.status_code == 200
    print({
        "status": result["status"],
        "total_assets": result["total_assets"],
        "total_slices": result["total_slices"],
        "slice_name": slice_asset["name"],
    })


asyncio.run(main())
PY
```

Expected: managed Profile authentication succeeds, fine-grained extraction returns at least one slice, and one PNG or SVG asset responds with HTTP 200. Record only the printed names/counts; never record Cookie values, complete signed URLs, or query secrets.

- [ ] **Step 6: Verify immutable tag prerequisites**

Run:

```bash
test "$(git rev-parse 'refs/tags/v0.1.0^{}')" = \
  "eef3cd31268e91e8aebc5925161331911319a2a4"
test -z "$(git tag --list v0.1.1)"
test "$(git show HEAD:pyproject.toml | grep -c 'version = "0.1.1"')" = "1"
test "$(git ls-tree -r --name-only HEAD -- .github/workflows/release.yml)" = \
  ".github/workflows/release.yml"
```

Expected: `v0.1.0` unchanged, `v0.1.1` absent, version correct, and workflow included in the candidate commit.

- [ ] **Step 7: Write verification report and stop for review**

Record exact commands, counts, artifact names, Registry result, macOS smoke result, tag checks, remaining risks, and primary dirty-state preservation in `.superpowers/sdd/task-5-report.md`. Do not tag or publish in this task.

---

### Task 6: Push, Tag, Publish v0.1.1, Verify PyPI, Then Publish MCP Registry

**Files:**
- External state only: GitHub `main`, tag and Release; PyPI project; MCP Registry
- Append report: `.superpowers/sdd/task-6-report.md`

**Interfaces:**
- Consumes: Task 5 approved release-candidate commit, existing PyPI pending publisher, and protected GitHub Environment `pypi` with reviewer `blantian`.
- Produces: immutable `v0.1.1`, PyPI `lanhu-design-mcp==0.1.1`, and MCP Registry `io.github.blantian/lanhu-design-mcp@0.1.1`.

- [ ] **Step 1: Freeze the reviewed feature commit without touching the dirty primary worktree**

Run from the isolated feature worktree on branch `feat/macos-managed-auth-cleanup`:

```bash
LANHU_RELEASE_HEAD=$(git rev-parse HEAD)
test "$(git branch --show-current)" = "feat/macos-managed-auth-cleanup"
git fetch origin main
git merge-base --is-ancestor origin/main "$LANHU_RELEASE_HEAD"
git -C /Users/buluesky/mcp/lanhu-design-mcp status --short
```

Record the primary dirty paths and exact feature HEAD. Do not fast-forward the local primary worktree: its user-owned `README.md`, `prompt/...`, and `uv.lock` bytes remain untouched. Stop if the candidate is not a fast-forward descendant of remote `main`.

- [ ] **Step 2: Push only main and verify SHA identity**

```bash
git push origin feat/macos-managed-auth-cleanup:main
test "$(git ls-remote --heads origin main | awk '{print $1}')" = "$LANHU_RELEASE_HEAD"
```

Expected: remote `main` equals the reviewed release-candidate commit; local dirty primary `main` remains unchanged and no tag has been pushed.

- [ ] **Step 3: Create and push the immutable v0.1.1 tag**

```bash
git tag -a v0.1.1 -m "Release v0.1.1"
test "$(git rev-parse 'v0.1.1^{}')" = "$LANHU_RELEASE_HEAD"
test "$(git ls-tree -r --name-only 'v0.1.1^{}' -- .github/workflows/release.yml)" = \
  ".github/workflows/release.yml"
git push origin v0.1.1
test "$(git ls-remote --tags origin 'refs/tags/v0.1.1^{}' | awk '{print $1}')" = \
  "$(git rev-parse 'v0.1.1^{}')"
```

Stop if the tag already exists or any SHA/workflow check differs. Never force-push the tag.

- [ ] **Step 4: Publish the GitHub Release and inspect the workflow**

Create GitHub Release `v0.1.1` from the existing tag with title `v0.1.1` and the `CHANGELOG.md` 0.1.1 section. Verify `Publish Python distribution to PyPI` starts from the release event and the build job checks out `v0.1.1`.

- [ ] **Step 5: Approve only the expected pypi deployment**

After the build job passes, inspect the waiting deployment: repository `blantian/lanhu-design-mcp`, workflow `release.yml`, environment `pypi`, tag `v0.1.1`, package version `0.1.1`. The user approves that deployment. Do not approve a different run, ref, environment, or version.

- [ ] **Step 6: Verify PyPI publication and attestations**

Run:

```bash
curl -f https://pypi.org/pypi/lanhu-design-mcp/0.1.1/json
LANHU_PYPI_VERIFY_DIR=$(mktemp -d)
uv venv "$LANHU_PYPI_VERIFY_DIR/.venv"
uv pip install --python "$LANHU_PYPI_VERIFY_DIR/.venv/bin/python" \
  "lanhu-design-mcp==0.1.1"
"$LANHU_PYPI_VERIFY_DIR/.venv/bin/lanhu-design-mcp" --help
```

Verify the GitHub Actions publish job succeeded and PyPI shows provenance/attestation metadata. Stop before Registry publication if any PyPI or install check fails.

- [ ] **Step 7: Publish MCP Registry metadata only after PyPI succeeds**

```bash
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish
curl -f \
  "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.blantian/lanhu-design-mcp"
```

Expected: response contains `io.github.blantian/lanhu-design-mcp` version `0.1.1` backed by the PyPI package.

- [ ] **Step 8: Record final release evidence**

Append local/remote main SHA, local/remote peeled tag SHA, GitHub Release URL, Actions run URL and conclusion, PyPI JSON/version, clean-install result, Registry result, deleted untracked publishing files, and preserved user prompt state to `.superpowers/sdd/task-6-report.md`.
