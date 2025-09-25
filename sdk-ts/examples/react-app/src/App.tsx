import React, { useMemo, useState } from 'react';
import { GatewayClient } from '../../../src';
import { useCeremonyStatus } from '../../useCeremonyStatus';

export default function App() {
  const [sessionId, setSessionId] = useState<string>('');
  const client = useMemo(() => new GatewayClient('http://localhost:8000', {
    retry: { enabled: true }
  }), []);

  const { status, error, done } = useCeremonyStatus(client, sessionId || null, { intervalMs: 1500 });

  return (
    <div style={{ padding: 20, fontFamily: 'Inter, system-ui, Arial, sans-serif' }}>
      <h1>ArkRelay Ceremony Status</h1>
      <label>
        Session ID:&nbsp;
        <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} placeholder="sess_..." style={{ width: 320 }} />
      </label>
      <pre style={{ background: '#111', color: '#0f0', padding: 12, marginTop: 16 }}>
        {JSON.stringify({ done, error, status }, null, 2)}
      </pre>
    </div>
  );
}
