from lanhu_design_mcp.design_ir import summarize_schema


def test_summarize_schema_converts_page_and_node_to_android_dp():
    schema = {
        "id": "root",
        "eleName": "Page",
        "type": "lanhupage",
        "style": {"width": 1920, "height": 1080},
        "children": [
            {
                "id": "menu",
                "eleName": "频道菜单",
                "type": "lanhublock",
                "style": {"x": 341, "y": 120, "width": 1579, "height": 74},
                "children": [
                    {
                        "id": "text",
                        "eleName": "Text_少儿",
                        "type": "lanhutext",
                        "style": {"x": 610, "y": 360, "width": 70, "height": 36, "fontSize": 36, "color": "rgba(255,255,255,1)"},
                        "data": {"text": "少儿"},
                    }
                ],
            }
        ],
    }
    result = summarize_schema(schema, "android")
    assert result["page"] == {"width": 960, "height": 540}
    assert result["nodes"][0]["name"] == "Page"
    assert result["nodes"][1]["name"] == "频道菜单"
    assert result["nodes"][1]["rect"] == {"x": 170.5, "y": 60, "width": 789.5, "height": 37}
    assert "少儿" in result["texts"]
