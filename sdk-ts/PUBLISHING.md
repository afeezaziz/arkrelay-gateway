# Publishing ArkRelay TypeScript SDK

This guide explains how to publish the ArkRelay TypeScript SDK to NPM.

## Prerequisites

1. **NPM Account**: Create an account at [npmjs.com](https://www.npmjs.com/)
2. **Access Token**: Generate an access token from your NPM account settings
3. **GitHub Secrets**: Add `NPM_TOKEN` to your repository secrets

## Manual Publishing

### 1. Build and Test
```bash
cd sdk-ts
npm install
npm run build
npm run publish:dry
```

### 2. Test Publishing (Dry Run)
```bash
node scripts/publish.js --test
```

This builds and validates the package without publishing.

### 3. Production Publishing
```bash
node scripts/publish.js
```

### 4. Publishing with Specific Version
```bash
node scripts/publish.js --version 0.2.0
```

## Automated Publishing (GitHub Actions)

### 1. Setup GitHub Secrets
- Go to your repository settings
- Add a new secret named `NPM_TOKEN`
- Paste your NPM access token

### 2. Create and Push Tag
```bash
# Bump version in package.json
# Tag the release
git tag sdk-ts-v0.1.0
git push origin sdk-ts-v0.1.0
```

The GitHub Actions workflow will automatically:
1. Run tests
2. Build the package
3. Publish to NPM
4. Create a GitHub release

## Package Structure

The published package includes:
- Compiled TypeScript files (`dist/`)
- Source TypeScript files (`src/`)
- Examples (`examples/`)
- Documentation and README

## Installation

After publishing, users can install with:

```bash
npm install arkrelay-sdk
```

## Using Examples

The examples are included in the package:

```typescript
import { LightningOperations, VtxoOperations } from 'arkrelay-sdk-ts';

// Lightning operations
const lightning = new LightningOperations('http://localhost:8000');
const result = await lightning.executeLiftFlow(100000, 'gBTC');

// VTXO operations
const vtxoOps = new VtxoOperations('http://localhost:8000');
const multiResult = await vtxoOps.executeMultiVtxoFlow('gUSD', 400000000, 'npub1recipient...');
```

## Version Management

Follow semantic versioning:
- `0.1.0` - Major breaking changes
- `0.1.1` - Minor feature additions
- `0.1.2` - Patch fixes

## Build Configuration

### TypeScript Configuration
The SDK uses two tsconfig files:
- `tsconfig.json` - Main library build
- `examples/tsconfig.json` - Examples build (optional)

### Package Files
The following files are included in the published package:
- `dist/` - Compiled JavaScript and TypeScript declarations
- `examples/` - TypeScript examples
- `README.md` - Package documentation
- `src/` - Source files for reference

## Troubleshooting

### Common Issues

1. **Build Errors**: Make sure TypeScript compilation succeeds
2. **Test Failures**: Ensure tests pass before publishing
3. **Upload Errors**: Check NPM token and permissions
4. **Version Conflicts**: Ensure version hasn't been published before

### Checking Package

```bash
# Check built package
npm run publish:dry

# Check package contents
npm pack --json

# Install locally to test
npm pack
npm install ./arkrelay-sdk-0.1.0.tgz
```

## Best Practices

1. **Dry run first**: Always use `--test` flag before actual publish
2. **Version carefully**: Follow semantic versioning
3. **Update changelog**: Document changes between versions
4. **Verify installation**: Test installing and using the published package
5. **Monitor issues**: Watch for user feedback and issues

## Example Usage in Projects

### React Integration
```typescript
import { LightningOperations } from 'arkrelay-sdk';

function WalletComponent() {
  const lightning = new LightningOperations('https://gateway.arkrelay.xyz');

  const handleLift = async () => {
    try {
      const result = await lightning.executeLiftFlow(100000, 'gBTC');
      console.log('Lift initiated:', result.sessionId);
    } catch (error) {
      console.error('Lift failed:', error);
    }
  };

  return <button onClick={handleLift}>Execute Lift</button>;
}
```

### Node.js Integration
```typescript
import { VtxoOperations } from 'arkrelay-sdk';

async function main() {
  const vtxoOps = new VtxoOperations('https://gateway.arkrelay.xyz');

  const result = await vtxoOps.executeMultiVtxoFlow(
    'gUSD',
    400000000,
    'npub1recipient...'
  );

  console.log('Multi-VTXO flow:', result.sessionId);
}

main().catch(console.error);
```

## Publishing Checklist

Before publishing, ensure:

- [ ] All tests pass
- [ ] TypeScript compilation succeeds
- [ ] Package builds correctly (`npm run build`)
- [ ] Dry run succeeds (`npm run publish:dry`)
- [ ] Documentation is updated
- [ ] Version number is appropriate
- [ ] Changelog is updated
- [ ] Examples work correctly
- [ ] License is appropriate
- [ ] Repository URLs are correct