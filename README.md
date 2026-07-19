<!-- mcp-name: io.github.blantian/lanhu-design-mcp -->

# 蓝湖设计 MCP

## 项目简介

面向 macOS 的蓝湖设计读取与细粒度 UI 资源导出 MCP 服务器。

## 功能

- 读取蓝湖设计项目，列出所有设计图
- 分析设计稿并返回平台调整后的 UI 结构（Android dp / iOS pt / Web px / 微信 rpx）
- 返回完整设计图与 Sketch、Figma、Photoshop 细粒度切图资源及多倍率地址
- 导出包含资产和分析的完整 Agent UI 还原上下文
- 托管 Chrome Profile 自动登录，无需手动复制 Cookie

## 系统要求

- macOS
- Google Chrome（已安装）
- Python 3.10 及以上

## 安装

```bash
pip install lanhu-design-mcp
```

## 首次登录

```bash
lanhu-design-mcp auth login
lanhu-design-mcp auth status
```

首次运行打开独立的本地 Chrome Profile，完成一次交互式 Lanhu 登录。后续 MCP 进程自动重用会话，正常设计工具调用不会打开可见浏览器。认证仅使用托管 Chrome Profile，不需要也不支持通过 Cookie 环境变量或 Cookie 文件配置凭据。

```bash
lanhu-design-mcp auth logout --confirm
```

## MCP 配置

```json
{
  "mcpServers": {
    "lanhu-design-mcp": {
      "type": "stdio",
      "command": "/Users/your-name/.local/bin/lanhu-design-mcp",
      "args": []
    }
  }
}
```

将 `/Users/your-name` 替换为你的本机用户名。此配置适用于 cc-switch 导入。

## 工具

| 工具 | 说明 |
|---|---|
| `lanhu_health_check` | 返回本地配置状态，不访问网络且不暴露凭据 |
| `lanhu_get_designs` | 获取项目的所有设计图列表 |
| `lanhu_analyze_design` | 分析指定设计稿并返回平台调整后的 UI 结构 |
| `lanhu_get_design_assets` | 返回完整设计图与细粒度可下载切图资源 |
| `lanhu_export_ui_context` | 返回包含资产和分析的完整 Agent UI 还原上下文 |
| `lanhu_auth_login` | 打开专属 Chrome Profile 进行交互式 Lanhu 登录 |
| `lanhu_auth_status` | 报告托管认证状态，不含凭据 |
| `lanhu_auth_logout` | 登出并删除托管 Profile，需要 confirm=true |

## 使用规范

- 调用方应将返回的签名资源 URL 下载到本地项目，不要生成对远程 Lanhu 签名 URL 的长期依赖。
- 不得在日志、异常或 MCP 响应中记录或输出凭据信息。
- 登出必须调用 `lanhu_auth_logout` 并传 `confirm=true`，或 CLI `--confirm`，仅删除托管的标记 Profile。
- 托管 Chrome Profile 仅存在于本地；认证凭据从不通过 MCP 网络传输。

## 常见错误

| 状态 | 说明 | 处理 |
|---|---|---|
| `auth_required` | 凭据无效或过期 | 运行 `lanhu-design-mcp auth login` |
| `unsupported_platform` | 仅在 macOS 支持 | 使用 macOS 设备 |
| `dependency_missing` | Playwright Python 库或 Chrome 不可用 | `pip install --upgrade lanhu-design-mcp` |
| `profile_locked` | 托管 Profile 被其他进程占用 | 等待完成后重试 |
| `cancelled` | 登录窗口在认证完成前关闭 | 重新运行 `lanhu-design-mcp auth login` |
| `timed_out` | 登录窗口 5 分钟内未完成认证 | 重新运行 `lanhu-design-mcp auth login` |

## 开发验证

```bash
git clone https://github.com/blantian/lanhu-design-mcp
cd lanhu-design-mcp
uv sync --dev
uv run pytest
```

## 许可证

MIT
