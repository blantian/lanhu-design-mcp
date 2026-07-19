# Manual Auth Smoke Test

Cross-platform manual smoke test for managed Lanhu authentication. Execute on each target platform before declaring support.

## Prerequisites

- System Google Chrome installed (no Chromium/Playwright browser download).
- `pip install lanhu-design-mcp` with `playwright>=1.50.0` available.
- Active Lanhu account accessible in Chrome.

## Steps

1. **Install core package and verify explicit-cookie mode starts without Playwright import.**
   ```bash
   pip install lanhu-design-mcp
   LANHU_COOKIE="session=test" lanhu-design-mcp --help
   ```
   Expected: usage prints; no Playwright import error.

2. **Run auth login and complete Lanhu sign-in.**
   ```bash
   lanhu-design-mcp auth login
   ```
   Expected: Chrome opens at lanhuapp.com. Sign in manually. CLI exits 0.

3. **Confirm status returns names only and no credential values.**
   ```bash
   lanhu-design-mcp auth status
   ```
   Expected: JSON output with `"authenticated": true`, `"cookieNames"` list. No cookie values or `=`-delimited headers in output.

4. **Restart MCP and retrieve a real design without cookie import.**
   Use the MCP `lanhu_get_designs` tool with any valid project URL.
   Expected: design list returns successfully; no browser opens; no manual cookie copy needed.

5. **Expire or clear Lanhu session and confirm auth_required.**
   Clear Lanhu session cookies in the managed Chrome profile, or wait for natural expiry.
   Expected: next design call returns structured `{"status": "auth_required", "nextAction": "lanhu_auth_login"}`.

6. **Run confirmed logout and verify only the managed profile is removed.**
   ```bash
   lanhu-design-mcp auth logout --confirm
   ```
   Expected: CLI exits 0 with `"status": "logged_out"`. Only the managed profile path listed below is removed. CAgent cookie file, env vars, and ordinary Chrome profiles are untouched.

## Platform-Specific Paths

| Platform | Managed profile location |
|---|---|
| macOS | `~/Library/Application Support/lanhu-design-mcp/browser-profile` |
| Linux | `~/.local/share/lanhu-design-mcp/browser-profile` |
| Windows | `%LOCALAPPDATA%\lanhu-design-mcp\browser-profile` |

## Results

| Platform | Status | Notes |
|---|---|---|
| macOS | Passed (non-destructive) | 2026-07-19: interactive Chrome login, new-process profile reuse, real design and fine-grained asset retrieval, and PNG/SVG HTTP 200 verified. Expiry and confirmed logout were not executed so the reusable profile remains available; their lifecycle paths are covered by automated tests. |
| Linux | Unverified | Checklist not yet executed |
| Windows | Unverified | Checklist not yet executed |

## Security

- Do NOT include cookie values, signed URLs, or raw HTTP headers in test notes.
- Document only cookie names, status values, and hostnames.
- Verify `status` and `logout` responses never contain credential material.
