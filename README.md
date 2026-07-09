# Lanhu Design MCP

Android-first MCP server for reading Lanhu design drafts and exporting UI restoration context for Codex, Claude Code, Cursor, and other coding agents.

## What It Does

- Reads Lanhu design project URLs.
- Lists design images.
- Fetches Lanhu DDS schema for a selected design.
- Normalizes design nodes into a compact Agent-friendly DesignIR.
- Converts page and node metrics for `web`, `android`, `ios`, and `wechat_miniprogram`.
- Defaults to Android output (`dp`) for Android TV and app development.

## Configuration

Copy `.env.example` to `.env` and fill in your Lanhu cookie:

```bash
LANHU_COOKIE="session=...; tfstk=..."
```

Optional variables:

```bash
DDS_COOKIE=""              # defaults to LANHU_COOKIE
DATA_DIR="./data"
HTTP_TIMEOUT=30
MCP_TRANSPORT=stdio        # stdio or http
SERVER_HOST="0.0.0.0"
SERVER_PORT=8000
```

## MCP stdio

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "/bin/bash",
      "args": ["/Users/buluesky/mcp/lanhu-design-mcp/run-stdio.sh"],
      "env": {
        "LANHU_COOKIE": "session=...; tfstk=..."
      }
    }
  }
}
```

## Tools

- `lanhu_get_designs(url)`
- `lanhu_analyze_design(url, design_name_or_index = null, target_platform = "android")`
- `lanhu_get_design_assets(url, design_name_or_index = null, target_platform = "android")`
- `lanhu_export_ui_context(url, design_name_or_index = null, target_platform = "android")`

## Platform Units

- Web: `px`
- Android: `dp = px / 2` based on verified Lanhu behavior for 1920x1080 -> 960x540.
- iOS: default `pt = px / 2`, configurable later after project-specific verification.
- WeChat Mini Program: default `rpx = px * 750 / design_width`.
