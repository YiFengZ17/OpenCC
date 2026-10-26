#!/usr/bin/env python3
"""Simulated Sub2API-compatible upstream for the OpenCC billing self-test.

Not SuperGPT. It answers Anthropic /v1/messages (plain and streaming) with
deterministic usage, charges its own balance like a reseller would
(multiplier x standard cost + fixed fee per request), and exposes the
endpoints OpenCC and opencc-cost-check.py read:

  GET /v1/usage            balance and cumulative usage records for the key
  GET /v1/sub2api/billing  rate multiplier declaration (upstream billing probe)
  GET /__requests          test hook: every request received, for assertions
"""
import argparse
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=18080)
p.add_argument("--multiplier", type=float, default=0.8, help="upstream charge per unit of standard cost")
p.add_argument("--fixed-fee", type=float, default=0.002, help="extra charge per request, not shown in usage records")
p.add_argument("--input-price", type=float, default=3e-6, help="base price per input token")
p.add_argument("--output-price", type=float, default=1.5e-5, help="base price per output token")
p.add_argument("--balance", type=float, default=100.0)
args = p.parse_args()

lock = threading.Lock()
state = {"balance": args.balance, "cost": 0.0, "actual_cost": 0.0, "requests": []}


def usage_for(req):
    text = json.dumps(req.get("messages", []), ensure_ascii=False)
    return {
        "input_tokens": max(10, len(text) // 4),
        "output_tokens": min(int(req.get("max_tokens") or 200), 200),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def charge(usage):
    standard = usage["input_tokens"] * args.input_price + usage["output_tokens"] * args.output_price
    with lock:
        state["balance"] -= args.multiplier * standard + args.fixed_fee
        state["cost"] += standard
        state["actual_cost"] += args.multiplier * standard


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("x-request-id", "req_mock")
        self.end_headers()
        self.wfile.write(body)

    def _record(self, **extra):
        key = self.headers.get("x-api-key") or (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        with lock:
            state["requests"].append({"method": self.command, "path": self.path, "key": key, **extra})

    def do_GET(self):
        if self.path.startswith("/__requests"):
            with lock:
                return self._json(200, state["requests"])
        self._record()
        if self.path.startswith("/v1/usage"):
            with lock:
                return self._json(200, {
                    "mode": "unrestricted", "isValid": True, "unit": "USD",
                    "balance": round(state["balance"], 10),
                    "usage": {"total": {"cost": state["cost"], "actual_cost": state["actual_cost"]}},
                })
        if self.path.startswith("/v1/sub2api/billing"):
            return self._json(200, {
                "object": "sub2api.key_billing", "schema_version": 1, "billing_scope": "token",
                "group_rate_multiplier": args.multiplier, "resolved_rate_multiplier": args.multiplier,
                "peak_rate_enabled": False, "effective_rate_multiplier": args.multiplier,
                "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            })
        if self.path.startswith("/v1/models"):
            return self._json(200, {"data": [{"id": "claude-sonnet-4-6", "type": "model"}]})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length) or b"{}")
        if not self.path.startswith("/v1/messages"):
            self._record()
            return self._json(404, {"error": "not found"})
        model = req.get("model", "claude-sonnet-4-6")
        usage = usage_for(req)
        charge(usage)
        self._record(model=model, stream=bool(req.get("stream")), usage=usage)
        if not req.get("stream"):
            return self._json(200, {
                "id": "msg_mock", "type": "message", "role": "assistant", "model": model,
                "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": usage,
            })
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "msg_mock", "type": "message", "role": "assistant", "model": model,
                "content": [], "stop_reason": None, "usage": {**usage, "output_tokens": 1}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                               "usage": {"output_tokens": usage["output_tokens"]}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        for name, data in events:
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()

    def log_message(self, *a):
        pass


print(f"mock upstream on http://{args.host}:{args.port} (multiplier {args.multiplier}, fixed fee {args.fixed_fee})", flush=True)
ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
