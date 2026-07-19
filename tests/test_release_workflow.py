from __future__ import annotations

import re
from pathlib import Path


WORKFLOW = Path(".github/workflows/release.yml")


def workflow_text() -> str:
    assert WORKFLOW.is_file(), "release workflow is missing"
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_published_is_the_only_trigger():
    text = workflow_text()
    assert "on:\n  release:\n    types: [published]" in text
    for forbidden in ("workflow_dispatch", "pull_request:", "push:", "schedule:"):
        assert forbidden not in text


def test_release_tag_and_versions_are_validated_before_build():
    text = workflow_text()
    assert "ref: ${{ github.event.release.tag_name }}" in text
    assert 'RELEASE_TAG: ${{ github.event.release.tag_name }}' in text
    assert 'Path("pyproject.toml")' in text
    assert 'Path("server.json")' in text
    assert 'server["packages"][0]["version"]' in text
    assert 'expected_tag = f"v{project_version}"' in text
    assert text.index("Verify release identity and versions") < text.index("Build distributions")


def test_oidc_permission_is_scoped_to_pypi_environment_job():
    text = workflow_text()
    assert text.count("id-token: write") == 1
    publish = text.split("  publish-to-pypi:", 1)[1]
    assert "environment:\n      name: pypi" in publish
    assert "permissions:\n      id-token: write\n      contents: read" in publish
    assert "https://pypi.org/p/lanhu-design-mcp" in publish


def test_build_and_publish_jobs_are_separated():
    text = workflow_text()
    build, publish = text.split("  publish-to-pypi:", 1)
    assert "python -m build" in build
    assert "python -m twine check dist/*" in build
    assert "actions/upload-artifact" in build
    assert "pypa/gh-action-pypi-publish" not in build
    assert "needs: build-distributions" in publish
    assert "actions/download-artifact" in publish
    assert "pypa/gh-action-pypi-publish" in publish
    assert "actions/checkout" not in publish


def test_actions_are_pinned_to_reviewed_commits():
    text = workflow_text()
    expected = {
        "actions/checkout": "df4cb1c069e1874edd31b4311f1884172cec0e10",
        "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
        "actions/upload-artifact": "330a01c490aca151604b8cf639adc76d48f6c5d4",
        "actions/download-artifact": "634f93cb2916e3fdff6788551b99b062d0335ce0",
        "pypa/gh-action-pypi-publish": "cef221092ed1bacb1cc03d23a2d87d1d172e277b",
    }
    uses = re.findall(r"uses:\s+([^@\s]+)@([0-9a-f]{40})", text)
    assert dict(uses) == expected
    assert len(re.findall(r"^\s*- uses:", text, flags=re.MULTILINE)) == len(uses)


def test_workflow_contains_no_long_lived_credentials():
    text = workflow_text().lower()
    assert "${{ secrets." not in text
    assert "api_token" not in text
    assert "password" not in text
    assert "attestations: false" not in text
