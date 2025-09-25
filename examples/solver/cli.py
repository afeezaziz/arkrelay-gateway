#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

import requests

BASE = os.getenv("SOLVER_BASE_URL", "http://localhost:9000").rstrip("/")


def _req(method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = f"{BASE}{path}"
    resp = requests.request(method, url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
    if not (200 <= resp.status_code < 300):
        print(f"[HTTP {resp.status_code}] {resp.text}", file=sys.stderr)
        sys.exit(1)
    if resp.content:
        return resp.json()
    return {}


def cmd_gen_intent(_: argparse.Namespace) -> None:
    out = _req("GET", "/simulate/generate-intent")
    print(json.dumps(out, indent=2))


def cmd_accept_intent(args: argparse.Namespace) -> None:
    if args.intent_file:
        with open(args.intent_file, "r", encoding="utf-8") as f:
            intent_payload = json.load(f)
    else:
        # Fallback: generate intent then accept
        gen = _req("GET", "/simulate/generate-intent")
        intent = gen["intent"]
        intent_payload = {
            "user_pubkey": gen["user_pubkey"],
            **intent,
        }
    out = _req("POST", "/simulate/intent", intent_payload)
    print(json.dumps(out, indent=2))


def cmd_ceremony_start(args: argparse.Namespace) -> None:
    out = _req("POST", "/simulate/ceremony/start", {"session_id": args.session_id})
    print(json.dumps(out, indent=2))


def cmd_ceremony_status(args: argparse.Namespace) -> None:
    out = _req("GET", f"/simulate/ceremony/{args.session_id}/status")
    print(json.dumps(out, indent=2))


def cmd_sign_ecdsa(args: argparse.Namespace) -> None:
    payload: Dict[str, Any] = {}
    if args.generate:
        payload["generate"] = args.generate
    if args.data:
        payload["data"] = json.loads(args.data)
    out = _req("POST", "/simulate/sign", payload)
    print(json.dumps(out, indent=2))


def cmd_verify(args: argparse.Namespace) -> None:
    payload: Dict[str, Any] = {"algorithm": args.algorithm, "signature": args.signature}
    if args.digest:
        payload["digest"] = args.digest
    elif args.data:
        payload["data"] = json.loads(args.data)
    elif args.message:
        payload["message"] = args.message
    out = _req("POST", "/simulate/verify", payload)
    print(json.dumps(out, indent=2))


def cmd_nostr_sign(args: argparse.Namespace) -> None:
    payload: Dict[str, Any] = {}
    if args.digest:
        payload["digest"] = args.digest
    elif args.data:
        payload["data"] = json.loads(args.data)
    elif args.message:
        payload["message"] = args.message
    else:
        print("Provide one of --digest | --data | --message", file=sys.stderr)
        sys.exit(2)
    out = _req("POST", "/simulate/nostr/sign", payload)
    print(json.dumps(out, indent=2))


def cmd_nostr_sign_event(args: argparse.Namespace) -> None:
    tags = json.loads(args.tags) if args.tags else []
    payload = {
        "kind": args.kind,
        "content": args.content or "",
        "tags": tags,
    }
    if args.created_at:
        payload["created_at"] = int(args.created_at)
    out = _req("POST", "/simulate/nostr/sign-event", payload)
    print(json.dumps(out, indent=2))


def cmd_nostr_verify_event(args: argparse.Namespace) -> None:
    if args.event_file:
        with open(args.event_file, "r", encoding="utf-8") as f:
            event = json.load(f)
    elif args.event:
        event = json.loads(args.event)
    else:
        print("Provide --event-file or --event (JSON)", file=sys.stderr)
        sys.exit(2)
    out = _req("POST", "/simulate/nostr/verify-event", event)
    print(json.dumps(out, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="ArkRelay solver example CLI")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("gen-intent", help="Generate a simulated intent (time-based)")
    s.set_defaults(func=cmd_gen_intent)

    s = sub.add_parser("accept-intent", help="Accept an intent and create a signing challenge at the gateway")
    s.add_argument("--intent-file", help="Path to JSON containing user_pubkey, action_id, type, params, expires_at")
    s.set_defaults(func=cmd_accept_intent)

    s = sub.add_parser("ceremony-start", help="Start signing ceremony")
    s.add_argument("--session-id", required=True)
    s.set_defaults(func=cmd_ceremony_start)

    s = sub.add_parser("ceremony-status", help="Get ceremony status")
    s.add_argument("--session-id", required=True)
    s.set_defaults(func=cmd_ceremony_status)

    s = sub.add_parser("sign-ecdsa", help="Sign using demo ECDSA key (transfer|note generator or raw data)")
    s.add_argument("--generate", choices=["transfer", "note"], help="Generate a sample payload to sign")
    s.add_argument("--data", help="Raw JSON object to sign")
    s.set_defaults(func=cmd_sign_ecdsa)

    s = sub.add_parser("verify", help="Verify signature with ECDSA or Nostr")
    s.add_argument("--algorithm", choices=["ecdsa", "nostr"], default="ecdsa")
    s.add_argument("--digest", help="Hex digest (32 bytes)")
    s.add_argument("--data", help="Raw JSON object to hash and verify")
    s.add_argument("--message", help="Plaintext message to hash and verify")
    s.add_argument("--signature", required=True, help="Signature hex")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("nostr-sign", help="Sign message/data/digest via BIP340 Schnorr")
    s.add_argument("--digest", help="Hex digest (32 bytes)")
    s.add_argument("--data", help="Raw JSON object to hash and sign")
    s.add_argument("--message", help="Plaintext message to hash and sign")
    s.set_defaults(func=cmd_nostr_sign)

    s = sub.add_parser("nostr-sign-event", help="Sign a Nostr event (NIP-01)")
    s.add_argument("--kind", type=int, default=1)
    s.add_argument("--content", help="Event content")
    s.add_argument("--tags", help="JSON list of tags, e.g. [[\"p\",\"<pubkey>\"]]")
    s.add_argument("--created-at", dest="created_at", help="Unix seconds override")
    s.set_defaults(func=cmd_nostr_sign_event)

    s = sub.add_parser("nostr-verify-event", help="Verify a Nostr event (NIP-01)")
    s.add_argument("--event-file", help="Path to JSON event file")
    s.add_argument("--event", help="Inline JSON event string")
    s.set_defaults(func=cmd_nostr_verify_event)

    args = p.parse_args()
    if not getattr(args, "cmd", None):
        p.print_help()
        sys.exit(2)
    args.func(args)


if __name__ == "__main__":
    main()
