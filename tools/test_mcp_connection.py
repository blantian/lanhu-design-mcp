#!/usr/bin/env python3
"""测试 MCP 服务器连接"""
import subprocess
import json
import sys
import time

def test_mcp_connection():
    print("=" * 80)
    print("MCP 连接测试")
    print("=" * 80)
    print()

    # 启动 MCP 服务器
    print("1. 启动 MCP 服务器...")
    process = subprocess.Popen(
        ["./run-stdio.sh"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    time.sleep(1)

    if process.poll() is not None:
        print("   ✗ 服务器启动失败")
        stderr = process.stderr.read()
        print(f"   错误信息:\n{stderr}")
        return False

    print("   ✓ 服务器已启动")
    print()

    # 发送初始化请求
    print("2. 发送初始化请求...")
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }

    try:
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # 读取响应
        response_line = process.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            print("   ✓ 初始化成功")
            print(f"   服务器信息: {response.get('result', {}).get('serverInfo', {})}")
            print()
        else:
            print("   ✗ 未收到响应")
            return False

    except Exception as e:
        print(f"   ✗ 初始化失败: {e}")
        return False

    # 发送 initialized 通知
    print("3. 发送 initialized 通知...")
    initialized_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }

    try:
        process.stdin.write(json.dumps(initialized_notification) + "\n")
        process.stdin.flush()
        print("   ✓ 通知已发送")
        print()
    except Exception as e:
        print(f"   ✗ 发送通知失败: {e}")
        return False

    # 列出可用工具
    print("4. 列出可用工具...")
    list_tools_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list"
    }

    try:
        process.stdin.write(json.dumps(list_tools_request) + "\n")
        process.stdin.flush()

        response_line = process.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            tools = response.get('result', {}).get('tools', [])
            print(f"   ✓ 找到 {len(tools)} 个工具:")
            for tool in tools:
                print(f"     - {tool.get('name')}: {tool.get('description', '')[:50]}...")
            print()
        else:
            print("   ✗ 未收到工具列表")
            return False

    except Exception as e:
        print(f"   ✗ 获取工具列表失败: {e}")
        return False

    # 清理
    print("5. 清理...")
    process.terminate()
    process.wait(timeout=3)
    print("   ✓ 服务器已停止")
    print()

    print("=" * 80)
    print("✅ MCP 连接测试通过！")
    print("=" * 80)
    print()
    print("📋 MCP Router 配置示例:")
    print()
    print(json.dumps({
        "mcpServers": {
            "lanhu-design": {
                "command": "/bin/bash",
                "args": [f"{subprocess.check_output(['pwd'], text=True).strip()}/run-stdio.sh"],
                "env": {
                    "AUTO_BROWSER_COOKIES": "true"
                }
            }
        }
    }, indent=2))
    print()

    return True

if __name__ == "__main__":
    try:
        success = test_mcp_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
