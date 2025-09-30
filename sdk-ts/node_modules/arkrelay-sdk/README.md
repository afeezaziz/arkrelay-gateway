# ArkRelay TypeScript SDK (sdk-ts)

A minimal TypeScript SDK for interacting with the ArkRelay Gateway and verifying/signing Nostr events in web or Node environments.

## Install

```bash
cd sdk-ts
npm install
npm run build
```

Local development note: when working inside this monorepo without publishing, you can import from the local source instead of the package name:

```ts
import { GatewayClient, computeEventId } from './src';
```

## Usage

### HTTP Client

```ts
import { GatewayClient } from 'arkrelay-sdk-ts';

const client = new GatewayClient('http://localhost:8000', {
  retry: { enabled: true, maxAttempts: 5, backoffBase: 200, backoffFactor: 2.0, jitter: 100 },
});

const session = await client.createSession('npub1...', 'protocol_op', { action_id: 'uuid...', type: 'amm:swap', params: {}, expires_at: 1735689600 });
const status = await client.getCeremonyStatus(session.session_id);
```

### Lightning Operations (for Wallet Developers)

```ts
import { LightningOperations } from 'arkrelay-sdk-ts';

const lightning = new LightningOperations('http://localhost:8000');
const result = await lightning.executeLiftFlow(100000, 'gBTC');
console.log(`Lift initiated: ${result.sessionId}`);
```

### VTXO Operations (for Solver Developers)

```ts
import { VtxoOperations } from 'arkrelay-sdk-ts';

const vtxoOps = new VtxoOperations('http://localhost:8000');
const result = await vtxoOps.executeMultiVtxoFlow('gUSD', 400000000, 'npub1recipient...');
console.log(`Multi-VTXO flow: ${result.sessionId}`);
```

### Nostr Utilities

```ts
import { computeEventId, verifyEvent, hexToNpub, npubToHex } from 'arkrelay-sdk-ts';

const expectedId = computeEventId(ev.pubkey, ev.created_at, ev.kind, ev.tags, ev.content);
const { ok } = await verifyEvent(ev);
```

### React Hook: useCeremonyStatus

```tsx
import { useEffect, useRef, useState } from 'react';
import { GatewayClient } from 'arkrelay-sdk-ts';

type UseCeremonyOpts = { intervalMs?: number };

export function useCeremonyStatus(client: GatewayClient, sessionId: string | null, opts: UseCeremonyOpts = {}) {
  const intervalMs = opts.intervalMs ?? 1000;
  const [status, setStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    async function tick() {
      try {
        const s = await client.getCeremonyStatus(sessionId);
        if (cancelled) return;
        setStatus(s);
        const state = String(s.state ?? s.status ?? '').toLowerCase();
        if (["completed", "finalized", "settled"].includes(state) || ["failed", "expired", "error"].includes(state)) {
          setDone(true);
          if (timer.current) window.clearInterval(timer.current);
        }
      } catch (e: any) {
        if (cancelled) return;
        setError(String(e?.message ?? e));
      }
    }
    tick();
    timer.current = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [client, sessionId, intervalMs]);

  return { status, error, done };
}
```

## Validation (AJV)

An optional JSON Schema validator is provided (mirrors Python's jsonschema usage).

```ts
import { validate31510, validate31511, validate31512 } from 'arkrelay-sdk-ts';

const ok = validate31510(intent);
```

## Examples and Documentation

### Available Examples
- **Lightning Operations**: Complete gBTC lift/land flows (`examples/lightning-operations.ts`)
- **VTXO Operations**: Splitting, multi-VTXO transactions, optimal change (`examples/vtxo-operations.ts`)
- **React Integration**: Live React app with ceremony polling (`examples/react-app/`)

### Running Examples
```bash
# Build the SDK
npm run build

# Run React example
cd examples/react-app
npm install
npm run dev

# Import examples in your code
import { LightningOperations, VtxoOperations } from 'arkrelay-sdk-ts';
```

### Documentation
- [Examples Guide](examples/README.md) - Complete usage examples
- [Nostr Event Flows](../../docs/examples/nostr_flows.md) - Complete event sequences
- [Solver Integration Guide](../../docs/developers/solver-integration.md) - Solver development

## Architecture Patterns

### For Wallet Developers
- Lightning lift/land operations
- Service request patterns (31500/31501/31502)
- Nostr event handling (31510/31511/31512)
- React hooks for session monitoring

### For Solver Developers
- VTXO management (splitting, multi-VTXO transactions)
- Protocol integration (lending, AMM, vaults)
- Multi-protocol support
- Error handling and recovery

## License

MIT

## React Example App

You can try the ceremony polling hook in a live Vite + React example.

```bash
cd sdk-ts/examples/react-app
npm install
npm run dev
# open http://localhost:5173
```

The app imports the SDK directly from the local `sdk-ts/src` and uses the `useCeremonyStatus` hook from `examples/useCeremonyStatus.tsx`.

## Publish (npm)

Before publishing, update `package.json` (name, version, repository, homepage) and ensure only the compiled `dist/` is included (e.g., via `files: ["dist"]`).

```bash
cd sdk-ts
npm run build
npm publish --access public
```

## Releasing (CI/CD)

This repo includes a GitHub Actions workflow to publish the TS SDK to npm when you push a tag of the form `sdk-ts-vX.Y.Z`.

1) Create an npm token with publish rights and add it to the repo as `NPM_TOKEN` secret.
2) Bump the version in `sdk-ts/package.json`.
3) Create and push a tag, e.g.:

```bash
git tag sdk-ts-v0.1.0
git push origin sdk-ts-v0.1.0
```

The workflow at `.github/workflows/release.yml` will build and publish `gateway/sdk-ts` using the token.
