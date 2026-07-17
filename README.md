<!-- mcp-name: io.github.buluesky/lanhu-design-mcp -->

# 蓝湖设计 MCP

面向 Android 优先的 MCP 服务器，用于读取蓝湖设计稿并导出 UI 还原上下文，支持 Codex、Claude Code、Cursor 等 AI 编程助手。

## 功能特性

- 读取蓝湖设计项目 URL
- 列出项目中的所有设计图
- 获取指定设计的 DDS schema 数据
- 将设计节点规范化为紧凑的 Agent 友好的 DesignIR 格式
- 支持 `web`、`android`、`ios`、`wechat_miniprogram` 平台的尺寸转换
- 默认输出 Android 单位 (`dp`)，适用于 Android TV 和 App 开发
- **🎉 支持从浏览器自动获取 Cookie（macOS Chrome/Safari）**

## 快速开始

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 2. 配置 Cookie

#### 方式 A: CAgent 共享 Cookie 文件（推荐）

将 Cookie 保存到 CAgent 共享目录，与 Wiki MCP 等工具共用：

```bash
mkdir -p ~/.config/cagent/lanhu
printf '%s\n' 'session=xxx; tfstk=yyy' > ~/.config/cagent/lanhu/cookie.txt
chmod 600 ~/.config/cagent/lanhu/cookie.txt
```

系统会自动读取 `~/.config/cagent/lanhu/cookie.txt`，无需额外配置。

#### 方式 B: Cookie 文件环境变量

指定自定义 Cookie 文件路径：

```bash
export LANHU_COOKIE_FILE=/path/to/cookie.txt
```

#### 方式 C: 环境变量直接配置

```bash
export LANHU_COOKIE="session=xxx; tfstk=yyy"
```

#### 方式 D: 浏览器自动导入（备用方案）

设置 `AUTO_BROWSER_COOKIES=true`，系统会尝试从浏览器（Chrome/Safari）读取 Cookie。自动导入是备用的可选路径，不推荐作为主要方式。

### 获取蓝湖 Cookie（手动方式）

1. 在浏览器中打开 https://lanhuapp.com 并登录
2. 打开开发者工具（F12）→ Network（网络）标签
3. 刷新页面，找到任意一个发往 lanhuapp.com 的请求
4. 点击请求，在右侧 Headers（请求头）中找到 `Cookie:` 行
5. 复制完整的 Cookie 值（格式：`session=xxx; tfstk=yyy`）

## 配置选项

```bash
# 自动从浏览器获取 Cookie（备用方案）
AUTO_BROWSER_COOKIES=false

# Cookie 文件路径（优先于环境变量）
LANHU_COOKIE_FILE=""
DDS_COOKIE_FILE=""

# 手动配置 Cookie（如果自动获取失败）
LANHU_COOKIE="session=...; tfstk=..."

# DDS Cookie（默认使用 LANHU_COOKIE）
DDS_COOKIE=""

# 数据目录
DATA_DIR="./data"

# HTTP 超时时间（秒）
HTTP_TIMEOUT=30

# MCP 传输模式
MCP_TRANSPORT=stdio        # stdio 或 http

# HTTP 服务器配置（仅在 http 模式下使用）
SERVER_HOST="0.0.0.0"
SERVER_PORT=8000
```

## MCP stdio 配置

在 Claude Desktop 或其他 MCP 客户端的配置文件中添加：

### 默认模式（使用 CAgent Cookie 文件）

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "/bin/bash",
      "args": ["/path/to/lanhu-design-mcp/run-stdio.sh"]
    }
  }
}
```

### 手动模式

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "/bin/bash",
      "args": ["/path/to/lanhu-design-mcp/run-stdio.sh"],
      "env": {
        "LANHU_COOKIE": "session=...; tfstk=...",
        "AUTO_BROWSER_COOKIES": "false"
      }
    }
  }
}
```

## Cookie 解析优先级

蓝湖 Cookie 解析顺序：

1. `LANHU_COOKIE_FILE` 环境变量
2. `~/.config/cagent/lanhu/cookie.txt`（默认 CAgent 文件）
3. `LANHU_COOKIE` 环境变量
4. 浏览器自动导入（仅在 `AUTO_BROWSER_COOKIES=true` 时）
5. 返回缺失 Cookie 错误

DDS Cookie 解析顺序：

1. `DDS_COOKIE_FILE` 环境变量
2. `DDS_COOKIE` 环境变量
3. 已解析的蓝湖 Cookie

## 可用工具

- `lanhu_health_check()` - 检查本地配置状态（不访问网络，不返回 Cookie 值）
- `lanhu_get_designs(url)` - 获取项目的所有设计图列表
- `lanhu_analyze_design(url, design_name_or_index = null, target_platform = "android")` - 分析指定设计稿
- `lanhu_get_design_assets(url, design_name_or_index = null, target_platform = "android")` - 获取设计资源下载信息
- `lanhu_export_ui_context(url, design_name_or_index = null, target_platform = "android")` - 导出完整的 UI 还原上下文

### 细粒度切图资源

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
      "scale_urls": {"1x": "https://...", "2x": "https://...", "android_xhdpi": "https://..."}
    }
  ]
}
```

## 平台单位转换

- Web: `px` - 蓝湖原始标注单位
- Android: `dp = px / 2` - 基于验证的蓝湖规则（1920x1080px → 960x540dp）
- iOS: `pt = px / 2` - 默认逻辑点转换，需要时可根据具体设计团队验证
- 微信小程序: `rpx = px * 750 / 设计稿宽度` - 基于设计稿宽度的 rpx 转换

## 辅助工具

- `python tools/setup_cookies.py` - 交互式 Cookie 配置工具
- `python tools/get_cookies.py` - 检测浏览器 Cookie 状态

## 故障排除

### 自动获取 Cookie 失败

如果看到 "自动获取浏览器 Cookies 失败" 的警告：

1. 确保已在 Chrome 或 Safari 中登录蓝湖
2. 运行 `python tools/get_cookies.py` 检测浏览器状态
3. 如果仍然失败，切换到手动模式：
   ```bash
   python tools/setup_cookies.py
   # 选择 "2. 手动模式"
   ```

### Chrome Cookie 解密失败

macOS Chrome 使用 Keychain 加密 Cookies，如果解密失败：

1. 尝试在 Safari 中登录蓝湖（Safari Cookie 不加密）
2. 或使用手动模式配置

### HTTP 418 错误

这表示 Cookie 无效或已过期：

1. 重新登录蓝湖网站
2. 重新运行 `python tools/setup_cookies.py`
