# Releasing

This repository ships two SDKs under `gateway/` with tag-driven release automation:

- Python SDK: `sdk/` → PyPI
- TypeScript SDK: `sdk-ts/` → npm

## Prerequisites

- Configure GitHub repo secrets:
  - `PYPI_API_TOKEN` (PyPI API token with publish rights)
  - `NPM_TOKEN` (npm auth token with publish rights)

## Tag formats

- Python SDK: `sdk-py-vX.Y.Z`
- TypeScript SDK: `sdk-ts-vX.Y.Z`

## Steps

### Python SDK

1) Bump version in `sdk/pyproject.toml` (or run helper):

```bash
activate your venv
cd gateway/sdk
python bump_version.py 0.1.1
# commit and tag
git add pyproject.toml
git commit -m "sdk(py): bump to 0.1.1"
git tag sdk-py-v0.1.1
git push origin main sdk-py-v0.1.1
```

The workflow `.github/workflows/release.yml` will build and publish to PyPI.

### TypeScript SDK

1) Bump version in `sdk-ts/package.json` (or run helper):

```bash
cd gateway/sdk-ts
npm run version:bump:patch
# commit and tag
git add package.json
git commit -m "sdk(ts): bump patch"
git tag sdk-ts-v0.1.1
git push origin main sdk-ts-v0.1.1
```

The workflow `.github/workflows/release.yml` will build and publish to npm.

## Pre-publish checks (CI)

- CI runs on pull requests and main pushes to ensure:
  - Python: `uv run pytest -q` passes
  - TypeScript: `npm run build` succeeds

## Changelogs

- Root changes: `CHANGELOG.md`
- Python SDK changes: `sdk/CHANGELOG.md`
- TypeScript SDK changes: `sdk-ts/CHANGELOG.md`

Keep changelogs up-to-date when bumping versions.
