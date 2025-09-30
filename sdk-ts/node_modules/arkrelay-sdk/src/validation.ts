import Ajv, { JSONSchemaType, DefinedError } from 'ajv';

export type ValidateResult = { valid: boolean; errors?: string[] };

const ajv = new Ajv({ allErrors: true, strict: false });

// ---- 31510 Intent ----
export interface Intent31510 {
  action_id: string;
  type: string;
  params: Record<string, unknown>;
  expires_at: number; // unix seconds
  [key: string]: unknown;
}

const schema31510 = {
  type: 'object',
  properties: {
    action_id: { type: 'string' },
    type: { type: 'string' },
    params: { type: 'object', additionalProperties: true },
    expires_at: { type: 'integer' },
  },
  required: ['action_id', 'type', 'params', 'expires_at'],
  additionalProperties: true,
};

// ---- 31511 Challenge ----
export interface Challenge31511 {
  session_id: string;
  type: 'sign_tx' | 'sign_payload';
  payload_to_sign: string;
  [key: string]: unknown;
}

const schema31511: JSONSchemaType<Challenge31511> = {
  type: 'object',
  properties: {
    session_id: { type: 'string' },
    type: { type: 'string', enum: ['sign_tx', 'sign_payload'] as any },
    payload_to_sign: { type: 'string' },
  },
  required: ['session_id', 'type', 'payload_to_sign'],
  additionalProperties: true,
} as any;

// ---- 31512 Response ----
export interface Response31512 {
  session_id: string;
  signature: string;
  [key: string]: unknown;
}

const schema31512 = {
  type: 'object',
  properties: {
    session_id: { type: 'string' },
    signature: { type: 'string' },
  },
  required: ['session_id', 'signature'],
  additionalProperties: true,
};

const validateIntent = ajv.compile(schema31510);
const validateChallenge = ajv.compile(schema31511);
const validateResponse = ajv.compile(schema31512);

function formatErrors(errors: DefinedError[] | null | undefined): string[] | undefined {
  if (!errors) return undefined;
  return errors.map((e) => `${e.instancePath || '/'} ${e.message || ''}`.trim());
}

export function validate31510(obj: unknown): boolean {
  return !!validateIntent(obj);
}

export function validate31511(obj: unknown): boolean {
  return !!validateChallenge(obj);
}

export function validate31512(obj: unknown): boolean {
  return !!validateResponse(obj);
}

export function validate31510Detailed(obj: unknown): ValidateResult {
  const valid = !!validateIntent(obj);
  return { valid, errors: valid ? undefined : formatErrors(validateIntent.errors as any) };
}

export function validate31511Detailed(obj: unknown): ValidateResult {
  const valid = !!validateChallenge(obj);
  return { valid, errors: valid ? undefined : formatErrors(validateChallenge.errors as any) };
}

export function validate31512Detailed(obj: unknown): ValidateResult {
  const valid = !!validateResponse(obj);
  return { valid, errors: valid ? undefined : formatErrors(validateResponse.errors as any) };
}
