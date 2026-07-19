# Blantian Release Identity Design

## Goal

Prepare the existing `0.1.0` release for the GitHub repository
`git@github.com:blantian/lanhu-design-mcp.git` by making every public package
and MCP Registry identity consistently use the `blantian` namespace.

## Public Identity

- Git remote: `git@github.com:blantian/lanhu-design-mcp.git`
- MCP Registry name: `io.github.blantian/lanhu-design-mcp`
- PyPI package name: `lanhu-design-mcp` (unchanged)
- GitHub project URLs: `https://github.com/blantian/lanhu-design-mcp`
- Author display name: `lantian` (unchanged)
- Remove the placeholder author email instead of publishing a fabricated
  `example.com` address.

## Tracked Changes

Update only tracked public release metadata and its contract test:

- `README.md`: MCP Registry ownership marker only.
- `server.json`: server name and repository URL.
- `pyproject.toml`: GitHub project URLs and author metadata.
- `CHANGELOG.md`: release link.
- `tests/test_server_auth.py`: expected Registry server name.
- Git repository configuration: replace the malformed current `origin` with
  the new SSH URL.

## Preserved Content

- Do not rewrite local filesystem paths containing `/Users/buluesky`; these
  describe the current workstation, not the public release identity.
- Do not modify or stage the existing unrelated README hunks, prompt changes,
  or `uv.lock` changes.
- Do not modify untracked `PUBLISHING_GUIDE.md`, `PUBLISHING_CHECKLIST.md`, or
  `publish.sh`; they are stale user-owned files and are not part of the release.
- Do not create or push a Git tag, upload to PyPI, publish to MCP Registry, or
  create a GitHub Release in this identity-migration step.

## Verification

1. Confirm tracked public metadata contains no remaining `buluesky` identity,
   excluding intentional local workstation paths.
2. Run the focused server metadata tests and the complete test suite.
3. Run `mcp-publisher validate`.
4. Build sdist and wheel from the committed release tree.
5. Inspect staged scope so unrelated dirty files remain unstaged.
6. Commit the identity migration, then push `main` to the new `origin`.

## Success Criteria

- GitHub, PyPI metadata, and MCP Registry ownership all point to `blantian`.
- `server.json` validates and the test suite passes.
- The new GitHub repository receives the committed `main` history.
- Existing user-owned working-tree changes remain intact and uncommitted.
- Tagging and external package/Registry publication remain explicit later
  steps requiring separate confirmation.
