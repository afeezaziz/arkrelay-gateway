export type Json = Record<string, unknown>;

export type RetryOptions = {
  enabled?: boolean;
  maxAttempts?: number;
  backoffBase?: number;
  backoffFactor?: number;
  jitter?: number;
  retryOnStatus?: number[]; // e.g., [429, 502, 503, 504]
};

export type GatewayClientOptions = {
  fetchImpl?: typeof fetch;
  retry?: RetryOptions;
};

export class RetriableHttpError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'RetriableHttpError';
  }
}

import { withRetryAsync } from './retry';

export class GatewayClient {
  private readonly fetchImpl: typeof fetch;
  private readonly retry: Required<RetryOptions>;

  constructor(public readonly baseUrl: string, options: GatewayClientOptions = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl ?? fetch;
    const r = options.retry ?? {};
    this.retry = {
      enabled: r.enabled ?? false,
      maxAttempts: r.maxAttempts ?? 5,
      backoffBase: r.backoffBase ?? 200,
      backoffFactor: r.backoffFactor ?? 2.0,
      jitter: r.jitter ?? 100,
      retryOnStatus: r.retryOnStatus ?? [429, 502, 503, 504],
    } as Required<RetryOptions>;
  }

  private async _get(path: string): Promise<any> {
    const call = async (): Promise<any> => {
      const res = await this.fetchImpl(`${this.baseUrl}${path}`, { method: 'GET' });
      if (!res.ok) {
        const text = await res.text();
        const err = new Error(`GET ${path} -> ${res.status}: ${text}`);
        if (this.retry.retryOnStatus.includes(res.status)) {
          throw new RetriableHttpError(res.status, err.message);
        }
        throw err;
      }
      const text = await res.text();
      return text ? JSON.parse(text) : {};
    };

    if (!this.retry.enabled) return call();
    return withRetryAsync(call, {
      maxAttempts: this.retry.maxAttempts,
      backoffBaseMs: this.retry.backoffBase,
      backoffFactor: this.retry.backoffFactor,
      jitterMs: this.retry.jitter,
    });
  }

  private async _post(path: string, body?: Json): Promise<any> {
    const call = async (): Promise<any> => {
      const res = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const text = await res.text();
        const err = new Error(`POST ${path} -> ${res.status}: ${text}`);
        if (this.retry.retryOnStatus.includes(res.status)) {
          throw new RetriableHttpError(res.status, err.message);
        }
        throw err;
      }
      const text = await res.text();
      return text ? JSON.parse(text) : {};
    };

    if (!this.retry.enabled) return call();
    return withRetryAsync(call, {
      maxAttempts: this.retry.maxAttempts,
      backoffBaseMs: this.retry.backoffBase,
      backoffFactor: this.retry.backoffFactor,
      jitterMs: this.retry.jitter,
    });
  }

  // Sessions & signing
  async createSession(user_pubkey: string, session_type: string, intent_data: Json): Promise<any> {
    return this._post(`/sessions/create`, { user_pubkey, session_type, intent_data });
  }

  async createChallenge(session_id: string, challenge_data: Json, context?: Json): Promise<any> {
    const payload: Json = { challenge_data };
    if (context) payload.context = context;
    return this._post(`/sessions/${session_id}/challenge`, payload);
  }

  async startCeremony(session_id: string): Promise<any> {
    return this._post(`/signing/ceremony/start`, { session_id });
  }

  async getCeremonyStatus(session_id: string): Promise<any> {
    return this._get(`/signing/ceremony/${session_id}/status`);
  }

  // Asset helpers (optional dev/ops)
  async createAsset(asset_id: string, name: string, ticker: string, total_supply = 0): Promise<any> {
    return this._post(`/assets`, { asset_id, name, ticker, total_supply });
  }

  async getAssetInfo(asset_id: string): Promise<any> {
    return this._get(`/assets/${asset_id}`);
  }

  async mintAsset(asset_id: string, user_pubkey: string, amount: number): Promise<any> {
    return this._post(`/assets/${asset_id}/mint`, { user_pubkey, amount });
  }

  async transferAsset(sender_pubkey: string, recipient_pubkey: string, asset_id: string, amount: number): Promise<any> {
    return this._post(`/assets/transfer`, { sender_pubkey, recipient_pubkey, asset_id, amount });
  }

  async getUserBalances(user_pubkey: string): Promise<any> {
    return this._get(`/balances/${user_pubkey}`);
  }
}
