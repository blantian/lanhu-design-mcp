<!-- mcp-name: io.github.blantian/lanhu-design-mcp -->

# 蓝湖设计 MCP

`v0.1.1` 是面向 macOS 的蓝湖设计读取与细粒度 UI 资源导出 MCP 服务器。

## 功能

- 读取蓝湖设计项目 URL，列出所有设计图
- 分析指定设计稿并返回平台调整后的 UI 结构（Android dp / iOS pt / Web px / 微信 rpx）
- 返回完整设计图与细粒度 Sketch、Figma、Photoshop 切图资源及 Web、iOS、Android 多倍率地址
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

登录使用独立的本地 Chrome Profile，首次交互式登录后，后续 MCP 进程自动重用会话。正常设计工具调用不会打开可见浏览器。凭证过期时返回 `auth_required` 指引，需重新调用 `lanhu_auth_login`。

```bash
lanhu-design-mcp auth logout --confirm
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

| 工具 | 参数 | 说明 |
|---|---|---|
| `lanhu_health_check` | 无 | 返回本地配置状态，不访问网络且不暴露 Cookie 值 |
| `lanhu_get_designs` | `url` | 获取项目的所有设计图列表 |
| `lanhu_analyze_design` | `url`, `design_name_or_index` (可选), `target_platform` (可选，默认 `android`) | 分析指定设计稿并返回平台调整后的 UI 结构 |
| `lanhu_get_design_assets` | `url`, `design_name_or_index` (可选), `target_platform` (可选，默认 `android`) | 返回完整设计图与细粒度可下载切图资源 |
| `lanhu_export_ui_context` | `url`, `design_name_or_index` (可选), `target_platform` (可选，默认 `android`) | 返回包含资产和分析的完整 Agent UI 还原上下文 |
| `lanhu_auth_login` | 无 | 打开专属 Chrome Profile 进行交互式 Lanhu 登录 |
| `lanhu_auth_status` | `session_id` (可选) | 报告托管认证状态，不含凭据 |
| `lanhu_auth_logout` | `confirm` (可选，默认 `false`) | 登出并删除托管 Profile，需要 `confirm=true` |

## 细粒度切图

`lanhu_get_design_assets` 返回整张设计图和设计师声明的细粒度切图。整图始终是 `assets` 的第一项；其余 `kind: "slice"` 项可包含：

- `remote_url`：蓝湖存储的原始 PNG 或 SVG 地址
- `svg_url`：同时存在 PNG 和 SVG 时的矢量地址
- `scale_urls`：Web、iOS 和 Android 多倍率 PNG 地址
- `logical_size`、`position_px`：逻辑尺寸和画布坐标
- `layer_path`：源设计中的图层路径
- `suggested_local_path`：建议的本地保存路径

该工具只返回下载映射，不会向调用方项目写入文件。

```json
{
  "slice_scale": 2,
  "total_assets": 2,
  "total_slices": 1,
  "assets": [
    {"kind": "design_image", "remote_url": "https://..."},
    {
      "kind": "slice",
      "name": "切换",
      "format": "png",
      "remote_url": "https://...",
      "svg_url": "https://...",
      "scale_urls": {"1x": "https://...", "2x": "https://...", "android_xhdpi": "https://..."},
      "logical_size": {"width": 22, "height": 22},
      "position_px": {"x": 1241, "y": 66},
      "layer_path": "切换",
      "suggested_local_path": "assets/lanhu/design-id/切换.png"
    }
  ]
}
```

## 平台单位

- Web: `px` - 蓝湖原始标注单位
- Android: `dp = px / 2` - 基于验证的蓝湖规则（1920x1080px → 960x540dp）
- iOS: `pt = px / 2` - 默认逻辑点转换
- 微信小程序: `rpx = px * 750 / 设计稿宽度` - 基于设计稿宽度的 rpx 转换

## 托管认证与安全

- 认证信息仅存在于本机托管 Chrome Profile 中，绝不通过 MCP 响应或日志输出
- 启动和健康检查不访问网络，不触发浏览器
- `auth_required` 错误为结构化响应，不含凭据
- 登出仅删除托管 Profile，不触碰系统 Chrome 默认 Profile

## 故障排查

| 状态 | 说明 | 处理 |
|---|---|---|
| `auth_required` | 凭据无效或过期 | 运行 `lanhu-design-mcp auth login` |
| `unsupported_platform` | 仅在 macOS 上支持 | 使用 macOS 设备 |
| `dependency_missing` | Playwright Python 库或 Chrome 不可用 | `pip install --upgrade lanhu-design-mcp` 并确认 Chrome 已安装 |
| `profile_locked` | 托管 Profile 被其他进程占用 | 等待其他进程完成后重试 |
| `cancelled` | 登录窗口在认证完成前关闭 | 重新运行 `lanhu-design-mcp auth login` |
| `timed_out` | 登录窗口 5 分钟内未完成认证 | 重新运行 `lanhu-design-mcp auth login` |

## 开发与测试

```bash
git clone https://github.com/blantian/lanhu-design-mcp
cd lanhu-design-mcp
uv sync --dev
uv run pytest
```

## v0.1.1 兼容性说明

- 仅支持 macOS；不再支持通过环境变量文件或浏览器默认数据库配置凭据
- MCP 传输固定为 stdio
- Playwright Python 库为必要依赖，但不会自动下载 Chromium

## 许可证

MIT
