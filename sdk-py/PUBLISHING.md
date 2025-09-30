# Publishing ArkRelay Python SDK

This guide explains how to publish the ArkRelay Python SDK to PyPI.

## Prerequisites

1. **PyPI Account**: Create an account at [PyPI](https://pypi.org/)
2. **API Token**: Generate an API token from your PyPI account settings
3. **GitHub Secrets**: Add `PYPI_API_TOKEN` to your repository secrets

## Manual Publishing

### 1. Test Publishing (Recommended)
```bash
cd sdk-py
python scripts/publish.py --test
```

This publishes to [Test PyPI](https://test.pypi.org/) where you can verify everything works.

### 2. Production Publishing
```bash
cd sdk-py
python scripts/publish.py
```

### 3. Publishing with Specific Version
```bash
cd sdk-py
python scripts/publish.py --version 0.2.0
```

## Automated Publishing (GitHub Actions)

### 1. Setup GitHub Secrets
- Go to your repository settings
- Add a new secret named `PYPI_API_TOKEN`
- Paste your PyPI API token

### 2. Create and Push Tag
```bash
# Bump version in pyproject.toml
# Tag the release
git tag sdk-py-v0.1.0
git push origin sdk-py-v0.1.0
```

The GitHub Actions workflow will automatically:
1. Run tests
2. Build the package
3. Publish to PyPI
4. Create a GitHub release

## Package Structure

The published package includes:
- Core SDK modules (`sdk/`)
- Examples (`examples/`)
- Documentation (`docs/`)
- README files

## Installation

After publishing, users can install with:

```bash
# From PyPI
pip install arkrelay

# From Test PyPI (for testing)
pip install --index-url https://test.pypi.org/simple/ arkrelay
```

## Using Examples

The examples are included in the package:

```python
from arkrelay.examples import run_example

# Run a lightning example
result = run_example('lightning', amount=100000, asset_id='gBTC')

# Run a VTXO example
result = run_example('vtxo', asset_id='gUSD', amount=400000000, recipient='npub1recipient...')
```

## Version Management

Follow semantic versioning:
- `0.1.0` - Major breaking changes
- `0.1.1` - Minor feature additions
- `0.1.2` - Patch fixes

## Troubleshooting

### Common Issues

1. **Build Errors**: Make sure all dependencies are listed in `pyproject.toml`
2. **Test Failures**: Ensure tests pass before publishing
3. **Upload Errors**: Check PyPI token and permissions
4. **Version Conflicts**: Ensure version hasn't been published before

### Checking Package

```bash
# Check built package
twine check dist/*

# Install locally to test
pip install dist/arkrelay-0.1.0-py3-none-any.whl
```

## Best Practices

1. **Test on Test PyPI first**: Always test on Test PyPI before production
2. **Version carefully**: Follow semantic versioning
3. **Update changelog**: Document changes between versions
4. **Verify installation**: Test installing and using the published package
5. **Monitor issues**: Watch for user feedback and issues