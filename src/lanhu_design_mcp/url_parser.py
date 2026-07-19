"""蓝湖。"""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class LanhuUrl:
    """蓝湖。"""
    project_id: str
    team_id: str | None = None
    image_id: str | None = None
    doc_id: str | None = None
    version_id: str | None = None
    page_id: str | None = None


def parse_lanhu_url(value: str) -> LanhuUrl:
    """蓝湖。"""
    if not value:
        raise ValueError("Lanhu URL is empty")

    query = value
    if value.startswith("http"):
        parsed = urlparse(value)
        fragment = parsed.fragment
        if not fragment:
            raise ValueError("Invalid Lanhu URL: missing hash fragment")
        query = fragment.split("?", 1)[1] if "?" in fragment else fragment
    elif value.startswith("?"):
        query = value[1:]

    params = {key: vals[-1] for key, vals in parse_qs(query, keep_blank_values=True).items()}
    project_id = params.get("pid") or params.get("project_id")
    if not project_id:
        raise ValueError("Invalid Lanhu URL: missing pid/project_id")

    return LanhuUrl(
        project_id=project_id,
        team_id=params.get("tid") or None,
        image_id=params.get("image_id") or None,
        doc_id=params.get("docId") or None,
        version_id=params.get("versionId") or None,
        page_id=params.get("pageId") or None,
    )
