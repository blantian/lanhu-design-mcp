"""从浏览器自动读取 Cookies"""
from __future__ import annotations

import json
import os
import platform
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


class BrowserCookieError(Exception):
    """浏览器 Cookie 读取错误"""


def get_chrome_cookies(domain: str = "lanhuapp.com") -> dict[str, str]:
    """从 Chrome 读取指定域名的 Cookies

    Args:
        domain: 目标域名

    Returns:
        Cookie 字典 {name: value}
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        chrome_cookie_path = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
    elif system == "Linux":
        chrome_cookie_path = Path.home() / ".config/google-chrome/Default/Cookies"
    elif system == "Windows":
        chrome_cookie_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/Cookies"
    else:
        raise BrowserCookieError(f"不支持的操作系统: {system}")

    if not chrome_cookie_path.exists():
        raise BrowserCookieError(f"Chrome Cookies 文件不存在: {chrome_cookie_path}")

    # Chrome 的 Cookies 数据库是加密的，需要复制到临时位置
    import tempfile
    import shutil

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        tmp_path = tmp_file.name

    try:
        shutil.copy2(chrome_cookie_path, tmp_path)

        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()

        # Chrome Cookies 表结构
        cursor.execute(
            "SELECT name, encrypted_value, value FROM cookies WHERE host_key LIKE ?",
            (f"%{domain}%",)
        )

        cookies = {}
        for name, encrypted_value, value in cursor.fetchall():
            if encrypted_value:
                # 尝试解密（macOS）
                if system == "Darwin":
                    try:
                        decrypted = _decrypt_chrome_cookie_macos(encrypted_value)
                        if decrypted:
                            cookies[name] = decrypted
                    except Exception:
                        # 解密失败，跳过
                        pass
            elif value:
                cookies[name] = value

        conn.close()
        return cookies

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _decrypt_chrome_cookie_macos(encrypted_value: bytes) -> str | None:
    """解密 macOS Chrome Cookie

    Chrome 在 macOS 上使用 Keychain 存储密钥
    """
    try:
        # Chrome v80+ 使用 "v10" 前缀
        if encrypted_value[:3] == b"v10":
            encrypted_value = encrypted_value[3:]

            # 从 Keychain 获取加密密钥
            command = [
                "security",
                "find-generic-password",
                "-w",
                "-s", "Chrome Safe Storage",
                "-a", "Chrome",
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                return None

            password = result.stdout.strip()

            # 使用 PBKDF2 派生密钥
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            kdf = PBKDF2(
                algorithm=hashes.SHA1(),
                length=16,
                salt=b"saltysalt",
                iterations=1003,
                backend=default_backend(),
            )
            key = kdf.derive(password.encode())

            # AES-128-CBC 解密
            iv = b" " * 16
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(encrypted_value) + decryptor.finalize()

            # 移除 PKCS7 padding
            padding_length = decrypted[-1]
            decrypted = decrypted[:-padding_length]

            return decrypted.decode("utf-8", errors="ignore")

    except Exception:
        return None

    return None


def get_safari_cookies(domain: str = "lanhuapp.com") -> dict[str, str]:
    """从 Safari 读取指定域名的 Cookies

    Args:
        domain: 目标域名

    Returns:
        Cookie 字典 {name: value}
    """
    if platform.system() != "Darwin":
        raise BrowserCookieError("Safari 只在 macOS 上可用")

    cookie_path = Path.home() / "Library/Cookies/Cookies.binarycookies"

    if not cookie_path.exists():
        raise BrowserCookieError(f"Safari Cookies 文件不存在: {cookie_path}")

    # Safari 使用 binarycookies 格式，比较复杂
    # 简化方案：使用 sqlite 数据库（如果存在）
    cookie_db = Path.home() / "Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"

    if cookie_db.exists():
        # 尝试作为 sqlite 数据库读取
        try:
            import tempfile
            import shutil

            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
                tmp_path = tmp_file.name

            try:
                shutil.copy2(cookie_db, tmp_path)
                conn = sqlite3.connect(tmp_path)
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT name, value FROM cookies WHERE domain LIKE ?",
                    (f"%{domain}%",)
                )

                cookies = {name: value for name, value in cursor.fetchall()}
                conn.close()
                return cookies

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            raise BrowserCookieError(f"无法读取 Safari Cookies: {e}") from e

    raise BrowserCookieError("Safari Cookies 格式不支持，请使用手动配置")


def get_lanhu_cookies(browser: str = "auto") -> str:
    """自动获取蓝湖 Cookies

    Args:
        browser: 浏览器类型 ("auto", "chrome", "safari")

    Returns:
        Cookie 字符串格式 "name1=value1; name2=value2"
    """
    cookies: dict[str, str] = {}
    errors: list[str] = []

    if browser in ("auto", "chrome"):
        try:
            cookies = get_chrome_cookies("lanhuapp.com")
            if cookies:
                return _format_cookies(cookies)
        except Exception as e:
            errors.append(f"Chrome: {e}")

    if browser in ("auto", "safari"):
        try:
            cookies = get_safari_cookies("lanhuapp.com")
            if cookies:
                return _format_cookies(cookies)
        except Exception as e:
            errors.append(f"Safari: {e}")

    if not cookies:
        error_msg = "\n".join(errors) if errors else "未找到浏览器 Cookies"
        raise BrowserCookieError(
            f"无法自动获取蓝湖 Cookies:\n{error_msg}\n\n"
            "请手动在 .env 文件中配置 LANHU_COOKIE"
        )

    return _format_cookies(cookies)


def _format_cookies(cookies: dict[str, str]) -> str:
    """将 Cookie 字典格式化为字符串"""
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def get_cookies_info() -> dict[str, Any]:
    """获取 Cookies 信息和状态"""
    info: dict[str, Any] = {
        "system": platform.system(),
        "browsers": {},
    }

    # 检查 Chrome
    try:
        chrome_cookies = get_chrome_cookies("lanhuapp.com")
        info["browsers"]["chrome"] = {
            "available": True,
            "cookies_found": len(chrome_cookies),
            "cookie_names": list(chrome_cookies.keys()),
        }
    except Exception as e:
        info["browsers"]["chrome"] = {
            "available": False,
            "error": str(e),
        }

    # 检查 Safari (仅 macOS)
    if platform.system() == "Darwin":
        try:
            safari_cookies = get_safari_cookies("lanhuapp.com")
            info["browsers"]["safari"] = {
                "available": True,
                "cookies_found": len(safari_cookies),
                "cookie_names": list(safari_cookies.keys()),
            }
        except Exception as e:
            info["browsers"]["safari"] = {
                "available": False,
                "error": str(e),
            }

    return info


if __name__ == "__main__":
    # 测试脚本
    print("=== 浏览器 Cookies 检测 ===\n")

    info = get_cookies_info()
    print(f"操作系统: {info['system']}\n")

    for browser, data in info["browsers"].items():
        print(f"{browser.title()}:")
        if data["available"]:
            print(f"  ✓ 找到 {data['cookies_found']} 个 Cookie")
            print(f"  Cookie 名称: {', '.join(data['cookie_names'])}")
        else:
            print(f"  ✗ {data['error']}")
        print()

    print("\n尝试自动获取蓝湖 Cookies...")
    try:
        cookie_string = get_lanhu_cookies()
        print(f"✓ 成功获取 Cookies ({len(cookie_string)} 字符)")
        print(f"\n预览: {cookie_string[:100]}...")
    except BrowserCookieError as e:
        print(f"✗ {e}")
