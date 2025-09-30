import { useEffect, useRef, useState } from 'react';
import { GatewayClient } from '../src';

export type UseCeremonyOpts = { intervalMs?: number };

export function useCeremonyStatus(client: GatewayClient, sessionId: string | null, opts: UseCeremonyOpts = {}) {
  const intervalMs = opts.intervalMs ?? 1000;
  const [status, setStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    const sid = sessionId;
    if (!sid) return;
    let cancelled = false;
    async function tick() {
      try {
        const s = await client.getCeremonyStatus(sid);
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
