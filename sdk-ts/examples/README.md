# ArkRelay TypeScript SDK Examples

This directory contains comprehensive examples demonstrating how to use the ArkRelay TypeScript SDK for wallet and solver development.

## Available Examples

### React Wallet Integration
```bash
cd examples/react-app
npm install
npm run dev
```

### TypeScript Examples
```typescript
// Import from gateway root directory
import { GatewayClient } from '../../src';
import { LightningOperations } from '../lightning-operations';
import { VtxoOperations } from '../vtxo-operations';

// Initialize client
const client = new GatewayClient('http://localhost:8000', { retryEnabled: true });

// Lightning operations
const lightning = new LightningOperations('http://localhost:8000');

// Execute lift flow
const liftResult = await lightning.executeLiftFlow(100000, 'gBTC');
console.log('Lift initiated:', liftResult.sessionId);
```

## SDK Integration

### Basic Usage

```typescript
import { GatewayClient, verifyEvent } from '@arkrelay/sdk-ts';

// Initialize client
const client = new GatewayClient('https://gateway.arkrelay.io');

// For wallet developers
const intent = {
  actionId: 'uuid-...',
  type: 'amm:swap',
  params: { poolId: 'LP-gBTC-gUSD', inAmount: 50000 },
  expiresAt: 1735689600
};

// For solver developers
const sessionId = await client.createSession({
  userPubkey: 'npub1user...',
  sessionType: 'amm_swap',
  intentData: intent
});

const challenge = await client.createChallenge(sessionId, {
  payloadToSign: '0x...',
  type: 'sign_tx',
  context: { human: 'Authorize swap' }
});
```

### React Hook Example

```typescript
import { useCeremonyStatus } from './useCeremonyStatus';

function WalletComponent() {
  const [sessionId, setSessionId] = useState<string>('');
  const { status, loading, error } = useCeremonyStatus(sessionId);

  const handleLift = async () => {
    const result = await lightning.executeLiftFlow(100000, 'gBTC');
    setSessionId(result.sessionId);
  };

  return (
    <div>
      <button onClick={handleLift}>Execute Lift</button>
      {loading && <p>Processing...</p>}
      {status && <p>Status: {status.status}</p>}
      {error && <p>Error: {error.message}</p>}
    </div>
  );
}
```

## Key Concepts

### Nostr Event Flow
- **31500**: Service requests (user → gateway)
- **31501**: Service responses (gateway → user)
- **31502**: Service notifications (ongoing updates)
- **31510**: Action intents (user → gateway)
- **31511/31512**: Signing challenges/responses
- **31340**: Transaction confirmations (gateway → public)
- **31341**: Transaction failures (gateway → user)

### VTXO Management
- **Split**: Divide large VTXOs into smaller denominations
- **Multi-VTXO**: Combine multiple VTXOs for larger transfers
- **Optimal Change**: Create change VTXOs efficiently

### Architecture Patterns
- **Dumb Gateway**: Gateway handles only VTXO/signing, solvers handle business logic
- **Solver Integration**: External DeFi services using gateway for settlement
- **Asset Support**: Multi-asset support with Taproot asset tagging

## Documentation

- [Nostr Event Flows](../../docs/examples/nostr_flows.md) - Complete event sequences
- [Solver Integration Guide](../../docs/developers/solver-integration.md) - Solver development guide
- [Solver Guide](../../docs/developers/solver-guide.md) - Advanced integration patterns

## Development

### Setting up Examples

1. Install dependencies:
```bash
cd sdk-ts
npm install
```

2. Build the SDK:
```bash
npm run build
```

3. Run React example:
```bash
cd examples/react-app
npm install
npm run dev
```

### TypeScript Configuration

The examples are configured with:
- Strict TypeScript mode
- ES modules
- Modern React with TypeScript
- Vite for fast development

### Contributing

When adding new examples:
1. Follow TypeScript best practices
2. Include proper error handling
3. Add comprehensive comments
4. Use React hooks for state management
5. Update this README

## Support

For issues and questions:
- Check the [main documentation](../../docs/)
- Review [Nostr event flows](../../docs/examples/nostr_flows.md)
- See [solver integration guide](../../docs/developers/solver-integration.md)