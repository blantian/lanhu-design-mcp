"""macOS 托管浏览器认证。"""

from .manager import ManagedBrowserAuth, get_managed_auth
from .models import CookieInfo, Settings, settings_from_cookie

__all__ = [
    "CookieInfo",
    "ManagedBrowserAuth",
    "Settings",
    "get_managed_auth",
    "settings_from_cookie",
]
