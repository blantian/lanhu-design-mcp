# Lanhu Managed Browser Authentication Design

## Goal

Replace the published MCP's manual clipboard-to-cookie workflow with a local, one-time interactive Lanhu login whose authenticated browser profile can be reused automatically. Existing file and environment-variable authentication must remain compatible.

## Scope

This design adds a managed local Chrome profile, an explicit authentication lifecycle, and structured authentication errors. It does not add a remote authentication proxy, attempt to automate passwords, QR codes, CAPTCHA, or SSO, and does not remove the existing cookie-file, environment-variable, or browser-database compatibility paths.

The first login remains user-interactive. "Automatic authentication" means that after this one-time login, normal MCP calls reuse the local session until Lanhu requires the user to sign in again.

## Chosen Approach

Use Playwright with the installed Google Chrome channel and a dedicated persistent browser profile. The profile must not be Chrome's default profile. This isolates MCP state from the user's normal browser, avoids reading or decrypting the default browser cookie database, and is compatible with Chrome's restrictions on remote debugging of default profiles.

Alternatives were rejected for the MVP:

- Direct CDP management would duplicate browser discovery, process, port, and WebSocket lifecycle logic already supplied by Playwright.
- A Chrome extension plus native messaging could reuse the user's existing Chrome login more seamlessly, but requires a second published artifact, broad browser permissions, and per-platform native-host installation. It remains a possible second phase.
- Direct Chrome and Safari cookie-database access is retained only as a legacy fallback because encryption, profile layout, file locking, and Safari binary-cookie handling are platform- and browser-version-sensitive.
- A remote proxy would have to receive users' Lanhu session credentials. It is outside this local-first security model.
- OAuth or device authorization is outside scope unless Lanhu publishes and supports the required authorization endpoints.

## Architecture

### Authentication module

A new focused module owns the managed browser profile and login lifecycle. It must not depend on `DesignService` or Lanhu design parsing.

Its public responsibilities are:

- resolve a platform-appropriate application data directory;
- start at most one interactive login session;
- report the login session state without exposing credentials;
- read only cookies applicable to Lanhu domains from the managed context;
- format those cookies for the existing HTTP client;
- clear the managed authentication state on explicit logout;
- turn expected failures into stable, structured status values.

The module uses Playwright lazily. Importing or starting the MCP server must not launch a browser or require Playwright unless the managed-profile authentication path is used.

### Managed profile

The default profile directory is resolved with platform-specific application-data conventions rather than stored inside the repository. The logical application name is `lanhu-design-mcp`, and the profile is a child named `browser-profile`.

On POSIX systems, newly created authentication directories must be owner-only (`0700`). The module must reject a configured profile path that resolves to Chrome's ordinary default profile. It must never delete an arbitrary user-supplied directory; logout may delete only a profile carrying a marker created by this package.

Chrome is launched through Playwright with `channel="chrome"`, the dedicated `user_data_dir`, and a visible window for interactive login. An installed system Chrome is the MVP browser requirement; the package does not automatically download another browser binary.

### Authentication state machine

One process maintains at most one login session:

```text
missing -> starting -> waiting_for_user -> authenticated
                     -> cancelled
                     -> timed_out
                     -> failed
authenticated -> expired -> waiting_for_user
```

`lanhu_auth_login` is non-blocking from the MCP caller's perspective. It starts the browser worker and returns a generated opaque `sessionId` plus state `starting` or `waiting_for_user`. Repeated calls while a session is active return the same session identifier and do not open additional windows.

`lanhu_auth_status` reports the current state. It may inspect the active browser context or managed profile and perform an authentication validation request, but it never returns cookie values. Once login is detected and validated, the browser is closed cleanly and the state becomes `authenticated`.

The login worker has a default five-minute deadline. Closing the window before authentication produces `cancelled`; exceeding the deadline produces `timed_out`. Neither condition modifies legacy cookie sources.

### Cookie resolution

The existing precedence remains stable for power users and CI:

1. Explicit `LANHU_COOKIE_FILE`.
2. Existing `~/.config/cagent/lanhu/cookie.txt`.
3. `LANHU_COOKIE`.
4. Managed Chrome profile.
5. Existing default-browser database extraction when `AUTO_BROWSER_COOKIES` enables it.
6. Missing authentication.

The current synchronous configuration resolver is split into explicit sources (file and environment) and the legacy browser-database fallback. Managed-profile extraction is asynchronous because Playwright must launch Chrome to access the persistent context; it must not be called from synchronous `get_settings()` while an MCP tool event loop is running.

Before constructing an authenticated `LanhuClient`, `DesignService` first uses an explicit configured cookie when present. When that result is missing, it awaits the managed authentication service, which returns a `CookieInfo`-compatible result with source `managed_browser`. Only when that is unavailable may it invoke the legacy browser-database fallback. The resulting request-level Lanhu cookie is also used as the DDS fallback exactly as the configured Lanhu cookie is today. The design-service integration must remain behind a small client/cookie factory so authentication mechanics do not spread through design parsing methods.

The MCP must not keep a browser open for every design request. On the first managed-authenticated request in a process, it launches the profile through the asynchronous browser boundary, extracts the current Lanhu cookie header, closes the browser, and caches the header in process memory. Later requests reuse that in-memory value. If Lanhu rejects it as expired, the cache is discarded. Browser access is lazy and serialized to avoid profile locking.

## MCP and CLI Interfaces

### `lanhu_auth_login`

Input: no required parameters.

Successful start response:

```json
{
  "status": "waiting_for_user",
  "sessionId": "opaque-id",
  "message": "Complete sign-in in the opened Chrome window."
}
```

If Playwright or Chrome is unavailable, it returns `dependency_missing` with a safe installation hint. It must not install software automatically.

### `lanhu_auth_status`

Input: optional `sessionId`.

Response fields are `status`, `authenticated`, `source`, `cookieNames`, and an optional safe `message`. Allowed status values are `missing`, `starting`, `waiting_for_user`, `authenticated`, `expired`, `cancelled`, `timed_out`, `dependency_missing`, `profile_locked`, and `failed`.

No response includes a cookie value, complete request header, browser storage state, password, token, or raw exception that might contain one.

### `lanhu_auth_logout`

Input: `confirm: true`.

The operation stops an active managed login and removes only the package-owned managed profile and in-memory managed cookie. It does not delete `LANHU_COOKIE_FILE`, the CAgent cookie file, environment variables, or any normal Chrome profile. Without explicit confirmation it performs no deletion.

### CLI

The existing `lanhu-design-mcp` entry point gains an `auth` command family while retaining no-argument server startup:

```text
lanhu-design-mcp auth login
lanhu-design-mcp auth status
lanhu-design-mcp auth logout
```

CLI and MCP tools call the same authentication service; neither duplicates browser logic.

## Normal Tool Behavior

`lanhu_health_check` remains local-only and adds the three authentication tool names plus managed-profile status metadata. It must not launch Chrome or access Lanhu over the network.

When no cookie is available, normal design tools return or raise a structured authentication error whose serializable detail contains:

```json
{
  "status": "auth_required",
  "nextAction": "lanhu_auth_login"
}
```

When Lanhu rejects a previously accepted session, the client marks the managed credential invalid for the process and produces the same `auth_required` action. It must not automatically open a visible browser during an unrelated design call.

Authentication failure detection is based on the current Lanhu client's observed HTTP and payload behavior, covered by fixtures. A generic `403` alone must not be assumed to mean expired authentication if Lanhu uses it for resource authorization; validation and error payload evidence must distinguish those cases.

## Security and Privacy

- All credential material remains on the machine running the stdio MCP.
- Only cookies matching an explicit Lanhu domain allowlist are extracted.
- Cookie values and browser storage state are forbidden in MCP responses, logs, exception messages, test snapshots, telemetry, and documentation examples.
- Cookie names may be returned for diagnostics.
- The dedicated profile and any optional cookie cache are excluded from source control by location and permissions.
- A persistent Playwright `storage_state` JSON file is not written for the MVP.
- Browser and profile operations are serialized with a process-local lock. A locked profile produces `profile_locked`; the MCP must not kill unrelated Chrome processes.
- Logout is constrained by a package-owned marker and explicit confirmation.
- Tests use fake cookies and temporary profile directories only.

## Packaging

> **Post-design amendment (2026-07-18):** The official MCP Registry PyPI package model cannot express extras. Therefore `playwright>=1.50.0` is a core package dependency. Its import remains lazy (only imported inside `PlaywrightBrowserBackend.open()`). No browser binary or Chromium is downloaded automatically; an installed system Google Chrome is required for managed login. The original optional-extra design was simplified to meet the Registry constraint.

Core installation bundles the Playwright Python library lazily. Explicit file and environment-variable authentication work without any browser or Playwright import.

```text
pip install --upgrade lanhu-design-mcp
```

No installation step runs `playwright install`, modifies the user's browser, installs an extension, or launches Chrome.

Manual `LANHU_COOKIE_FILE` and `LANHU_COOKIE` instructions remain available for CI, headless machines, and users without Chrome.

## Error Handling

- Missing Python dependency: `dependency_missing` with safe upgrade message (`pip install --upgrade lanhu-design-mcp`).
- Missing system Chrome: `dependency_missing`, naming Chrome as the missing dependency and retaining manual-cookie guidance.
- Profile locked: `profile_locked`; do not terminate another browser process.
- User closes login window: `cancelled`.
- Five-minute deadline: `timed_out`, with a new login allowed afterward.
- Concurrent login requests: return the active session rather than create a second worker.
- Browser or validation exception: sanitize it, set `failed`, close owned resources, and allow retry.
- Invalid legacy file/env cookie: report authentication required but never overwrite or delete the configured source.

## Testing Strategy

Unit tests mock the Playwright boundary and cover profile selection, directory permissions, domain filtering, cookie formatting, state transitions, timeout, cancellation, concurrency, sanitization, marker-guarded logout, and absence of secret values in responses.

Configuration tests cover the exact precedence chain and DDS inheritance, including environments where Playwright is not installed. Server contract tests cover the three MCP tools, the health-check additions, non-blocking login responses, and structured `auth_required` errors.

CLI tests cover no-argument MCP startup compatibility and all three `auth` subcommands without launching a real browser.

A manual smoke test is required on macOS, Linux, and Windows before declaring cross-platform release support:

1. Install the package on a machine with Chrome.
2. Start login and authenticate to Lanhu.
3. Confirm status becomes authenticated without exposing cookie values.
4. Restart the MCP process and retrieve a real design without manual cookie import.
5. Expire or clear the Lanhu session and confirm the next design call returns `auth_required`.
6. Log out and confirm only the managed profile is removed.

## Acceptance Criteria

- A new Registry/PyPI user with Chrome can authenticate through one visible login without copying cookies.
- Restarting the MCP reuses the managed session until Lanhu invalidates it.
- Existing file, CAgent file, environment, and DDS fallback behavior remains compatible.
- Ordinary design calls never unexpectedly open a browser.
- MCP and CLI outputs never expose credential values.
- Missing dependencies, cancellation, timeout, profile locking, and expiry are actionable and retryable.
- Core installation starts and uses explicit cookie sources (Playwright import is lazy; explicit-source modes never trigger it).
- The full automated test suite passes, and platform-specific release claims are limited to platforms that completed the manual smoke test.

## Deferred Work

- Chrome extension and native messaging integration for reusing the user's ordinary Chrome profile.
- Automatic installation of browsers or extensions.
- Remote credential storage or hosted authentication proxy.
- OAuth or device flow unless Lanhu provides a supported public authorization integration.
