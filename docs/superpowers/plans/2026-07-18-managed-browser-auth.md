# Lanhu Managed Browser Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a locally published Lanhu MCP open a dedicated Chrome profile for one interactive login, then reuse that session without manual cookie copying while preserving all existing cookie sources.

**Architecture:** Keep synchronous file/env configuration separate from asynchronous managed-browser authentication. A focused `ManagedBrowserAuth` service owns the package-marked Chrome profile, lazy Playwright boundary, in-memory cookie cache, and login state machine; `DesignService` resolves credentials before constructing `LanhuClient`. FastMCP tools and CLI commands are thin adapters over the same service.

**Tech Stack:** Python 3.10+, FastMCP, httpx, optional Playwright Python package using installed Chrome (`channel="chrome"`), pytest, pytest-asyncio.

## Global Constraints

- The first Lanhu login is user-interactive; password, QR, CAPTCHA, and SSO entry are never automated.
- Existing precedence remains `LANHU_COOKIE_FILE` -> CAgent cookie file -> `LANHU_COOKIE` -> managed Chrome profile -> legacy browser DB -> missing.
- Normal design tools never open a visible browser; only `lanhu_auth_login` or `auth login` may do so.
- Playwright is lazily imported and optional; explicit cookie modes and bare MCP startup work without it.
- Cookie values and storage state never appear in MCP/CLI responses, logs, exceptions, snapshots, fixtures, or documentation.
- Managed browser state is outside the repository, owner-only on POSIX, and removable only when a package marker exists and logout is explicitly confirmed.
- Use installed Google Chrome through `channel="chrome"`; do not run `playwright install` or download browsers automatically.
- Do not include the repository's pre-existing `README.md`, `uv.lock`, prompt, publishing, or `.ccb` changes in feature commits. `uv.lock` currently contains unrelated package-index rewrites; do not regenerate or stage it in this plan.

---

## File Structure

- Create `src/lanhu_design_mcp/managed_auth.py`: profile paths, domain filtering, browser protocols, Playwright adapter, state machine, safe result serialization, logout.
- Create `src/lanhu_design_mcp/cli.py`: no-argument MCP startup plus `auth login|status|logout` dispatch.
- Modify `src/lanhu_design_mcp/config.py`: explicit/legacy resolver split, `managed_browser` metadata, settings override helper.
- Modify `src/lanhu_design_mcp/client.py`: stable authentication-required error and narrowly classified HTTP authentication failures.
- Modify `src/lanhu_design_mcp/design_service.py`: asynchronous credential/client factory and managed-cache invalidation.
- Modify `src/lanhu_design_mcp/server.py`: three MCP authentication tools and local-only health metadata.
- Modify `pyproject.toml`: optional `auth` extra and CLI entry point.
- Modify `server.json`: published installation/configuration metadata for automatic local login.
- Modify `README.md`: managed login becomes the recommended human workflow while manual sources remain documented.
- Create `tests/test_managed_auth.py`, `tests/test_design_service_auth.py`, `tests/test_server_auth.py`, and `tests/test_cli.py`; extend `tests/test_config.py` and `tests/test_client_assets.py` only for their owned contracts.

---

### Task 1: Split Explicit and Legacy Cookie Resolution

**Files:**
- Modify: `src/lanhu_design_mcp/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `resolve_configured_lanhu_cookie() -> CookieInfo`
- Produces: `resolve_legacy_browser_cookie() -> CookieInfo`
- Produces: `get_settings(*, include_browser_fallback: bool = True, lanhu_override: CookieInfo | None = None) -> Settings`
- Preserves: `resolve_lanhu_cookie() -> CookieInfo` as the synchronous compatibility resolver.

- [ ] **Step 1: Add failing configuration contract and precedence tests**

Add imports and tests equivalent to:

```python
from lanhu_design_mcp.config import (
    resolve_configured_lanhu_cookie,
    resolve_legacy_browser_cookie,
)

def test_configured_resolver_does_not_touch_browser(monkeypatch, tmp_path):
    monkeypatch.delenv("LANHU_COOKIE", raising=False)
    monkeypatch.delenv("LANHU_COOKIE_FILE", raising=False)
    monkeypatch.setenv("AUTO_BROWSER_COOKIES", "true")
    with patch.object(Path, "home", return_value=tmp_path), patch(
        "lanhu_design_mcp.browser_cookies.get_lanhu_cookies"
    ) as browser:
        info = resolve_configured_lanhu_cookie()
    assert info.source == "missing"
    browser.assert_not_called()

def test_settings_accept_managed_browser_override(monkeypatch, tmp_path):
    monkeypatch.delenv("DDS_COOKIE", raising=False)
    monkeypatch.delenv("DDS_COOKIE_FILE", raising=False)
    info = CookieInfo(True, "session=fake", "managed_browser", None, ["session"])
    with patch.object(Path, "home", return_value=tmp_path):
        settings = get_settings(include_browser_fallback=False, lanhu_override=info)
    assert settings.lanhu_cookie_source == "managed_browser"
    assert settings.dds_cookie == "session=fake"
    assert settings.dds_cookie_source == "lanhu"
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m pytest tests/test_config.py -q`

Expected: import failure for the two new resolver names or rejection of `managed_browser`/new keyword arguments.

- [ ] **Step 3: Implement the resolver split without changing compatibility behavior**

Use this structure in `config.py`:

```python
CookieSource = Literal["file", "env", "browser", "managed_browser", "lanhu", "missing"]

def _missing_cookie_info() -> CookieInfo:
    return CookieInfo(False, "", "missing", None, [])

def resolve_configured_lanhu_cookie() -> CookieInfo:
    cookie_file_path = os.getenv("LANHU_COOKIE_FILE", "").strip()
    if cookie_file_path:
        path = Path(cookie_file_path)
        cookie = _read_cookie_file(path)
        if cookie:
            return CookieInfo(True, cookie, "file", path, cookie_names_from_header(cookie))
    path = default_lanhu_cookie_file()
    cookie = _read_cookie_file(path)
    if cookie:
        return CookieInfo(True, cookie, "file", path, cookie_names_from_header(cookie))
    cookie = os.getenv("LANHU_COOKIE", "").strip()
    if cookie:
        return CookieInfo(True, cookie, "env", None, cookie_names_from_header(cookie))
    return _missing_cookie_info()

def resolve_legacy_browser_cookie() -> CookieInfo:
    if os.getenv("AUTO_BROWSER_COOKIES", "false").lower() not in {"true", "1", "yes"}:
        return _missing_cookie_info()
    try:
        from .browser_cookies import get_lanhu_cookies
        cookie = get_lanhu_cookies()
    except Exception:
        print("警告: 自动获取浏览器 Cookies 失败", file=sys.stderr)
        return _missing_cookie_info()
    if not cookie:
        return _missing_cookie_info()
    return CookieInfo(True, cookie, "browser", None, cookie_names_from_header(cookie))

def resolve_lanhu_cookie() -> CookieInfo:
    configured = resolve_configured_lanhu_cookie()
    if configured.configured:
        return configured
    return resolve_legacy_browser_cookie()

def get_settings(
    *,
    include_browser_fallback: bool = True,
    lanhu_override: CookieInfo | None = None,
) -> Settings:
    if lanhu_override is not None:
        lanhu_info = lanhu_override
    else:
        lanhu_info = resolve_configured_lanhu_cookie()
        if include_browser_fallback and not lanhu_info.configured:
            lanhu_info = resolve_legacy_browser_cookie()
    dds_info = resolve_dds_cookie(lanhu_info)
    return Settings(
        lanhu_cookie=lanhu_info.cookie,
        dds_cookie=dds_info.cookie,
        data_dir=Path(os.getenv("DATA_DIR", "./data")),
        http_timeout=float(os.getenv("HTTP_TIMEOUT", "30")),
        transport=os.getenv("MCP_TRANSPORT", "stdio").lower(),
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
        lanhu_cookie_source=lanhu_info.source,
        lanhu_cookie_file=lanhu_info.cookie_file,
        lanhu_cookie_names=lanhu_info.cookie_names,
        dds_cookie_source=dds_info.source,
        dds_cookie_file=dds_info.cookie_file,
        dds_cookie_names=dds_info.cookie_names,
    )
```

Do not print raw browser exceptions. Keep the existing safe warning text.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m pytest tests/test_config.py -q`

Expected: all configuration tests pass.

Run: `python -m pytest -q`

Expected: the existing 43-test baseline plus new tests passes.

- [ ] **Step 5: Commit only Task 1 files**

```bash
git add src/lanhu_design_mcp/config.py tests/test_config.py
git commit -m "refactor: split Lanhu cookie resolution"
```

---

### Task 2: Add Managed Profile and Cookie-Safety Foundations

**Files:**
- Create: `src/lanhu_design_mcp/managed_auth.py`
- Create: `tests/test_managed_auth.py`

**Interfaces:**
- Produces: `default_profile_dir(system: str | None = None, environ: Mapping[str, str] | None = None) -> Path`
- Produces: `filter_lanhu_cookies(cookies: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]`
- Produces: `format_cookie_header(cookies: Sequence[Mapping[str, Any]]) -> str`
- Produces: `AuthSnapshot.to_dict() -> dict[str, Any]`
- Produces: package marker helpers used by Task 3 logout.

- [ ] **Step 1: Write failing pure-function and safety tests**

Create tests covering exact platform paths, allowlisting, serialization, permissions, and deletion guard:

```python
def test_default_profile_dir_uses_platform_app_data(tmp_path):
    path = default_profile_dir("Darwin", {"HOME": str(tmp_path)})
    assert path == tmp_path / "Library" / "Application Support" / "lanhu-design-mcp" / "browser-profile"

def test_cookie_filter_accepts_only_lanhu_domains():
    cookies = [
        {"name": "session", "value": "fake", "domain": ".lanhuapp.com"},
        {"name": "evil", "value": "secret", "domain": "example.com"},
    ]
    assert [item["name"] for item in filter_lanhu_cookies(cookies)] == ["session"]

def test_snapshot_never_serializes_cookie_value():
    snapshot = AuthSnapshot(
        status="authenticated", authenticated=True, source="managed_browser",
        cookie_names=["session"], session_id="id", message=None,
    )
    assert "fake" not in str(snapshot.to_dict())
    assert "cookie" not in snapshot.to_dict()

def test_unmarked_directory_cannot_be_removed(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    with pytest.raises(UnsafeProfileError):
        remove_owned_profile(profile)
    assert profile.exists()
```

Also test Linux (`XDG_DATA_HOME` then `~/.local/share`) and Windows (`LOCALAPPDATA`) paths, POSIX `0700`, deterministic `name=value` formatting, empty cookies, and rejection of ordinary Chrome Default profile suffixes.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest tests/test_managed_auth.py -q`

Expected: module import failure.

- [ ] **Step 3: Implement the pure foundations**

Start `managed_auth.py` with these stable types and constants:

```python
AuthStatus = Literal[
    "missing", "starting", "waiting_for_user", "authenticated", "expired",
    "cancelled", "timed_out", "dependency_missing", "profile_locked", "failed",
]
LANHU_DOMAINS = {"lanhuapp.com", ".lanhuapp.com", "dds.lanhuapp.com", ".dds.lanhuapp.com"}
AUTH_COOKIE_NAMES = {"session", "user_token"}
PROFILE_MARKER = ".lanhu-design-mcp-profile"

@dataclass(frozen=True)
class AuthSnapshot:
    status: AuthStatus
    authenticated: bool
    source: str
    cookie_names: list[str]
    session_id: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "status": self.status,
            "authenticated": self.authenticated,
            "source": self.source,
            "cookieNames": self.cookie_names,
            "sessionId": self.session_id,
        }
        if self.message:
            result["message"] = self.message
        return result
```

`filter_lanhu_cookies` must compare normalized cookie domains, not use substring matching. `format_cookie_header` accepts only the already-filtered list and sorts by cookie name for deterministic tests. `ensure_owned_profile` creates parent/profile directories, sets `0700` on POSIX, rejects default Chrome profile paths, and creates the marker. `remove_owned_profile` resolves the path, requires the marker as a direct child, then deletes only that directory.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_managed_auth.py -q`

Expected: all pure foundation tests pass without Playwright installed or a browser launch.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/lanhu_design_mcp/managed_auth.py tests/test_managed_auth.py
git commit -m "feat: add managed auth foundations"
```

---

### Task 3: Implement the Lazy Playwright Login State Machine

**Files:**
- Modify: `src/lanhu_design_mcp/managed_auth.py`
- Modify: `tests/test_managed_auth.py`

**Interfaces:**
- Produces protocol: `BrowserBackend.open(profile_dir: Path, *, headless: bool) -> BrowserSession`
- Produces: `PlaywrightBrowserBackend`
- Produces: `ManagedBrowserAuth.start_login() -> dict[str, Any]`
- Produces: `ManagedBrowserAuth.status(session_id: str | None = None, *, probe_profile: bool = True) -> dict[str, Any]`
- Produces: `ManagedBrowserAuth.status_now() -> dict[str, Any]` for local, synchronous health metadata.
- Produces: `ManagedBrowserAuth.resolve_cookie() -> CookieInfo`
- Produces: `ManagedBrowserAuth.invalidate() -> None`
- Produces: `ManagedBrowserAuth.logout(confirm: bool) -> dict[str, Any]`
- Produces singleton accessor: `get_managed_auth() -> ManagedBrowserAuth`

- [ ] **Step 1: Add failing state-machine tests using a fake backend**

Define a fake `BrowserSession`/`BrowserBackend`; never import or launch real Playwright in automated tests. Cover:

```python
@pytest.mark.asyncio
async def test_start_login_is_non_blocking_and_idempotent(tmp_path):
    backend = FakeBackend(cookies_after=asyncio.Event())
    auth = ManagedBrowserAuth(backend=backend, profile_dir=tmp_path / "profile", poll_interval=0)
    first = await auth.start_login()
    second = await auth.start_login()
    assert first["status"] in {"starting", "waiting_for_user"}
    assert second["sessionId"] == first["sessionId"]
    assert backend.open_count == 1
    await auth.shutdown()

@pytest.mark.asyncio
async def test_login_caches_only_lanhu_cookies(tmp_path):
    backend = FakeBackend(cookies=[
        {"name": "session", "value": "fake", "domain": ".lanhuapp.com"},
        {"name": "other", "value": "secret", "domain": "example.com"},
    ])
    auth = ManagedBrowserAuth(backend=backend, profile_dir=tmp_path / "profile", poll_interval=0)
    await auth.start_login()
    await auth.wait_for_terminal_state()
    info = await auth.resolve_cookie()
    assert info.source == "managed_browser"
    assert info.cookie == "session=fake"
    assert info.cookie_names == ["session"]
```

Also cover persisted-profile headless extraction, missing Playwright, missing Chrome, profile lock, cancellation, timeout with injected clock/short timeout, retry after terminal failure, safe exception messages, `invalidate()`, confirmed marker-guarded logout, unconfirmed no-op, and closing owned contexts/tasks.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest tests/test_managed_auth.py -q`

Expected: missing protocols/classes/methods.

- [ ] **Step 3: Implement the injectable browser boundary**

Use protocols so tests do not depend on Playwright:

```python
class BrowserSession(Protocol):
    async def cookies(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def is_closed(self) -> bool:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

class BrowserBackend(Protocol):
    async def open(self, profile_dir: Path, *, headless: bool) -> BrowserSession:
        raise NotImplementedError
```

`PlaywrightBrowserBackend.open` performs the import inside the method:

```python
try:
    from playwright.async_api import async_playwright
except ImportError as exc:
    raise AuthDependencyError("Install automatic login with: pip install 'lanhu-design-mcp[auth]'") from exc
```

Start Playwright, then call `chromium.launch_persistent_context(user_data_dir=str(profile_dir), channel="chrome", headless=headless)`. For visible login, ensure one page exists and navigate it to `https://lanhuapp.com/`. Wrap the context and Playwright driver in one session whose `close()` always closes both. Map the known Playwright executable-not-found message to a safe Chrome-required message; map profile-lock signatures to `AuthProfileLockedError`; never return raw exception text.

- [ ] **Step 4: Implement `ManagedBrowserAuth` lifecycle**

Use one `asyncio.Lock`, one optional background task, and one in-memory cookie string. `start_login()` creates an opaque `uuid4().hex`, sets `starting`, schedules `_login_worker`, and yields once with `await asyncio.sleep(0)` so the caller gets `starting` or `waiting_for_user` immediately.

The visible worker opens the owned profile, sets `waiting_for_user`, then polls cookies until either `session` or `user_token` exists on an allowed domain. It stores only the filtered/formatted header in memory, exposes only names, closes the browser, and sets `authenticated`. Timeout/cancel/failure must close resources and leave the service retryable.

`resolve_cookie()` first returns the in-memory value. If the marker exists but the cache is empty, serialize a headless profile open, extract allowed cookies, close it, and return `CookieInfo(source="managed_browser")`; if no auth cookie exists return missing. It must never open a visible window.

`status_now()` is pure/local and used by health check. Async `status(probe_profile=False)` wraps the same snapshot, while `status(probe_profile=True)` may call `resolve_cookie()` when idle. `logout(confirm=False)` returns a safe `confirmation_required`; `confirm=True` cancels the owned task, closes the owned session, clears memory, then calls marker-guarded removal.

- [ ] **Step 5: Run focused and regression tests**

Run: `python -m pytest tests/test_managed_auth.py -q`

Expected: all state-machine tests pass without opening Chrome.

Run: `python -m pytest -q`

Expected: full suite passes.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/lanhu_design_mcp/managed_auth.py tests/test_managed_auth.py
git commit -m "feat: manage Lanhu browser login"
```

---

### Task 4: Resolve Managed Authentication Before Design Requests

**Files:**
- Modify: `src/lanhu_design_mcp/client.py`
- Modify: `src/lanhu_design_mcp/design_service.py`
- Modify: `tests/test_client_assets.py`
- Create: `tests/test_design_service_auth.py`

**Interfaces:**
- Produces: `LanhuAuthRequiredError.to_dict() -> {"status": "auth_required", "nextAction": "lanhu_auth_login"}`
- Produces: `DesignService._resolve_settings() -> Settings`
- Produces: `DesignService._client() -> LanhuClient`
- Consumes: `get_managed_auth().resolve_cookie()` and `.invalidate()` from Task 3.

- [ ] **Step 1: Write failing client authentication classification tests**

Add tests that prove only strong authentication evidence is classified:

```python
def test_auth_error_has_safe_structured_payload():
    error = LanhuAuthRequiredError()
    assert error.to_dict() == {"status": "auth_required", "nextAction": "lanhu_auth_login"}
    assert "cookie" not in str(error).lower()

def test_http_418_is_auth_failure():
    response = httpx.Response(418, request=httpx.Request("GET", "https://lanhuapp.com/api/project/images"))
    with pytest.raises(LanhuAuthRequiredError):
        raise_for_lanhu_auth(response)

def test_plain_403_is_not_assumed_to_be_expired_auth():
    response = httpx.Response(403, request=httpx.Request("GET", "https://lanhuapp.com/api/project/images"))
    raise_for_lanhu_auth(response)  # no auth exception; normal raise_for_status remains caller-owned
```

- [ ] **Step 2: Write failing service precedence and invalidation tests**

Create `tests/test_design_service_auth.py` using patched settings/auth/client factories:

```python
@pytest.mark.asyncio
async def test_explicit_cookie_beats_managed_and_legacy(monkeypatch):
    auth = AsyncMock()
    service = DesignService(managed_auth=auth)
    service.settings = explicit_settings("session=explicit")
    resolved = await service._resolve_settings()
    assert resolved.lanhu_cookie == "session=explicit"
    auth.resolve_cookie.assert_not_called()

@pytest.mark.asyncio
async def test_managed_cookie_beats_legacy_browser(monkeypatch):
    auth = AsyncMock()
    auth.resolve_cookie.return_value = CookieInfo(True, "session=managed", "managed_browser", None, ["session"])
    service = DesignService(managed_auth=auth)
    service.settings = missing_settings()
    with patch("lanhu_design_mcp.design_service.resolve_legacy_browser_cookie") as legacy:
        resolved = await service._resolve_settings()
    assert resolved.lanhu_cookie_source == "managed_browser"
    legacy.assert_not_called()

@pytest.mark.asyncio
async def test_asset_auth_error_is_not_swallowed_as_partial_success():
    service = DesignService(managed_auth=AsyncMock())

    @asynccontextmanager
    async def failing_client():
        client = AsyncMock()
        client.get_designs.side_effect = LanhuAuthRequiredError()
        yield client

    service._client = failing_client
    with pytest.raises(LanhuAuthRequiredError):
        await service.get_design_assets("https://lanhuapp.com/web/#/item/project/stage?pid=p1")
```

Also prove legacy fallback is last, missing auth produces the structured exception, DDS explicit override still wins, and all four design-service public operations use `_client()`.

- [ ] **Step 3: Run focused tests and confirm RED**

Run: `python -m pytest tests/test_client_assets.py tests/test_design_service_auth.py -q`

Expected: missing exception/helper and synchronous `DesignService` behavior failures.

- [ ] **Step 4: Add narrow client authentication detection**

In `client.py` add:

```python
class LanhuAuthRequiredError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Lanhu authentication is required; call lanhu_auth_login")

    def to_dict(self) -> dict[str, str]:
        return {"status": "auth_required", "nextAction": "lanhu_auth_login"}

def raise_for_lanhu_auth(response: httpx.Response) -> None:
    if response.status_code in {401, 418}:
        raise LanhuAuthRequiredError()
    location = response.headers.get("location", "")
    if response.is_redirect and "login" in location.lower():
        raise LanhuAuthRequiredError()
```

Call `raise_for_lanhu_auth(response)` before `raise_for_status()` for Lanhu/DDS API responses. Do not classify a plain `403` without login redirect or an observed Lanhu auth payload fixture.

- [ ] **Step 5: Add asynchronous settings/client resolution to `DesignService`**

Give `DesignService.__init__` an injectable managed-auth service for tests and call `get_settings(include_browser_fallback=False)`. Implement:

```python
async def _resolve_settings(self) -> Settings:
    if self.settings.lanhu_cookie:
        return self.settings
    info = await self.managed_auth.resolve_cookie()
    if not info.configured:
        info = resolve_legacy_browser_cookie()
    if not info.configured:
        raise LanhuAuthRequiredError()
    return get_settings(include_browser_fallback=False, lanhu_override=info)

@asynccontextmanager
async def _client(self):
    settings = await self._resolve_settings()
    try:
        async with LanhuClient(settings) as client:
            yield client
    except LanhuAuthRequiredError:
        if settings.lanhu_cookie_source == "managed_browser":
            self.managed_auth.invalidate()
        raise
```

Replace every direct `async with LanhuClient(self.settings)` with `async with self._client()`. In `get_design_assets`, add `except LanhuAuthRequiredError: raise` before the existing broad partial-success catch so expired authentication is never downgraded to a slice warning.

- [ ] **Step 6: Run focused and full tests**

Run: `python -m pytest tests/test_client_assets.py tests/test_design_service_auth.py tests/test_design_service_assets.py -q`

Expected: authentication and existing asset integration tests pass.

Run: `python -m pytest -q`

Expected: full suite passes.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/lanhu_design_mcp/client.py src/lanhu_design_mcp/design_service.py tests/test_client_assets.py tests/test_design_service_auth.py
git commit -m "feat: resolve managed Lanhu authentication"
```

---

### Task 5: Expose MCP Authentication Tools and CLI

**Files:**
- Modify: `src/lanhu_design_mcp/server.py`
- Create: `src/lanhu_design_mcp/cli.py`
- Create: `tests/test_server_auth.py`
- Create: `tests/test_cli.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces MCP tools: `lanhu_auth_login()`, `lanhu_auth_status(session_id=None)`, `lanhu_auth_logout(confirm=False)`.
- Produces CLI: `main(argv: Sequence[str] | None = None) -> int | None`.
- Preserves: `lanhu-design-mcp` with no arguments starts the existing MCP transport.

- [ ] **Step 1: Add failing MCP contract/security tests**

Test the functions directly with the singleton accessor patched:

```python
@pytest.mark.asyncio
async def test_auth_login_delegates_without_waiting():
    auth = AsyncMock()
    auth.start_login.return_value = {"status": "waiting_for_user", "sessionId": "id"}
    with patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth):
        result = await lanhu_auth_login()
    assert result == {"status": "waiting_for_user", "sessionId": "id"}

@pytest.mark.asyncio
async def test_health_is_local_and_lists_auth_tools():
    auth = Mock()
    auth.status_now.return_value = AuthSnapshot("missing", False, "missing", []).to_dict()
    with patch("lanhu_design_mcp.server.get_managed_auth", return_value=auth):
        result = await lanhu_health_check()
    assert "lanhu_auth_login" in result["tools"]
    auth.resolve_cookie.assert_not_called()
```

Also test status optional session ID, logout confirmation forwarding, and that a sentinel cookie value is absent from every serialized result.

- [ ] **Step 2: Add failing CLI dispatch tests**

Use injected/patched async service and server main:

```python
def test_no_args_starts_mcp(monkeypatch):
    run_server = Mock()
    monkeypatch.setattr("lanhu_design_mcp.server.main", run_server)
    assert cli.main([]) is None
    run_server.assert_called_once_with()

def test_auth_status_prints_safe_json(monkeypatch, capsys):
    auth = AsyncMock()
    auth.status.return_value = {"status": "authenticated", "authenticated": True, "cookieNames": ["session"]}
    monkeypatch.setattr(cli, "get_managed_auth", lambda: auth)
    assert cli.main(["auth", "status"]) == 0
    assert "session" in capsys.readouterr().out
```

Cover `auth login` waiting for terminal state in the CLI-owned event loop, `auth logout` requiring `--confirm`, invalid command exit code 2, and absence of secrets.

- [ ] **Step 3: Run focused tests and confirm RED**

Run: `python -m pytest tests/test_server_auth.py tests/test_cli.py -q`

Expected: missing tools/module or wrong entry-point behavior.

- [ ] **Step 4: Add thin MCP adapters and local health metadata**

In `server.py` add:

```python
@mcp.tool()
async def lanhu_auth_login() -> dict:
    return await get_managed_auth().start_login()

@mcp.tool()
async def lanhu_auth_status(session_id: str | None = None) -> dict:
    return await get_managed_auth().status(session_id, probe_profile=True)

@mcp.tool()
async def lanhu_auth_logout(confirm: bool = False) -> dict:
    return await get_managed_auth().logout(confirm)
```

Health uses `get_settings(include_browser_fallback=False)` plus a synchronous `status_now()` snapshot only; it must not call legacy browser extraction, Playwright, or the network. Add all three names to its tool list and a `managedAuth` object containing only safe state, source, cookie names, and profile availability—not the full profile path if unnecessary. `server.main()` also uses `get_settings(include_browser_fallback=False)` for transport/data-directory configuration; legacy browser extraction occurs only in the asynchronous design-request credential chain.

- [ ] **Step 5: Implement the CLI without duplicating authentication logic**

`cli.main` parses only:

```text
[]
["auth", "login"]
["auth", "status"]
["auth", "logout", "--confirm"]
```

No arguments import and call `server.main()`. Auth commands run the singleton methods with `asyncio.run`. CLI login calls `start_login()` then `wait_for_terminal_state()` so the CLI process remains alive while Chrome is open; MCP login remains non-blocking. Print only `json.dumps(result, ensure_ascii=False)` and return `0` for authenticated/logout success, `1` for cancelled/timeout/dependency/profile failures, `2` for usage errors.

- [ ] **Step 6: Change only the package entry point and optional dependency**

In `pyproject.toml`:

```toml
[project.optional-dependencies]
auth = [
  "playwright>=1.50.0",
]
dev = [
  "pytest>=7.4.0",
  "pytest-asyncio>=0.21.0",
]

[project.scripts]
lanhu-design-mcp = "lanhu_design_mcp.cli:main"
```

Do not modify or stage `uv.lock` because it has pre-existing unrelated source-index changes. Verify packaging with pip metadata instead of `uv sync`.

- [ ] **Step 7: Run focused, full, and package tests**

Run: `python -m pytest tests/test_server_auth.py tests/test_cli.py -q`

Expected: all MCP/CLI tests pass.

Run: `python -m pytest -q`

Expected: full suite passes.

Run: `python -m pip install --no-deps -e .`

Expected: editable install succeeds and `lanhu-design-mcp --help` or an invalid CLI usage exits without importing Playwright.

- [ ] **Step 8: Commit Task 5 without the dirty lock file**

```bash
git add src/lanhu_design_mcp/server.py src/lanhu_design_mcp/cli.py tests/test_server_auth.py tests/test_cli.py pyproject.toml
git commit -m "feat: expose Lanhu authentication commands"
```

---

### Task 6: Publish the Automatic Login Workflow

**Files:**
- Modify: `README.md` (preserve and include the pre-existing unstaged CAgent/cc-switch additions rather than discarding them)
- Modify: `server.json`
- Create: `docs/manual-auth-smoke-test.md`
- Test: `tests/test_server_auth.py`

**Interfaces:**
- Documents: `pip install 'lanhu-design-mcp[auth]'`, MCP/CLI login/status/logout, precedence, security, and fallback.
- Publishes: Registry metadata that recommends the auth extra without requiring a secret environment variable.

- [ ] **Step 1: Add a failing metadata/documentation contract test**

Extend `tests/test_server_auth.py` with repository-root reads:

```python
def test_published_docs_describe_managed_login():
    readme = Path("README.md").read_text(encoding="utf-8")
    metadata = json.loads(Path("server.json").read_text(encoding="utf-8"))
    assert "lanhu-design-mcp[auth]" in readme
    assert "lanhu_auth_login" in readme
    assert metadata["packages"][0]["identifier"] == "lanhu-design-mcp"
    assert metadata["config"]["environmentVariables"]["LANHU_COOKIE"]["isRequired"] is False
```

- [ ] **Step 2: Run the contract and confirm RED**

Run: `python -m pytest tests/test_server_auth.py::test_published_docs_describe_managed_login -q`

Expected: README lacks the new installation/login workflow.

- [ ] **Step 3: Update README while preserving existing user changes**

Make managed login the recommended interactive path:

```bash
pip install 'lanhu-design-mcp[auth]'
lanhu-design-mcp auth login
lanhu-design-mcp auth status
```

Document that the login window uses a dedicated local Chrome profile, ordinary tools never open Chrome, and expiry returns `auth_required`. Keep the existing CAgent file, `LANHU_COOKIE_FILE`, `LANHU_COOKIE`, and legacy `AUTO_BROWSER_COOKIES` sections as advanced/CI/fallback paths. Update precedence and available-tool lists. Do not show real cookie values.

Because README already has unstaged CAgent/cc-switch additions, save `git diff -- README.md` before editing, inspect the combined diff afterward, and ensure those lines remain. Construct and apply an index-only patch containing only the new managed-authentication README hunks; leave the pre-existing CAgent/cc-switch hunks unstaged. Do not use `git add README.md`, because that would take ownership of the user's unrelated changes.

- [ ] **Step 4: Update Registry metadata and smoke-test runbook**

In `server.json`, keep `LANHU_COOKIE` optional/secret and change `AUTO_BROWSER_COOKIES` description/default so legacy database extraction is not presented as the primary flow. Add package metadata or description text indicating that `[auth]` enables local Chrome login; do not invent unsupported Registry schema fields. Validate the JSON against the existing schema shape.

Create `docs/manual-auth-smoke-test.md` with explicit macOS/Linux/Windows checklist:

```text
1. Install core package and prove explicit-cookie mode starts without Playwright.
2. Install [auth] on a machine with system Chrome.
3. Run auth login and complete Lanhu sign-in.
4. Confirm status returns names only and no values.
5. Restart MCP and retrieve a real design without cookie import.
6. Clear/expire the Lanhu session and confirm auth_required.
7. Run confirmed logout and prove only the marked managed profile is removed.
```

Mark a platform supported in release documentation only after its checklist is actually executed.

- [ ] **Step 5: Run documentation, metadata, regression, and secret scans**

Run: `python -m pytest tests/test_server_auth.py -q`

Expected: metadata/documentation contract passes.

Run: `python -m json.tool server.json >/dev/null`

Expected: valid JSON.

Run: `python -m pytest -q`

Expected: full suite passes.

Run: `grep -R -nE 'session=[^.<x*f]|user_token=[^.<x*f]' README.md docs src tests --exclude='2026-07-13-cagent-cookie-config-design.md' || true`

Expected: no credential-looking literal introduced by this feature; inspect every match manually because fake test values may intentionally match.

- [ ] **Step 6: Perform the available real smoke test**

On the current macOS workstation, install the auth extra into the project environment without touching `uv.lock`, run `lanhu-design-mcp auth login`, complete login, restart the command, and call a real design tool. Record only status, cookie names, and HTTP/result success—not cookie values—in the task report. Do not claim Linux or Windows support until those platform checks are run.

- [ ] **Step 7: Commit only intended publication files**

```bash
git add server.json docs/manual-auth-smoke-test.md tests/test_server_auth.py
# Apply the reviewed managed-auth-only README patch to the index with:
git apply --cached /tmp/lanhu-managed-auth-readme.patch
git commit -m "docs: publish managed Lanhu login workflow"
```

Create `/tmp/lanhu-managed-auth-readme.patch` as an explicit diff against `HEAD:README.md` containing only the managed-login installation, precedence, tool-list, and troubleshooting hunks. Before committing, run `git diff --cached -- README.md` and confirm the CAgent clipboard-import and cc-switch blocks are absent from the staged diff while still present in `git diff -- README.md`.

- [ ] **Step 8: Final scope and history verification**

Run: `git status --short`

Expected: only the user's pre-existing unrelated changes remain; `uv.lock` is still unstaged.

Run: `git log --oneline -8`

Expected: six small feature commits after the design/plan commits.

Run: `python -m pytest -q`

Expected: complete suite passes with no browser launched by automated tests.

---

## CCB Execution and Review Gates

Execute one task per CCB packet. Every packet must repeat its objective, exact allowed files, forbidden changes, required plan section, exact verification commands, and requested completion report. After every result, Codex must inspect the actual diff and commit, confirm no cookie values or unrelated files were staged, rerun the focused tests, and only then issue the next packet.

Task 3 and Task 4 are authentication/security review gates: do not proceed if raw exception text can reach MCP output, if logout can remove an unmarked directory, if a plain `403` is treated as expiry, or if `get_design_assets` swallows authentication failure as `partial_success`.

Task 6 is a release gate: automated tests plus the current-platform real smoke test are required before describing the feature as working. Linux and Windows stay documented as unverified checklists until independently executed.
