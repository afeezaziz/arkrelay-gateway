export type RetryAsyncOptions = {
  maxAttempts: number;
  backoffBaseMs: number; // e.g., 200
  backoffFactor: number; // e.g., 2.0
  jitterMs: number; // e.g., 100
  onRetry?: (attempt: number, error: unknown, sleepMs: number) => void;
};

function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}

export async function withRetryAsync<T>(fn: () => Promise<T>, opts: RetryAsyncOptions): Promise<T> {
  let attempt = 0;
  while (true) {
    try {
      return await fn();
    } catch (err) {
      attempt += 1;
      if (attempt >= opts.maxAttempts) throw err;
      const base = opts.backoffBaseMs * Math.pow(opts.backoffFactor, attempt - 1);
      const jitter = Math.random() * opts.jitterMs;
      const sleepMs = base + jitter;
      try {
        opts.onRetry?.(attempt, err, sleepMs);
      } catch {}
      await sleep(sleepMs);
    }
  }
}
