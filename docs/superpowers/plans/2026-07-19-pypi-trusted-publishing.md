# PyPI Trusted Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a release-triggered GitHub Actions workflow that builds the existing `v0.1.0` tag and publishes `lanhu-design-mcp` to PyPI through OIDC Trusted Publishing after GitHub Environment approval.

**Architecture:** Separate unprivileged package construction from the OIDC-enabled publish job. Pin every third-party Action to an immutable commit, enforce tag/package/Registry version consistency before artifact upload, and keep first-release account configuration as an explicit user-controlled gate.

**Tech Stack:** GitHub Actions, Python 3.12, `build`, `twine`, PyPI Trusted Publishing, pytest, zizmor.

## Global Constraints

- Workflow path is exactly `.github/workflows/release.yml`.
- The only trigger is GitHub `release` with `types: [published]`; do not add `workflow_dispatch`, push, tag-push, pull-request, or schedule triggers.
- Build the tag in `github.event.release.tag_name`, not the latest `main` tree.
- PyPI project is `lanhu-design-mcp`; GitHub owner/repository are `blantian/lanhu-design-mcp`.
- PyPI workflow filename is `release.yml`; GitHub Environment is `pypi`.
- Only the publish job receives `id-token: write`; the build job receives read-only repository access.
- Store no PyPI token, password, or GitHub secret reference.
- Keep PyPI attestations enabled.
- All `uses:` references are pinned to the exact 40-character SHAs specified below.
- Do not change or recreate `v0.1.0`; it remains at `eef3cd31268e91e8aebc5925161331911319a2a4`.
- Do not change package version, package contents, MCP Registry metadata, or Lanhu authentication behavior.
- Preserve existing unstaged README, prompt, `uv.lock`, and untracked user files.

---

### Task 1: Add the Trusted Publishing Workflow and Contract Tests

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `tests/test_release_workflow.py`

**Interfaces:**
- Consumes: annotated release tag `v0.1.0`, `pyproject.toml` project version, `server.json` server/package versions.
- Produces: GitHub artifact `python-package-distributions` containing `dist/*.tar.gz` and `dist/*.whl`; OIDC publish job bound to Environment `pypi`.

- [ ] **Step 1: Write the failing workflow contract tests**

Create `tests/test_release_workflow.py`:

```python
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
```

- [ ] **Step 2: Run the contract test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_workflow.py -q
```

Expected: FAIL with `release workflow is missing` before the workflow is created.

- [ ] **Step 3: Create the pinned release workflow**

Create `.github/workflows/release.yml` exactly as follows:

```yaml
name: Publish Python distribution to PyPI

on:
  release:
    types: [published]

permissions:
  contents: read

concurrency:
  group: pypi-${{ github.event.release.tag_name }}
  cancel-in-progress: false

jobs:
  build-distributions:
    name: Build release distributions
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
        with:
          ref: ${{ github.event.release.tag_name }}
          persist-credentials: false

      - name: Set up Python
        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
        with:
          python-version: "3.12"

      - name: Verify release identity and versions
        env:
          RELEASE_TAG: ${{ github.event.release.tag_name }}
        run: |
          python - <<'PY'
          import json
          import os
          import tomllib
          from pathlib import Path

          project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
          server = json.loads(Path("server.json").read_text(encoding="utf-8"))
          project_version = project["project"]["version"]
          expected_tag = f"v{project_version}"

          assert project["project"]["name"] == "lanhu-design-mcp"
          assert os.environ["RELEASE_TAG"] == expected_tag
          assert server["name"] == "io.github.blantian/lanhu-design-mcp"
          assert server["version"] == project_version
          assert server["packages"][0]["identifier"] == "lanhu-design-mcp"
          assert server["packages"][0]["version"] == project_version
          PY

      - name: Install build tooling
        run: python -m pip install --disable-pip-version-check build twine

      - name: Build distributions
        run: python -m build

      - name: Check distribution metadata
        run: python -m twine check dist/*

      - name: Upload distribution artifact
        uses: actions/upload-artifact@330a01c490aca151604b8cf639adc76d48f6c5d4 # v5.0.0
        with:
          name: python-package-distributions
          path: dist/
          if-no-files-found: error
          retention-days: 7

  publish-to-pypi:
    name: Publish distributions to PyPI
    needs: build-distributions
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/lanhu-design-mcp
    permissions:
      id-token: write
      contents: read
    steps:
      - name: Download distribution artifact
        uses: actions/download-artifact@634f93cb2916e3fdff6788551b99b062d0335ce0 # v5.0.0
        with:
          name: python-package-distributions
          path: dist/

      - name: Publish distributions to PyPI
        uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
```

- [ ] **Step 4: Run focused tests and semantic/security validation**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_workflow.py -q
uvx zizmor --offline --strict-collection --collect=workflows .github/workflows/release.yml
```

Expected: all workflow contract tests pass; zizmor exits 0 with no findings or collection errors.

- [ ] **Step 5: Run repository and package verification**

Run:

```bash
.venv/bin/python -m pytest -q
mcp-publisher validate
git diff --check
LANHU_TRUSTED_PUBLISHING_BUILD_DIR=$(mktemp -d)
git worktree add --detach "$LANHU_TRUSTED_PUBLISHING_BUILD_DIR" HEAD
(
  cd "$LANHU_TRUSTED_PUBLISHING_BUILD_DIR"
  uv build --no-sources
  uvx twine check dist/*
)
git worktree remove "$LANHU_TRUSTED_PUBLISHING_BUILD_DIR"
```

Expected: full suite and Registry validation pass; sdist/wheel build and both pass Twine metadata checks; temporary worktree is removed.

- [ ] **Step 6: Commit only the workflow and contract tests**

```bash
git add -- .github/workflows/release.yml tests/test_release_workflow.py
git diff --cached --check
git diff --cached --stat
git commit -m "ci: publish releases with PyPI OIDC"
```

Expected: exactly the two new files are committed; existing README, prompt, `uv.lock`, and untracked user files remain unstaged.

---

### Task 2: Push the Workflow Without Triggering a Release

**Files:**
- Verify: repository and remote Git state only

**Interfaces:**
- Consumes: Task 1 workflow commit on `main`; existing `v0.1.0` tag at `eef3cd31268e91e8aebc5925161331911319a2a4`.
- Produces: reviewed workflow on `origin/main`; no workflow run and no package upload yet.

- [ ] **Step 1: Verify the tag remains immutable**

```bash
test "$(git rev-parse refs/tags/v0.1.0^{})" = "eef3cd31268e91e8aebc5925161331911319a2a4"
test "$(git ls-remote --tags origin 'refs/tags/v0.1.0^{}' | awk '{print $1}')" = "eef3cd31268e91e8aebc5925161331911319a2a4"
```

Expected: both commands exit 0.

- [ ] **Step 2: Push only main and verify the remote SHA**

```bash
git push origin main
test "$(git ls-remote --heads origin main | awk '{print $1}')" = "$(git rev-parse HEAD)"
```

Expected: `main` updates successfully; no release event is emitted because no GitHub Release was published.

- [ ] **Step 3: Verify no tag or package state changed**

```bash
git ls-remote --tags origin 'v0.1.0*'
curl -sS -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/lanhu-design-mcp/0.1.0/json
git status -sb
```

Expected: remote annotated tag still dereferences to `eef3cd3`; PyPI returns 404 before first publication; primary dirty files remain unchanged.

---

### Task 3: Configure Trust and Publish the Existing GitHub Release

**Files:**
- External configuration only: PyPI account and GitHub repository settings

**Interfaces:**
- Consumes: `release.yml` on `origin/main`, existing tag `v0.1.0`, reviewed GitHub workflow commit.
- Produces: PyPI project/version `lanhu-design-mcp==0.1.0` and signed attestations.

- [ ] **Step 1: Register the PyPI pending publisher**

Open `https://pypi.org/manage/account/publishing/` and submit these exact values:

```text
PyPI project name: lanhu-design-mcp
GitHub owner: blantian
GitHub repository: lanhu-design-mcp
Workflow filename: release.yml
Environment name: pypi
```

Expected: PyPI lists a pending publisher with all five values exactly matching.

- [ ] **Step 2: Create and protect the GitHub Environment**

Open `https://github.com/blantian/lanhu-design-mcp/settings/environments`, create `pypi`, and add the user-controlled required reviewer.

Expected: the `pypi` Environment exists and deployments require approval; it contains no PyPI secret.

- [ ] **Step 3: Publish a GitHub Release for the existing tag**

Open `https://github.com/blantian/lanhu-design-mcp/releases/new`, select the existing `v0.1.0` tag, set title `v0.1.0`, use the committed changelog as release notes, and publish the Release.

Expected: the `Publish Python distribution to PyPI` workflow starts; build job completes and publish job waits for `pypi` Environment approval.

- [ ] **Step 4: Approve the deployment and verify publication**

Approve the waiting `pypi` Environment deployment in GitHub Actions, then verify:

```bash
curl -f https://pypi.org/pypi/lanhu-design-mcp/0.1.0/json
LANHU_PYPI_VERIFY_DIR=$(mktemp -d)
uv venv "$LANHU_PYPI_VERIFY_DIR/.venv"
uv pip install --python "$LANHU_PYPI_VERIFY_DIR/.venv/bin/python" "lanhu-design-mcp==0.1.0"
"$LANHU_PYPI_VERIFY_DIR/.venv/bin/lanhu-design-mcp" --help
```

Expected: PyPI JSON is available, clean installation succeeds, and the installed CLI prints usage without importing or downloading a Playwright browser.

- [ ] **Step 5: Publish metadata to MCP Registry only after PyPI succeeds**

From the committed project checkout:

```bash
mcp-publisher validate
mcp-publisher login github
mcp-publisher publish
curl -f "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.blantian/lanhu-design-mcp"
```

Expected: Registry publication succeeds and the search result contains `io.github.blantian/lanhu-design-mcp` version `0.1.0`.
