#!/usr/bin/env python3
"""交互式 Cookie 配置工具"""
from __future__ import annotations

import sys
from pathlib import Path


def main():
    print("=" * 80)
    print("蓝湖 MCP - Cookie 配置助手")
    print("=" * 80)
    print()

    env_file = Path(".env")

    print("请选择配置方式：")
    print()
    print("  1. 自动模式 - 从浏览器自动读取（推荐，但可能需要权限）")
    print("  2. 手动模式 - 粘贴完整的 Cookie 字符串")
    print("  3. 检测浏览器状态")
    print("  4. 退出")
    print()

    choice = input("请输入选项 (1-4): ").strip()

    if choice == "1":
        # 自动模式
        print("\n配置自动模式...")

        if env_file.exists():
            content = env_file.read_text()
            lines = []
            found_auto = False
            found_cookie = False

            for line in content.split("\n"):
                if line.startswith("AUTO_BROWSER_COOKIES="):
                    lines.append("AUTO_BROWSER_COOKIES=true")
                    found_auto = True
                elif line.startswith("LANHU_COOKIE="):
                    found_cookie = True
                    # 注释掉手动配置的 Cookie
                    lines.append(f"# {line}")
                else:
                    lines.append(line)

            if not found_auto:
                lines.insert(0, "AUTO_BROWSER_COOKIES=true")

            env_file.write_text("\n".join(lines))
        else:
            env_file.write_text("AUTO_BROWSER_COOKIES=true\n")

        print("\n✅ 已配置为自动模式")
        print("\n测试自动获取...")

        sys.path.insert(0, "src")
        try:
            from lanhu_design_mcp.browser_cookies import get_lanhu_cookies
            cookie = get_lanhu_cookies()
            print(f"\n✅ 成功自动获取 Cookie ({len(cookie)} 字符)")
            print(f"预览: {cookie[:100]}...")
        except Exception as e:
            print(f"\n⚠️  自动获取失败: {e}")
            print("\n建议切换到手动模式（选项 2）")

    elif choice == "2":
        # 手动模式
        print("\n" + "=" * 80)
        print("手动配置 Cookie")
        print("=" * 80)
        print()
        print("📋 获取步骤：")
        print("  1. 在浏览器打开 https://lanhuapp.com 并登录")
        print("  2. 按 F12 打开开发者工具")
        print("  3. 切换到 'Network' 标签")
        print("  4. 刷新页面，找到任意请求")
        print("  5. 在右侧 'Headers' 中找到 'Cookie:' 行")
        print("  6. 复制完整的 Cookie 值")
        print()
        print("请粘贴完整的 Cookie (输入后按回车):")
        print()

        cookie = input().strip()

        if not cookie:
            print("\n❌ Cookie 不能为空")
            return 1

        if "session=" not in cookie or "tfstk=" not in cookie:
            print("\n⚠️  警告: Cookie 中缺少 session 或 tfstk 字段")
            confirm = input("是否继续？(y/n): ").strip().lower()
            if confirm != "y":
                return 1

        # 写入 .env
        if env_file.exists():
            content = env_file.read_text()
            lines = []
            found = False

            for line in content.split("\n"):
                if line.startswith("LANHU_COOKIE="):
                    lines.append(f'LANHU_COOKIE="{cookie}"')
                    found = True
                elif line.startswith("AUTO_BROWSER_COOKIES="):
                    lines.append("AUTO_BROWSER_COOKIES=false")
                else:
                    lines.append(line)

            if not found:
                lines.insert(0, f'LANHU_COOKIE="{cookie}"')

            env_file.write_text("\n".join(lines))
        else:
            env_file.write_text(
                f'LANHU_COOKIE="{cookie}"\n'
                f'AUTO_BROWSER_COOKIES=false\n'
            )

        print("\n✅ Cookie 已保存到 .env 文件")
        print(f"Cookie 长度: {len(cookie)} 字符")

    elif choice == "3":
        # 检测浏览器
        print("\n检测浏览器状态...\n")
        sys.path.insert(0, "src")

        try:
            from lanhu_design_mcp.browser_cookies import get_cookies_info
            info = get_cookies_info()

            print(f"操作系统: {info['system']}\n")

            for browser, data in info["browsers"].items():
                print(f"📦 {browser.title()}:")
                if data["available"]:
                    if data["cookies_found"] > 0:
                        print(f"   ✓ 找到 {data['cookies_found']} 个蓝湖 Cookie")
                        print(f"   Cookie: {', '.join(data['cookie_names'])}")
                    else:
                        print(f"   ✗ 未找到蓝湖 Cookie")
                else:
                    print(f"   ✗ {data['error']}")
                print()
        except Exception as e:
            print(f"❌ 检测失败: {e}")

    elif choice == "4":
        print("\n👋 再见！")
        return 0

    else:
        print("\n❌ 无效的选项")
        return 1

    print("\n✨ 配置完成！现在可以使用 MCP 工具了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
