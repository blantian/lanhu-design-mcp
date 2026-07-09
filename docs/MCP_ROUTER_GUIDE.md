# MCP Router 配置指南

## 问题诊断

如果遇到 "Connection closed" 错误，按以下步骤排查：

### 1. 检查日志

启动脚本现在会写入日志到 `~/.mcp_lanhu_design.log`

```bash
tail -f ~/.mcp_lanhu_design.log
```

### 2. 验证 Cookie 配置

```bash
# 运行交互式配置工具
python tools/setup_cookies.py

# 或手动测试 Cookie
python -c "from src.lanhu_design_mcp.config import get_settings; s = get_settings(); print('Cookie:', 'OK' if s.lanhu_cookie else 'MISSING')"
```

### 3. 测试 MCP 连接

```bash
python tools/test_mcp_connection.py
```

## MCP Router 配置

### 推荐配置（自动获取 Cookie）

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "/bin/bash",
      "args": ["/Users/buluesky/mcp/lanhu-design-mcp/run-stdio.sh"],
      "env": {
        "AUTO_BROWSER_COOKIES": "true"
      }
    }
  }
}
```

### 手动配置（如果自动获取失败）

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "/bin/bash",
      "args": ["/Users/buluesky/mcp/lanhu-design-mcp/run-stdio.sh"],
      "env": {
        "LANHU_COOKIE": "session=xxx; tfstk=yyy",
        "AUTO_BROWSER_COOKIES": "false"
      }
    }
  }
}
```

## 常见问题

### Q1: "Connection closed" 错误

**原因**：
- Cookie 未配置或已过期
- Python 虚拟环境问题
- 依赖未安装

**解决**：
1. 运行 `python tools/setup_cookies.py` 配置 Cookie
2. 检查 `~/.mcp_lanhu_design.log` 查看错误
3. 确保虚拟环境已安装依赖：`source .venv/bin/activate && pip install -e .`

### Q2: Cookie 自动获取失败

**解决**：
1. 确保在 Chrome 或 Safari 中已登录蓝湖
2. 运行 `python tools/get_cookies.py` 检测浏览器状态
3. 切换到手动模式：在 MCP Router 配置中设置 `LANHU_COOKIE` 环境变量

### Q3: 工具调用失败

**解决**：
1. 测试 URL 是否正确：必须是蓝湖项目 URL
2. 检查 Cookie 是否过期：重新登录蓝湖并更新 Cookie
3. 查看日志文件获取详细错误信息

## 验证配置

### 步骤 1: 测试启动脚本

```bash
./run-stdio.sh
# 应该看到 FastMCP 的启动界面
# 按 Ctrl+C 退出
```

### 步骤 2: 检查日志

```bash
cat ~/.mcp_lanhu_design.log
```

### 步骤 3: 测试完整流程

```bash
python tools/test_mcp_connection.py
```

如果所有测试都通过，MCP Router 应该能正常工作。

## 调试模式

如果问题仍然存在，在 MCP Router 中启用详细日志：

```json
{
  "mcpServers": {
    "lanhu-design": {
      "command": "/bin/bash",
      "args": ["/Users/buluesky/mcp/lanhu-design-mcp/run-stdio.sh"],
      "env": {
        "LANHU_COOKIE": "session=xxx; tfstk=yyy",
        "AUTO_BROWSER_COOKIES": "false",
        "MCP_DEBUG": "true"
      }
    }
  }
}
```

然后查看日志：`tail -f ~/.mcp_lanhu_design.log`
