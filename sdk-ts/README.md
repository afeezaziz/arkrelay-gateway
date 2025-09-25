# ArkRelay TypeScript SDK (sdk-ts)

A minimal TypeScript SDK for interacting with the ArkRelay Gateway and verifying/signing Nostr events in web or Node environments.

## Install

```bash
cd sdk-ts
npm install
npm run build
```

## Usage

### HTTP Client

```ts
import { GatewayClient } from './src';

const client = new GatewayClient('http://localhost:8000', {
  retry: { enabled: true, maxAttempts: 5, backoffBase: 200, backoffFactor: 2.0, jitter: 100 },
});

const session = await client.createSession('npub1...', 'protocol_op', { action_id: 'uuid...', type: 'amm:swap', params: {}, expires_at: 1735689600 });
const status = await client.getCeremonyStatus(session.session_id);
```

### Nostr Utilities

```ts
import { computeEventId, verifyEvent, hexToNpub, npubToHex } from './src';

const expectedId = computeEventId(ev.pubkey, ev.created_at, ev.kind, ev.tags, ev.content);
const { ok } = await verifyEvent(ev);
```

### React Hook: useCeremonyStatus

```tsx
import { useEffect, useRef, useState } from 'react';
import { GatewayClient } from './src';

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
import { validate31510, validate31511, validate31512 } from './src/validation';

const ok = validate31510(intent);
```

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
