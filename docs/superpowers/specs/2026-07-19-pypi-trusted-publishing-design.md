# PyPI Trusted Publishing Design

## Goal

Publish `lanhu-design-mcp==0.1.0` to PyPI without a long-lived API token by
using GitHub Actions OIDC Trusted Publishing. The workflow must preserve a
small trust boundary, require a human approval before upload, and build the
already-reviewed `v0.1.0` tag.

## Trigger and First Release

- The workflow file is `.github/workflows/release.yml` on the default
  `main` branch.
- It runs only for the GitHub `release.published` event.
- The existing annotated `v0.1.0` tag remains unchanged and points to
  `eef3cd31268e91e8aebc5925161331911319a2a4`.
- After the workflow reaches `main`, publishing a GitHub Release for the
  existing tag triggers the first PyPI upload. No tag deletion or force-push
  is needed.
- The build job explicitly checks out `github.event.release.tag_name`, so
  release artifacts come from the tagged, reviewed source rather than from a
  later `main` commit.

## Workflow Architecture

The workflow has two isolated jobs.

### Build Job

The build job has read-only repository permission and no OIDC permission. It:

1. checks out the released tag with persisted Git credentials disabled;
2. sets up Python 3.12;
3. verifies the release tag is exactly `v<project.version>`;
4. verifies `pyproject.toml`, `server.json`, and
   `server.json.packages[0].version` contain the same version;
5. builds the sdist and wheel with `python -m build`;
6. validates both distributions with `python -m twine check dist/*`;
7. uploads only `dist/` as a GitHub Actions artifact.

### Publish Job

The publish job depends on the build job and does not check out or execute
repository code. It:

1. binds to the GitHub Environment named `pypi`;
2. receives `id-token: write` only at job scope;
3. downloads the build artifact into `dist/`;
4. invokes `pypa/gh-action-pypi-publish` using Trusted Publishing;
5. leaves the action's default PyPI attestations enabled.

The workflow and all third-party Actions are pinned to immutable commit SHAs.
Comments beside each SHA record the corresponding upstream release tag so
future updates are reviewable.

## PyPI Configuration

Before publishing the GitHub Release, the user creates a pending publisher at
`https://pypi.org/manage/account/publishing/` with these exact values:

- PyPI project name: `lanhu-design-mcp`
- GitHub owner: `blantian`
- GitHub repository: `lanhu-design-mcp`
- Workflow filename: `release.yml`
- Environment name: `pypi`

The pending publisher creates the PyPI project on first successful OIDC
upload. It does not reserve the package name before that upload.

## GitHub Environment

Create a repository Environment named `pypi`. Configure at least one required
reviewer so the publish job pauses before receiving its deployment approval.
The workflow stores no PyPI API token and references no repository secret.

## Contract Tests and Validation

Add deterministic repository tests that verify:

- `.github/workflows/release.yml` exists;
- the only publishing trigger is `release: types: [published]`;
- the build checkout uses the Release tag explicitly;
- the version gate reads both `pyproject.toml` and `server.json`;
- the publish job uses environment `pypi` and job-scoped `id-token: write`;
- the publish action is present and no API token, password, or secret reference
  exists;
- all `uses:` references are pinned to full 40-character commit SHAs.

Also run the full Python test suite, `mcp-publisher validate`, `actionlint` (or
an equivalent semantic GitHub Actions validator), a clean local package build,
and `twine check` before pushing the workflow.

## Failure Handling

- Version mismatch: fail the build before artifact upload.
- Build or metadata validation failure: publish job never starts.
- Missing/mismatched PyPI pending publisher: the publish action fails closed;
  correct the PyPI owner/repository/workflow/environment fields, then rerun
  the failed workflow without changing the tag.
- Environment approval denied or absent: no OIDC upload occurs.
- PyPI reports version already exists: do not overwrite or delete the tag;
  inspect whether `0.1.0` was already published, then prepare a new version in
  a separate release change if necessary.

## Scope Boundaries

- Do not add TestPyPI in the first workflow.
- Do not add `workflow_dispatch`, tag-push, branch-push, or pull-request
  publishing triggers.
- Do not store PyPI credentials in GitHub Secrets.
- Do not change `v0.1.0`, package contents, package version, MCP Registry
  metadata, or managed Lanhu authentication behavior.
- Preserve the existing unstaged README, prompt, `uv.lock`, and untracked user
  files.

## Success Criteria

- Workflow security and release contract tests pass.
- Workflow is pushed to `main` without altering `v0.1.0`.
- PyPI pending publisher and GitHub `pypi` Environment use the exact values
  above.
- Publishing the GitHub Release pauses for environment approval, then uploads
  the two checked distributions through OIDC with no long-lived token.
- `https://pypi.org/project/lanhu-design-mcp/0.1.0/` becomes available after
  the approved workflow completes.
