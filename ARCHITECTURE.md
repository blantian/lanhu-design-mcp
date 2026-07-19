# lanhu-design-mcp v0.2.0 架构设计

## 目标

v0.2.0 对认证、设计处理和测试代码按职责重组，清除旧认证方案、历史任务文档、生成物和无引用代码。重构不改变 MCP 工具、CLI、stdio 传输或返回数据契约。

## 生产代码结构

```text
src/lanhu_design_mcp/
├── __init__.py
├── cli.py
├── server.py
├── client.py
├── auth/
│   ├── __init__.py
│   ├── models.py
│   ├── profile.py
│   ├── validator.py
│   ├── browser.py
│   └── manager.py
└── design/
    ├── __init__.py
    ├── url.py
    ├── units.py
    ├── ir.py
    ├── assets.py
    └── service.py
```

### 顶层模块

- `server.py`：声明八个 MCP 工具并以前台 stdio 启动。
- `cli.py`：启动服务器，分派认证命令。
- `client.py`：访问蓝湖 HTTP API，分类认证响应并管理请求生命周期。

### 认证模块

- `auth/models.py`：认证状态、凭据模型、客户端设置和安全错误类型。
- `auth/profile.py`：托管 Profile 路径、所有权、Cookie 过滤与 Header 构造。
- `auth/validator.py`：验证蓝湖账号会话。
- `auth/browser.py`：Playwright 后端、浏览器会话协议和资源清理。
- `auth/manager.py`：认证状态机、并发锁、Cookie 缓存、登录、探测、登出和单例。

依赖方向固定为：

```text
auth.models
    ↓
auth.profile / auth.validator / auth.browser
    ↓
auth.manager
```

低层认证模块不得导入 `auth.manager`，避免循环依赖。

### 设计模块

- `design/url.py`：解析蓝湖项目和设计 URL。
- `design/units.py`：转换 Web、Android、iOS 和小程序单位。
- `design/ir.py`：将 DDS Schema 转为 DesignIR。
- `design/assets.py`：提取 Sketch、Figma、Photoshop 切图和倍率资源。
- `design/service.py`：组合认证、API 客户端、设计分析和资产输出。

## 测试结构

```text
tests/
├── auth/
│   ├── test_profile.py
│   ├── test_validator.py
│   ├── test_browser.py
│   └── test_manager.py
├── design/
│   ├── test_url.py
│   ├── test_units.py
│   ├── test_ir.py
│   ├── test_assets.py
│   ├── test_service_assets.py
│   └── test_service_auth.py
├── contracts/
│   ├── test_product.py
│   ├── test_source_documentation.py
│   └── test_release_workflow.py
├── test_client.py
├── test_cli.py
└── test_server.py
```

保留行为、安全、MCP 契约和发布测试。删除只约束旧文档存在的测试，不为旧内部 Python 模块路径保留兼容测试。

## 兼容边界

v0.2.0 必须保持：

- 八个 MCP 工具名称、参数和返回数据结构。
- stdio-only 传输和现有 cc-switch 配置。
- `auth login`、`auth status`、`auth logout --confirm` CLI 行为。
- macOS-only 托管 Chrome Profile 路径和安全边界。
- Sketch、Figma、Photoshop 切图、去重和单位转换行为。
- PyPI 包名 `lanhu-design-mcp`。
- MCP Registry 名称 `io.github.blantian/lanhu-design-mcp`。
- 已发布的 v0.1.0、v0.1.1 标签不可变。

内部 Python 模块路径不是公共接口，允许在 v0.2.0 中改变，不保留转发兼容层。

## 仓库清理

- 删除 `docs/`、`prompt/` 和无引用的 `prompts.py`。
- `.gitignore` 增加 `.ccb/`、`.claude/`、`.superpowers/`。
- 删除本地旧 `.env`、旧 `dist/`、生成的 `data/`、缓存、egg-info 和 `.DS_Store`。
- 保留 `.venv/`、活动 `.ccb/`、`.claude/` 和现有 worktree。
- 保留 `README.md`、`CHANGELOG.md`、`server.json`、发布工作流和必要测试。

README 仅保留项目简介、功能、系统要求、安装、首次登录、MCP 配置、工具、使用规范、常见错误、开发验证和许可证。

## 实施顺序

1. 拆分认证模型、Profile、验证器和浏览器后端。
2. 迁移认证状态机并验证认证测试。
3. 重组设计模块，只调整导入路径。
4. 更新服务器、CLI、客户端和测试导入。
5. 删除旧模块、旧文档、死代码和本地生成物。
6. 精简 README，更新 `.gitignore`。
7. 更新版本、CHANGELOG、锁文件和发布元数据。

每一步先保持行为测试通过，再进入下一步。

## v0.2.0 发布门槛

发布前必须通过：

- 完整 pytest 和 Ruff。
- wheel、sdist 构建及 Twine 检查。
- `mcp-publisher validate` 和 zizmor。
- 公共 wheel 隔离安装、CLI 启动和八个 MCP 工具发现。
- 托管认证探测、真实蓝湖项目获取和细粒度切图验证。

验证通过后才允许推送 `main`、创建不可变 `v0.2.0` 标签和 GitHub Release。随后验证 PyPI Trusted Publishing、PyPI Integrity、公共 PyPI 全新安装和 MCP Registry `0.2.0`。任一发布门槛失败都停止后续发布操作。
