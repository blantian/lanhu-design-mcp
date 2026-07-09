#!/usr/bin/env python3
"""蓝湖 Cookie 获取辅助工具"""
from __future__ import annotations

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    from lanhu_design_mcp.browser_cookies import get_cookies_info, get_lanhu_cookies, BrowserCookieError

    print("=" * 80)
    print("蓝湖 MCP - Cookie 自动获取工具")
    print("=" * 80)
    print()

    # 检测浏览器状态
    print("正在检测浏览器 Cookies...\n")
    info = get_cookies_info()

    print(f"操作系统: {info['system']}\n")

    has_cookies = False
    for browser, data in info["browsers"].items():
        print(f"📦 {browser.title()}:")
        if data["available"]:
            if data["cookies_found"] > 0:
                print(f"   ✓ 找到 {data['cookies_found']} 个蓝湖 Cookie")
                print(f"   Cookie 名称: {', '.join(data['cookie_names'])}")
                has_cookies = True
            else:
                print(f"   ✗ 未找到蓝湖 Cookies（可能未在此浏览器登录蓝湖）")
        else:
            print(f"   ✗ 无法访问: {data['error']}")
        print()

    if not has_cookies:
        print("=" * 80)
        print("❌ 自动获取失败")
        print("=" * 80)
        print()
        print("原因可能是：")
        print("  1. 浏览器未登录蓝湖网站")
        print("  2. Chrome Cookie 加密无法解密")
        print("  3. 浏览器数据库访问权限不足")
        print()
        print("解决方案：")
        print()
        print("📋 手动获取 Cookie 步骤：")
        print()
        print("  1. 在浏览器中打开 https://lanhuapp.com 并登录")
        print("  2. 打开开发者工具（按 F12）")
        print("  3. 切换到 'Network（网络）' 标签")
        print("  4. 刷新页面，找到任意请求")
        print("  5. 点击请求，在 'Headers（请求头）' 中找到 'Cookie:'")
        print("  6. 复制完整的 Cookie 值")
        print("  7. 在 .env 文件中设置：")
        print()
        print("     LANHU_COOKIE=\"session=xxx; tfstk=yyy\"")
        print()
        return 1

    # 尝试自动获取
    print("=" * 80)
    print("尝试自动获取 Cookies...")
    print("=" * 80)
    print()

    try:
        cookie_string = get_lanhu_cookies()
        cookie_preview = cookie_string[:150] + "..." if len(cookie_string) > 150 else cookie_string

        print("✅ 成功获取蓝湖 Cookies！")
        print()
        print(f"Cookie 长度: {len(cookie_string)} 字符")
        print()
        print("预览:")
        print(f"  {cookie_preview}")
        print()
        print("=" * 80)
        print("配置方式")
        print("=" * 80)
        print()
        print("方式 1: 自动模式（推荐）")
        print("  在 .env 文件中设置：")
        print("  AUTO_BROWSER_COOKIES=true")
        print("  （无需配置 LANHU_COOKIE，系统将自动读取）")
        print()
        print("方式 2: 手动模式")
        print("  在 .env 文件中设置：")
        print(f'  LANHU_COOKIE="{cookie_string}"')
        print()
        print("💡 提示：自动模式会在每次启动时从浏览器读取最新 Cookie")
        print()
        return 0

    except BrowserCookieError as e:
        print(f"❌ {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
