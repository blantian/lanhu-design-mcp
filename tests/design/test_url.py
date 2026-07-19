from lanhu_design_mcp.design.url import parse_lanhu_url


def test_parse_stage_url():
    parsed = parse_lanhu_url(
        "https://lanhuapp.com/web/#/item/project/stage?pid=p1&tid=t1&see=all"
    )
    assert parsed.project_id == "p1"
    assert parsed.team_id == "t1"
    assert parsed.image_id is None


def test_parse_detail_detach_url():
    parsed = parse_lanhu_url(
        "https://lanhuapp.com/web/#/item/project/detailDetach?pid=p1&tid=t1&image_id=i1&type=image"
    )
    assert parsed.project_id == "p1"
    assert parsed.team_id == "t1"
    assert parsed.image_id == "i1"


def test_parse_query_string_only():
    parsed = parse_lanhu_url("?pid=p1&image_id=i1")
    assert parsed.project_id == "p1"
    assert parsed.image_id == "i1"
