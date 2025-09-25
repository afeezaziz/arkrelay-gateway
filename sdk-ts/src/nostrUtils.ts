import { schnorr } from '@noble/secp256k1';
import { sha256 } from '@noble/hashes/sha256';
import { bech32 } from 'bech32';

export type NostrEvent = {
  id: string;
  pubkey: string; // 64-hex x-only
  created_at: number;
  kind: number;
  tags: any[];
  content: string;
  sig: string; // 64-hex schnorr
};

function utf8Bytes(str: string): Uint8Array {
  return new TextEncoder().encode(str);
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function hexToBytes(hex: string): Uint8Array {
  const h = hex.startsWith('0x') ? hex.slice(2) : hex;
  if (h.length % 2) throw new Error('invalid hex');
  const arr = new Uint8Array(h.length / 2);
  for (let i = 0; i < arr.length; i++) arr[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  return arr;
}

function serializeEvent0(pubkeyHex: string, created_at: number, kind: number, tags: any[], content: string): Uint8Array {
  const json = JSON.stringify([0, pubkeyHex.toLowerCase(), created_at, kind, tags, content]);
  return utf8Bytes(json);
}

export function computeEventId(pubkeyHex: string, created_at: number, kind: number, tags: any[], content: string): string {
  const ser = serializeEvent0(pubkeyHex, created_at, kind, tags, content);
  return bytesToHex(sha256(ser));
}

export async function verifyEvent(event: NostrEvent): Promise<{ ok: boolean; idMatches: boolean; signatureValid: boolean; expectedId: string }>{
  const expectedId = computeEventId(event.pubkey, event.created_at, event.kind, event.tags, event.content);
  const idMatches = expectedId === event.id.toLowerCase();
  let signatureValid = false;
  try {
    const msg32 = hexToBytes(expectedId);
    const sig = hexToBytes(event.sig);
    const pubkeyXOnly = hexToBytes(event.pubkey);
    signatureValid = await schnorr.verify(sig, msg32, pubkeyXOnly);
  } catch {
    signatureValid = false;
  }
  return { ok: idMatches && signatureValid, idMatches, signatureValid, expectedId };
}

export function hexToNpub(pubkeyHex: string): string {
  const bytes = hexToBytes(pubkeyHex);
  if (bytes.length !== 32) throw new Error('x-only pubkey must be 32 bytes');
  const words = bech32.toWords(bytes);
  return bech32.encode('npub', words);
}

export function npubToHex(npub: string): string {
  const dec = bech32.decode(npub);
  if (dec.prefix !== 'npub') throw new Error('invalid npub');
  const bytes = new Uint8Array(bech32.fromWords(dec.words));
  if (bytes.length !== 32) throw new Error('npub decoded length != 32 bytes');
  return bytesToHex(bytes);
}
