# Lanhu Design MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Android-first MCP server that lets coding agents read Lanhu design specs and consume platform-adjusted UI restoration context.

**Architecture:** Create a small Python/FastMCP package that wraps Lanhu Web/DDS endpoints, normalizes design schema into a compact DesignIR, and exposes a few MCP tools for design listing, analysis, assets, and UI context export. Keep the old monolithic server untouched and migrate only the design-related minimum.

**Tech Stack:** Python 3.10+, FastMCP, httpx, python-dotenv, pytest.

---

### Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `.env.example`
- Create: `run-stdio.sh`
- Create: `src/lanhu_design_mcp/__init__.py`

- [x] Create package metadata and runtime entry point.
- [x] Document environment variables and MCP client setup.

### Task 2: Core Models and Unit Conversion

**Files:**
- Create: `src/lanhu_design_mcp/platform_units.py`
- Create: `tests/test_platform_units.py`

- [x] Define `TargetPlatform` and conversion helpers.
- [x] Test Web px, Android dp, iOS pt, and WeChat rpx conversion.

### Task 3: URL Parser

**Files:**
- Create: `src/lanhu_design_mcp/url_parser.py`
- Create: `tests/test_url_parser.py`

- [x] Parse `stage` and `detailDetach` Lanhu URLs.
- [x] Preserve `pid`, `tid`, `image_id`, and `docId`.

### Task 4: Lanhu Client

**Files:**
- Create: `src/lanhu_design_mcp/client.py`

- [x] Implement authenticated httpx client.
- [x] Fetch design list from `/api/project/images`.
- [x] Resolve latest version from `/api/project/multi_info`.
- [x] Fetch DDS schema from `/api/dds/image/store_schema_revise`.
- [x] Fetch Sketch JSON from `/api/project/image`.

### Task 5: DesignIR and Service Layer

**Files:**
- Create: `src/lanhu_design_mcp/design_ir.py`
- Create: `src/lanhu_design_mcp/design_service.py`
- Create: `tests/test_design_ir.py`

- [x] Convert raw schema into compact nodes with names, text, styles, and bounds.
- [x] Resolve design by name, index, or URL `image_id`.
- [x] Return Android-first platform-adjusted page and node metrics.

### Task 6: MCP Tools

**Files:**
- Create: `src/lanhu_design_mcp/server.py`
- Create: `src/lanhu_design_mcp/config.py`
- Create: `src/lanhu_design_mcp/prompts.py`

- [x] Expose `lanhu_get_designs`.
- [x] Expose `lanhu_analyze_design`.
- [x] Expose `lanhu_get_design_assets`.
- [x] Expose `lanhu_export_ui_context`.

### Task 7: Verification

**Files:**
- Test: `tests/`

- [x] Run unit tests.
- [ ] Run real Lanhu smoke test with user Cookie for `少儿模式`.
- [ ] Confirm Android output reports `960 x 540 dp`.
