from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .url_parser import LanhuUrl

BASE_URL = "https://lanhuapp.com"
DDS_BASE_URL = "https://dds.lanhuapp.com"


class LanhuAuthError(RuntimeError):
    pass


class LanhuClient:
    def __init__(self, settings: Settings):
        if not settings.lanhu_cookie:
            raise LanhuAuthError("LANHU_COOKIE is required")
        self.settings = settings
        self.client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://lanhuapp.com/web/",
                "Accept": "application/json, text/plain, */*",
                "Cookie": settings.lanhu_cookie,
                "request-from": "web",
                "real-path": "/item/project/stage",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "LanhuClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def get_designs(self, ref: LanhuUrl) -> dict[str, Any]:
        params: dict[str, Any] = {
            "project_id": ref.project_id,
            "dds_status": 1,
            "position": 1,
            "show_cb_src": 1,
            "comment": 1,
        }
        if ref.team_id:
            params["team_id"] = ref.team_id

        response = await self.client.get(f"{BASE_URL}/api/project/images", params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "00000":
            raise RuntimeError(data.get("msg", "Failed to get Lanhu designs"))
        project_data = data.get("data") or {}
        designs = []
        for index, image in enumerate(project_data.get("images") or [], 1):
            designs.append(
                {
                    "index": index,
                    "id": image.get("id"),
                    "name": image.get("name"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "url": image.get("url"),
                    "has_comment": image.get("has_comment", False),
                    "update_time": image.get("update_time"),
                }
            )
        return {
            "status": "success",
            "project_id": ref.project_id,
            "project_name": project_data.get("name"),
            "total_designs": len(designs),
            "designs": designs,
        }

    async def get_version_id(self, ref: LanhuUrl, image_id: str) -> str:
        params: dict[str, Any] = {
            "project_id": ref.project_id,
            "img_limit": 500,
            "detach": 1,
        }
        if ref.team_id:
            params["team_id"] = ref.team_id
        response = await self.client.get(f"{BASE_URL}/api/project/multi_info", params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "00000":
            raise RuntimeError(data.get("msg", "Failed to get Lanhu multi_info"))
        for image in (data.get("result") or {}).get("images") or []:
            if image.get("id") == image_id:
                version_id = image.get("latest_version")
                if version_id:
                    return version_id
                raise RuntimeError(f"Design {image_id} has no latest_version")
        raise RuntimeError(f"Design image_id not found: {image_id}")

    async def get_design_schema(self, ref: LanhuUrl, image_id: str) -> dict[str, Any]:
        version_id = await self.get_version_id(ref, image_id)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://dds.lanhuapp.com/",
            "Cookie": self.settings.dds_cookie,
            "Authorization": "Basic dW5kZWZpbmVkOg==",
        }
        async with httpx.AsyncClient(timeout=self.settings.http_timeout, headers=headers, follow_redirects=True) as dds:
            response = await dds.get(f"{DDS_BASE_URL}/api/dds/image/store_schema_revise", params={"version_id": version_id})
            response.raise_for_status()
            data = response.json()
            if data.get("code") != "00000":
                raise RuntimeError(data.get("msg", "Failed to get DDS schema URL"))
            schema_url = (data.get("data") or {}).get("data_resource_url")
            if not schema_url:
                raise RuntimeError("DDS schema response missing data_resource_url")
            schema_response = await dds.get(schema_url)
            schema_response.raise_for_status()
            return schema_response.json()

    async def get_sketch_json(self, ref: LanhuUrl, image_id: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "dds_status": 1,
            "image_id": image_id,
            "project_id": ref.project_id,
        }
        if ref.team_id:
            params["team_id"] = ref.team_id
        response = await self.client.get(f"{BASE_URL}/api/project/image", params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "00000":
            raise RuntimeError(data.get("msg", "Failed to get Lanhu image"))
        return data.get("data") or data.get("result") or {}

    async def get_design_asset_source(self, ref: LanhuUrl, image_id: str) -> dict[str, Any]:
        metadata = await self.get_sketch_json(ref, image_id)
        versions = metadata.get("versions") or []
        if not versions or not isinstance(versions[0], dict):
            raise RuntimeError(f"Design {image_id} has no version metadata")
        latest_version = versions[0]
        json_url = latest_version.get("json_url")
        if not json_url:
            raise RuntimeError(f"Design {image_id} version metadata missing json_url")
        response = await self.client.get(json_url)
        response.raise_for_status()
        source = response.json()
        if not isinstance(source, dict):
            raise RuntimeError(f"Design {image_id} asset source is not a JSON object")
        return {
            "source": source,
            "version": latest_version.get("version_info"),
            "json_url": json_url,
        }
