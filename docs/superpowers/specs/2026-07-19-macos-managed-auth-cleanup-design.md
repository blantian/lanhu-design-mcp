# macOS 单一托管认证与 v0.1.1 正式发布设计

## 背景

`lanhu-design-mcp` 已具备细粒度切图、托管 Chrome 登录、会话验证和 PyPI Trusted Publishing 工作流。现有 `v0.1.0` 标签早于发布工作流，因此对应 GitHub Release 不会触发 Actions；该标签保持不可变，也不发布到 PyPI。

`v0.1.1` 作为第一个 PyPI 版本，目标是把产品收敛为面向普通 macOS 用户的单一路径：安装包、登录蓝湖、配置 MCP、调用工具。旧 Cookie 文件、环境变量、浏览器数据库读取和本地开发脚本不再作为兼容路径保留。

## 目标

- 仅正式支持 macOS、Google Chrome 和 Python 3.10+。
- 蓝湖认证只使用 MCP 管理的专用 Chrome Profile。
- MCP 服务只提供 stdio 启动方式。
- 删除旧认证、旧配置、无用代码、重复测试和过时发布资料。
- `src/lanhu_design_mcp/` 中每个函数和方法都有简洁中文 docstring。
- 把现有英文代码注释改为中文，并补充必要的安全与状态说明。
- 将 README 重写为可直接用于 GitHub 和 PyPI 的正式 `v0.1.1` 项目首页。
- 保持细粒度切图、平台单位转换、会话安全和八个 MCP 工具的现有行为。
- 通过新标签 `v0.1.1` 触发已经配置好的 PyPI Trusted Publishing。

## 非目标

- 不支持或宣称支持 Linux、Windows。
- 不保留 Cookie 文件、Cookie 环境变量、CAgent Cookie 或默认浏览器数据库兼容层。
- 不保留 HTTP MCP 传输模式。
- 不重新设计蓝湖 API、DesignIR 或切图数据结构。
- 不移动、删除或重建 `v0.1.0` 标签。
- 不清理历史 plans、specs、prompt 或 CCB 过程资料。
- 不为了静态分析结果而删除仍属于公开接口或协议要求的代码。

## 运行架构

唯一认证链为：

```text
CLI / MCP 工具
    -> ManagedBrowserAuth
    -> macOS 专用 Chrome Profile
    -> 蓝湖账户接口会话验证
    -> LanhuClient
```

首次使用时，用户运行 `lanhu-design-mcp auth login` 或调用 `lanhu_auth_login`。登录由用户在可见 Chrome 窗口中完成；程序不填写密码、验证码、二维码或 SSO 信息。

登录成功后，Cookie 只保存在 MCP 拥有的 Chrome Profile 和进程内缓存中。普通设计工具只进行无界面的 Profile 读取，不主动打开可见浏览器。会话过期时统一抛出 `LanhuAuthRequiredError`，并返回 `auth_required` 指引。

DDS 请求复用同一份已经验证的蓝湖会话，不再支持独立 DDS Cookie。

## 平台边界

托管认证在运行时显式检查 `platform.system() == "Darwin"`。非 macOS 环境返回固定、安全、不含异常原文的 `unsupported_platform` 状态，不尝试启动浏览器，也不创建 Profile。

macOS Profile 使用固定的用户级应用支持目录，并继续满足以下安全约束：

- Profile 目录带所有权标记。
- 目录权限仅限当前用户。
- 删除操作只允许作用于带直接子级标记的 MCP 专用目录。
- 不接受 Chrome 默认 Profile 路径或符号链接目标。
- 浏览器操作由锁串行化。
- Cookie 值不进入状态输出、日志或异常信息。
- 会话必须通过蓝湖账户接口验证后才视为已认证。

## 配置收敛

`config.py` 不再发现凭据，只保留客户端运行所需的最小类型和从已验证会话构建客户端设置的函数。

删除以下配置来源和字段：

- `LANHU_COOKIE_FILE`
- `LANHU_COOKIE`
- `AUTO_BROWSER_COOKIES`
- `DDS_COOKIE_FILE`
- `DDS_COOKIE`
- `DATA_DIR`
- `MCP_TRANSPORT`
- `SERVER_HOST`
- `SERVER_PORT`

HTTP 请求超时保留为代码内默认值，不作为面向用户的配置入口。MCP 入口始终调用 `mcp.run(transport="stdio")`。

健康检查只返回 SDK、工具列表和托管认证快照，不再返回 Cookie 文件、Cookie 名称或旧来源字段。

## 删除范围

删除已被单一路径替代的文件：

- `src/lanhu_design_mcp/browser_cookies.py`
- `tools/get_cookies.py`
- `tools/setup_cookies.py`
- `tools/test_mcp_connection.py`
- `run-stdio.sh`
- `.env.example`

删除已经过时且未纳入 Git 的本地发布资料：

- `PUBLISHING_GUIDE.md`
- `PUBLISHING_CHECKLIST.md`
- `publish.sh`

从 `pyproject.toml` 删除只服务旧浏览器 Cookie 解密或 `.env` 加载的依赖：

- `python-dotenv`
- `cryptography`

清理所有被上述删除产生的 import、字段、分支、测试夹具和文档引用。静态分析发现的既有无用 import 一并删除。

## 中文注释规范

作用范围是 `src/lanhu_design_mcp/` 下的生产代码：

- 每个 `FunctionDef` 和 `AsyncFunctionDef` 都有中文 docstring。
- 范围包含公开函数、私有函数、类方法、Protocol 方法、嵌套函数和回调函数。
- 模块与类使用中文 docstring 说明职责。
- 现有英文行内注释和分段注释改为中文。
- 复杂状态转换、锁、Profile 删除保护和认证判定增加原因说明。
- 不对显而易见的赋值或返回值逐行复述。
- Python 标识符、协议字段、JSON 键、状态码、URL 和外部 API 固定值保持英文。
- MCP 工具 docstring 与参数说明使用中文，以便客户端直接显示用途。

新增 AST 契约测试，扫描生产包中的所有函数定义，要求存在至少一个中文字符的 docstring。该测试防止后续版本重新引入无用途说明的方法。

## 测试清理

保留以下回归保障：

- 托管认证状态机、锁、Profile 所有权和敏感信息保护。
- 蓝湖会话有效性验证。
- 客户端认证响应分类。
- 设计列表、DesignIR、平台单位和细粒度切图。
- 八个 MCP 工具与 CLI 行为。
- Trusted Publishing 工作流触发、权限、固定 Action SHA 和无长期凭据约束。

删除或重写以下测试：

- Cookie 文件和 Cookie 环境变量优先级测试。
- CAgent 默认路径测试。
- Chrome/Safari 默认数据库读取测试。
- DDS 独立 Cookie 测试。
- HTTP 传输配置测试。
- 只验证已删除实现细节的 mock 测试。
- 与其他测试完全重复的断言。

测试代码本身不整体删除。只有功能已经删除、覆盖完全重复或测试与实现细节过度耦合时才移除。

新增以下契约测试：

- 非 macOS 返回 `unsupported_platform` 且不启动浏览器。
- 设计服务只从 `ManagedBrowserAuth` 获取凭据。
- 旧 Cookie 环境变量不再出现在代码、Registry metadata 或 README。
- 服务器固定 stdio。
- 每个生产函数都有中文 docstring。
- 版本在 `pyproject.toml`、包 `__version__` 和 `server.json` 中一致为 `0.1.1`。

## README 与公开文档

README 重写为正式项目首页，按用户首次使用路径组织：

1. 项目定位与 `v0.1.1` 状态。
2. 功能亮点。
3. macOS、Google Chrome、Python 3.10+ 系统要求。
4. `pip install lanhu-design-mcp` 安装命令。
5. `lanhu-design-mcp auth login` 首次登录。
6. 只包含 `command: "lanhu-design-mcp"` 的 MCP stdio 配置。
7. 八个 MCP 工具及参数用途。
8. 细粒度切图数据说明。
9. 托管认证安全边界、状态和故障排查。
10. 开发、测试和贡献说明。
11. `v0.1.1` 破坏性变更说明。

README 不再出现本地绝对路径、cc-switch 专用脚本、Cookie-Editor、手动 Cookie、CAgent、`.env`、HTTP 模式或旧发布步骤。

`CHANGELOG.md` 新增 `0.1.1`，说明托管认证单一路径、macOS-only、中文注释、细粒度切图、配置清理和 PyPI Trusted Publishing。

`server.json` 删除旧环境变量声明，并将服务器与 PyPI 包版本更新为 `0.1.1`。

## 版本与发布

以下版本必须同时更新为 `0.1.1`：

- `pyproject.toml` 的项目版本。
- `src/lanhu_design_mcp/__init__.py` 的 `__version__`。
- `server.json` 的服务器版本。
- `server.json` 的 PyPI package 版本。

发布顺序：

1. 完成代码、测试、文档和独立审查。
2. 验证 Ruff、pytest、MCP Registry metadata、sdist、wheel 和 Twine。
3. 推送 `main`。
4. 创建不可变标签 `v0.1.1`，确保标签提交包含 `.github/workflows/release.yml`。
5. 发布 GitHub Release `v0.1.1`。
6. 构建作业成功后，由用户批准 `pypi` Environment。
7. 验证 PyPI JSON、全新虚拟环境安装和 CLI 帮助。
8. PyPI 成功后发布 MCP Registry `0.1.1`。

现有 `v0.1.0` GitHub Release 与标签保留为历史记录，不移动、不删除、不向 PyPI 上传该版本。

如果发布前验证失败，不创建标签。如果标签创建后发现需要改代码，不移动标签，改用下一个补丁版本。

## 验收标准

- macOS 真实 Chrome 登录、进程重启复用、蓝湖设计列表和细粒度切图冒烟测试通过。
- 普通设计调用不会意外打开可见浏览器。
- 非 macOS 认证路径返回固定 `unsupported_platform`。
- 代码库不存在旧 Cookie 配置入口和旧浏览器数据库实现。
- 生产代码每个函数和方法都有中文 docstring，英文代码注释已转换。
- 只删除失效或重复测试，其余回归测试全部通过。
- README 是无本机路径、无旧 Cookie 步骤的正式 `v0.1.1` 文档。
- Ruff 无未使用 import。
- MCP Registry metadata 校验通过。
- sdist 与 wheel 构建通过 Twine 检查。
- `v0.1.1` 标签包含发布工作流且保持不可变。
- PyPI Trusted Publishing 成功，`pip install lanhu-design-mcp==0.1.1` 可用。
- MCP Registry 可检索 `io.github.blantian/lanhu-design-mcp` 版本 `0.1.1`。
