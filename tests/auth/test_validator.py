"""auth.validator 的 HTTP 会话验证契约测试。"""

from __future__ import annotations

import json as _json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from lanhu_design_mcp.auth.validator import HttpSessionValidator

ACCOUNT_URL = "https://lanhuapp.com/api/account/user/detail"


def _make_resp(status, json_body=None, text_body="", headers=None, history=None):
    content = _json.dumps(json_body).encode() if json_body is not None else text_body.encode()
    hdrs = dict(headers or {})
    if json_body is not None:
        hdrs.setdefault("content-type", "application/json")
    return httpx.Response(status, headers=hdrs, content=content,
                          request=httpx.Request("GET", ACCOUNT_URL),
                          history=list(history or []))


class TestHttpSessionValidator:
    """Deterministic classification tests — no real HTTP."""

    @pytest.mark.asyncio
    async def test_200_code_00000_is_true(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "00000"}))):
            assert await v.validate("s=x") is True

    @pytest.mark.asyncio
    async def test_200_code_not_00000_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "00001"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_200_code_numeric_0_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": 0}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_200_code_str_0_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "0"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_200_missing_code_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"msg": "ok"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_401_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(401, {"code": 30001}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_500_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(500, {"code": "00000"}))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_redirect_history_to_login_is_false(self):
        redirect = httpx.Response(
            302, headers={"Location": "https://lanhuapp.com/login"},
            request=httpx.Request("GET", ACCOUNT_URL),
        )
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, {"code": "00000"}, history=[redirect]))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_malformed_json_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, text_body="not json"))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_non_dict_json_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=_make_resp(200, json_body=[]))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_network_error_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(side_effect=RuntimeError("network"))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_timeout_is_false(self):
        v = HttpSessionValidator()
        with patch.object(httpx.AsyncClient, "get", AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
            assert await v.validate("s=x") is False

    @pytest.mark.asyncio
    async def test_requests_account_endpoint_with_safe_headers(self):
        v = HttpSessionValidator()
        mock_get = AsyncMock(return_value=_make_resp(200, {"code": "00000"}))
        with patch.object(httpx.AsyncClient, "get", mock_get):
            await v.validate("s=fakevalue")
        call_args = mock_get.call_args
        url = call_args[0][0]
        req_headers = call_args[1]["headers"]
        assert url == ACCOUNT_URL
        assert "Cookie" in req_headers
        assert req_headers.get("Referer") == "https://lanhuapp.com/web/"
        assert req_headers.get("request-from") == "web"
