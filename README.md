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

#### 方式 A: 自动模式（推荐）

使用交互式配置工具：

```bash
python tools/setup_cookies.py
```

选择 "1. 自动模式"，系统会尝试从浏览器（Chrome/Safari）自动读取蓝湖 Cookie。

#### 方式 B: 手动模式

如果自动获取失败，可以手动配置：

1. 复制 `.env.example` 为 `.env`
2. 运行配置工具选择 "2. 手动模式"，或直接编辑 `.env` 文件：

```bash
# 禁用自动获取
AUTO_BROWSER_COOKIES=false

# 手动填写 Cookie
LANHU_COOKIE="session=xxx; tfstk=yyy"
```

### 获取蓝湖 Cookie（手动方式）

1. 在浏览器中打开 https://lanhuapp.com 并登录
2. 打开开发者工具（F12）→ Network（网络）标签
3. 刷新页面，找到任意一个发往 lanhuapp.com 的请求
4. 点击请求，在右侧 Headers（请求头）中找到 `Cookie:` 行
5. 复制完整的 Cookie 值（格式：`session=xxx; tfstk=yyy`）

## 配置选项

```bash
# 自动从浏览器获取 Cookie（推荐）
AUTO_BROWSER_COOKIES=true

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

### 自动模式（推荐）

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "/bin/bash",
      "args": ["/path/to/lanhu-design-mcp/run-stdio.sh"],
      "env": {
        "AUTO_BROWSER_COOKIES": "true"
      }
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

## 可用工具

- `lanhu_get_designs(url)` - 获取项目的所有设计图列表
- `lanhu_analyze_design(url, design_name_or_index = null, target_platform = "android")` - 分析指定设计稿
- `lanhu_get_design_assets(url, design_name_or_index = null, target_platform = "android")` - 获取设计资源下载信息
- `lanhu_export_ui_context(url, design_name_or_index = null, target_platform = "android")` - 导出完整的 UI 还原上下文

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
