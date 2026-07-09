#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 设置日志文件用于调试
LOG_FILE="${HOME}/.mcp_lanhu_design.log"
echo "[$(date)] Starting lanhu-design MCP server" >> "$LOG_FILE"

export MCP_TRANSPORT=stdio

# 检查 .env 文件
if [ ! -f .env ]; then
  echo "[$(date)] Warning: .env file not found" >> "$LOG_FILE"
fi

# 使用虚拟环境的 Python
if [ -x ".venv/bin/python" ]; then
  echo "[$(date)] Using .venv/bin/python" >> "$LOG_FILE"
  exec .venv/bin/python -m lanhu_design_mcp.server 2>> "$LOG_FILE"
fi

echo "[$(date)] Using system python3" >> "$LOG_FILE"
exec python3 -m lanhu_design_mcp.server 2>> "$LOG_FILE"
