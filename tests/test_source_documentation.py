from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

SOURCE_ROOT = Path("src/lanhu_design_mcp")
CHINESE = re.compile(r"[㐀-鿿]")
MIN_CHINESE_CHARS = 4
COMMENT_DIRECTIVES = ("# type:", "# noqa", "# pragma:")


def source_files() -> list[Path]:
    return sorted(SOURCE_ROOT.glob("*.py"))


def test_modules_classes_and_functions_have_chinese_docstrings():
    missing: list[str] = []
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes = list(ast.walk(tree))
        for node in nodes:
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node, clean=True) or ""
            if len(CHINESE.findall(doc)) < MIN_CHINESE_CHARS:
                name = getattr(node, "name", "<module>")
                line = getattr(node, "lineno", 1)
                missing.append(f"{path}:{line}:{name} ({len(CHINESE.findall(doc))}zh)")
    assert missing == []


def test_non_directive_comments_contain_chinese_explanation():
    invalid: list[str] = []
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type != tokenize.COMMENT:
                continue
            comment = token.string.strip()
            if comment.startswith(COMMENT_DIRECTIVES):
                continue
            if len(CHINESE.findall(comment)) < MIN_CHINESE_CHARS:
                invalid.append(f"{path}:{token.start[0]}:{comment} ({len(CHINESE.findall(comment))}zh)")
    assert invalid == []
