# Blantian Release Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the committed Python package, GitHub links, and MCP Registry ownership consistently use `blantian`, then push the verified `main` branch to `git@github.com:blantian/lanhu-design-mcp.git`.

**Architecture:** Treat the GitHub owner as a release identity contract spanning PyPI metadata, MCP Registry metadata, the README ownership marker, and release links. Protect the dirty worktree by changing and staging only named tracked files, with interactive staging for the already-modified README; verify the committed tree from a detached temporary worktree before pushing.

**Tech Stack:** Python packaging (`pyproject.toml`, setuptools), MCP Registry `server.json`, pytest, Git, `uv`, `twine`, `mcp-publisher`.

## Global Constraints

- Public GitHub identity is `blantian`; MCP Registry name is `io.github.blantian/lanhu-design-mcp`.
- PyPI package name and release version remain `lanhu-design-mcp==0.1.0`.
- Author display name remains `lantian`; remove the placeholder author email.
- Do not rewrite local paths containing `/Users/buluesky`.
- Preserve existing unstaged README, prompt, and `uv.lock` changes.
- Do not modify untracked publishing guides/scripts or older plans/specs.
- Do not create/push a tag or publish to PyPI/MCP Registry in this plan.

---

### Task 1: Enforce the Blantian Release Identity

**Files:**
- Modify: `tests/test_server_auth.py`
- Modify: `README.md`
- Modify: `server.json`
- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: GitHub repository identity `blantian/lanhu-design-mcp` and MCP server identity `io.github.blantian/lanhu-design-mcp`.
- Produces: PyPI package metadata and MCP Registry ownership metadata that resolve to the same public repository.

- [ ] **Step 1: Write failing release-identity contract tests**

Update `TestServerJson.test_valid_json` and add the following class to `tests/test_server_auth.py`:

```python
class TestReleaseIdentity:
    def test_public_metadata_uses_blantian(self):
        server = json.loads(Path("server.json").read_text())
        assert server["name"] == "io.github.blantian/lanhu-design-mcp"
        assert server["repository"]["url"] == "https://github.com/blantian/lanhu-design-mcp"

        readme = Path("README.md").read_text()
        assert "<!-- mcp-name: io.github.blantian/lanhu-design-mcp -->" in readme

        pyproject = Path("pyproject.toml").read_text()
        assert 'Homepage = "https://github.com/blantian/lanhu-design-mcp"' in pyproject
        assert 'Repository = "https://github.com/blantian/lanhu-design-mcp"' in pyproject
        assert 'Issues = "https://github.com/blantian/lanhu-design-mcp/issues"' in pyproject
        assert "buluesky@example.com" not in pyproject

        changelog = Path("CHANGELOG.md").read_text()
        assert "https://github.com/blantian/lanhu-design-mcp/releases/tag/v0.1.0" in changelog
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_server_auth.py::TestServerJson::test_valid_json tests/test_server_auth.py::TestReleaseIdentity -q
```

Expected: failures showing the existing `io.github.buluesky/...` name, old GitHub URLs, and placeholder email.

- [ ] **Step 3: Update the five tracked public metadata files**

Make these exact replacements:

```text
README.md
  <!-- mcp-name: io.github.blantian/lanhu-design-mcp -->

server.json
  name: io.github.blantian/lanhu-design-mcp
  repository.url: https://github.com/blantian/lanhu-design-mcp

pyproject.toml
  authors = [{name = "lantian"}]
  Homepage = https://github.com/blantian/lanhu-design-mcp
  Repository = https://github.com/blantian/lanhu-design-mcp
  Issues = https://github.com/blantian/lanhu-design-mcp/issues

CHANGELOG.md
  [0.1.0]: https://github.com/blantian/lanhu-design-mcp/releases/tag/v0.1.0
```

Do not replace `/Users/buluesky` workstation paths and do not edit untracked publishing files.

- [ ] **Step 4: Run focused and complete verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_server_auth.py -q
.venv/bin/python -m pytest -q
mcp-publisher validate
git diff --check
```

Expected: all tests exit 0, publisher prints `server.json is valid`, and diff check is empty.

- [ ] **Step 5: Stage only the identity changes**

Stage the files without pre-existing user edits:

```bash
git add -- server.json pyproject.toml CHANGELOG.md tests/test_server_auth.py
git add -p README.md
```

For `git add -p README.md`, accept only the first-line `mcp-name` identity hunk and reject the existing Cookie-Editor and cc-switch hunks. Verify scope:

```bash
git diff --cached --check
git diff --cached --stat
git diff --cached -- README.md
git diff --cached -- prompt/ uv.lock
```

Expected: the cached README diff contains only the `mcp-name` line; prompt and `uv.lock` cached diffs are empty.

- [ ] **Step 6: Commit the identity migration**

```bash
git commit -m "chore: align release identity with blantian"
```

Expected: one commit containing only the five metadata/test files while unrelated working-tree changes remain unstaged.

---

### Task 2: Verify the Committed Release Tree and Push Main

**Files:**
- Modify: repository-local Git configuration (`origin` URL only)
- Verify: committed tree at `HEAD`

**Interfaces:**
- Consumes: the Task 1 commit and existing empty GitHub repository `git@github.com:blantian/lanhu-design-mcp.git`.
- Produces: a GitHub `main` branch containing the verified committed history; no tag or package publication.

- [ ] **Step 1: Correct and verify the Git remote**

```bash
git remote set-url origin git@github.com:blantian/lanhu-design-mcp.git
git remote get-url origin
git ls-remote origin
```

Expected: `git remote get-url origin` prints the exact SSH URL; `git ls-remote` exits 0 (an empty result is valid for a new repository).

- [ ] **Step 2: Build and inspect artifacts from a detached clean worktree**

```bash
LANHU_RELEASE_VERIFY_DIR=$(mktemp -d)
git worktree add --detach "$LANHU_RELEASE_VERIFY_DIR" HEAD
(
  cd "$LANHU_RELEASE_VERIFY_DIR"
  uv build --no-sources
  uvx twine check dist/*
)
git worktree remove "$LANHU_RELEASE_VERIFY_DIR"
```

Expected: sdist and wheel build successfully and both pass `twine check`. The user's dirty primary worktree is unchanged.

- [ ] **Step 3: Reconfirm branch and dirty-worktree safety**

```bash
git branch --show-current
git status --short
git log -2 --oneline
```

Expected: branch is `main`; only the pre-existing README, prompt, `uv.lock`, `.ccb`, and untracked user files remain dirty; the identity commit is at `HEAD`.

- [ ] **Step 4: Push the verified main branch**

```bash
git push -u origin main
```

Expected: GitHub accepts the branch and configures `main` to track `origin/main`.

- [ ] **Step 5: Verify the remote branch without mutating release state**

```bash
git ls-remote --heads origin main
git status -sb
```

Expected: `refs/heads/main` resolves to local `HEAD`; the branch reports tracking `origin/main`. Do not create a `v0.1.0` tag yet.
