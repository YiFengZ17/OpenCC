#!/usr/bin/env python3
"""Measure what the upstream really charges, as a multiplier U on our standard cost.

U = (upstream balance drop) / (our standard cost for the same requests)

Upstream key and URL are read from the environment only, never from the command line:
  OPENCC_UPSTREAM_BASE   e.g. https://api.supergpt.dev
  OPENCC_UPSTREAM_KEY    the upstream API key (use a dedicated key while measuring)

measure    Send a few small test requests straight to the upstream and compare the
           balance drop with the standard cost of each request. Costs real credit.
reconcile  Run periodically (cron). Compares the upstream balance drop since the last
           run with the standard and account cost recorded in our usage_logs.

Both need the upstream to expose Sub2API's GET /v1/usage (returns "balance").
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_PSQL = ("docker compose --env-file .env.opencc -f compose.opencc.yml "
                "exec -T postgres psql -U opencc -d opencc")
FILLER = "OpenCC cost measurement filler text. " * 400  # roughly 3.2k input tokens


def upstream():
    base = os.environ.get("OPENCC_UPSTREAM_BASE", "").rstrip("/")
    key = os.environ.get("OPENCC_UPSTREAM_KEY", "")
    if not base or not key:
        sys.exit("Set OPENCC_UPSTREAM_BASE and OPENCC_UPSTREAM_KEY in the environment.")
    return base, key


def http_json(method, url, key=None, body=None, timeout=120, with_headers=False):
    req = urllib.request.Request(url, method=method,
                                 data=None if body is None else json.dumps(body).encode())
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", "Bearer " + key)
        req.add_header("x-api-key", key)
        req.add_header("anthropic-version", "2023-06-01")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            return (data, dict(r.headers)) if with_headers else data
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url} -> HTTP {e.code}: {e.read()[:300]!r}")


def usage_snapshot():
    """Balance plus the upstream's own cumulative records for this key, when present."""
    base, key = upstream()
    data = http_json("GET", base + "/v1/usage", key)
    value = data.get("balance", data.get("remaining"))
    if not isinstance(value, (int, float)):
        sys.exit(f"Upstream /v1/usage has no numeric balance: {str(data)[:300]}")
    total = (data.get("usage") or {}).get("total") or {}
    return {"balance": float(value), "cost": total.get("cost"), "actual_cost": total.get("actual_cost")}


def balance():
    return usage_snapshot()["balance"]


# Response headers worth showing: anything that might carry billing information.
BORING_HEADERS = {"date", "content-type", "content-length", "connection", "server", "vary",
                  "set-cookie", "cache-control", "transfer-encoding", "strict-transport-security",
                  "alt-svc", "cf-cache-status", "nel", "report-to", "x-content-type-options"}


def wait_for_drop(before, timeout=45):
    deadline = time.time() + timeout
    after = balance()
    while after >= before and time.time() < deadline:
        time.sleep(3)
        after = balance()
    time.sleep(3)  # let any trailing settlement land
    return balance()


def load_prices(source):
    if source.startswith("http://") or source.startswith("https://"):
        data = http_json("GET", source)
    else:
        with open(source) as f:
            data = json.load(f)
    groups = data.get("data", data).get("groups", [])
    prices = {}
    for g in groups:
        for m in g.get("models", []):
            p = m.get("pricing") or {}
            if p.get("billing_mode", "token") == "token" and m["name"] not in prices:
                prices[m["name"]] = p
    return prices


def standard_cost(price, usage):
    def per_token(field):
        return price.get(field) or 0.0
    return (usage.get("input_tokens", 0) * per_token("input_price")
            + usage.get("output_tokens", 0) * per_token("output_price")
            + usage.get("cache_read_input_tokens", 0) * per_token("cache_read_price")
            + usage.get("cache_creation_input_tokens", 0) * per_token("cache_write_price"))


def cmd_measure(args):
    base, key = upstream()
    prices = load_prices(args.prices)
    shapes = {"short": "Reply with the single word OK.", "long": FILLER + "\nReply with the single word OK."}
    rows = []
    start = usage_snapshot()
    shown_headers = False
    for model in args.model:
        if model not in prices:
            sys.exit(f"No token price for {model} in {args.prices}")
        for shape, text in shapes.items():
            for _ in range(args.repeat):
                before = balance()
                resp, headers = http_json("POST", base + "/v1/messages", key, {
                    "model": model, "max_tokens": 16,
                    "messages": [{"role": "user", "content": text}]}, with_headers=True)
                if not shown_headers:
                    shown_headers = True
                    extra = {k: v for k, v in headers.items() if k.lower() not in BORING_HEADERS}
                    print("Upstream response headers (look for cost/credit fields):")
                    for k, v in sorted(extra.items()):
                        print(f"    {k}: {v}")
                after = wait_for_drop(before)
                usage = resp.get("usage", {})
                std = standard_cost(prices[model], usage)
                spent = before - after
                u = spent / std if std > 0 else float("nan")
                rows.append((model, shape, usage.get("input_tokens", 0), usage.get("output_tokens", 0), std, spent, u))
                print(f"{model:<24} {shape:<5} in={usage.get('input_tokens', 0):>6} out={usage.get('output_tokens', 0):>4} "
                      f"standard=¥{std:.6f} upstream=¥{spent:.6f} U={u:.3f}")
    time.sleep(5)
    end = usage_snapshot()
    ours = sum(r[4] for r in rows)
    print(f"\nWhole run: our standard cost ¥{ours:.6f}, balance drop ¥{start['balance'] - end['balance']:.6f}")
    if isinstance(start["cost"], (int, float)) and isinstance(end["cost"], (int, float)):
        print(f"  upstream's own records: standard ¥{end['cost'] - start['cost']:.6f}, "
              f"charged ¥{(end['actual_cost'] or 0) - (start['actual_cost'] or 0):.6f}")
        print("  standard differs from ours -> fix channel base prices; charged differs from balance drop"
              " -> extra credit fees not shown in the upstream's usage records.")
    else:
        print("  upstream /v1/usage has no usage records; only the balance is used.")
    print("\nPer model: upstream charge ≈ a × standard cost + b per request")
    for model in args.model:
        mine = [r for r in rows if r[0] == model]
        short = [r for r in mine if r[1] == "short"]
        long_ = [r for r in mine if r[1] == "long"]
        avg = lambda rs, i: sum(r[i] for r in rs) / len(rs)
        a = (avg(long_, 5) - avg(short, 5)) / (avg(long_, 4) - avg(short, 4))
        b = max(0.0, avg(short, 5) - a * avg(short, 4))
        print(f"  {model:<24} a={a:.3f}  b=¥{b:.5f}/request")
        for std in (0.002, 0.01, 0.05):
            u = a + b / std
            print(f"      request with standard cost ¥{std}: real U={u:.3f}; "
                  f"D for 25% margin = {u / 0.75:.3f}")
    print("\nb > 0 means a fixed fee per request: small requests cost relatively more."
          " Use 'reconcile' on real traffic to see the U that matters for your team.")


def psql(sql, command):
    out = subprocess.run(shlex.split(command) + ["-At", "-F", "|", "-v", "ON_ERROR_STOP=1"],
                         input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed: " + out.stderr.strip())
    return out.stdout.strip()


def cmd_reconcile(args):
    now = datetime.now(timezone.utc)
    current = {"at": now.isoformat(), "balance": balance()}
    previous = None
    if os.path.exists(args.state):
        with open(args.state) as f:
            lines = [line for line in f if line.strip()]
        if lines:
            previous = json.loads(lines[-1])
    with open(args.state, "a") as f:
        f.write(json.dumps(current) + "\n")
    if previous is None:
        print(f"{current['at']} first snapshot, upstream balance ¥{current['balance']:.4f}")
        return
    sql = (
        "SELECT count(*), COALESCE(sum(total_cost),0), COALESCE(sum(actual_cost),0), "
        "COALESCE(sum(COALESCE(account_stats_cost,total_cost)*COALESCE(account_rate_multiplier,1)),0) "
        f"FROM usage_logs WHERE account_id = {int(args.account_id)} "
        f"AND created_at > '{previous['at']}'::timestamptz AND created_at <= '{current['at']}'::timestamptz;"
    )
    count, std, charged, recorded = psql(sql, args.psql).split("|")
    count, std, charged, recorded = int(count), float(std), float(charged), float(recorded)
    spent = previous["balance"] - current["balance"]
    head = f"{previous['at']} -> {current['at']}  requests={count}"
    if spent < -1e-9:
        print(f"{head}  upstream balance rose by ¥{-spent:.4f} (top-up?); window skipped")
        return
    if std <= 0:
        print(f"{head}  no billable usage; upstream spent ¥{spent:.4f}")
        return
    print(f"{head}\n  standard ¥{std:.4f}  charged to members ¥{charged:.4f}"
          f"\n  upstream spent ¥{spent:.4f} (real U={spent / std:.3f})"
          f"  recorded cost ¥{recorded:.4f} (configured U≈{recorded / std:.3f})"
          f"\n  real gross profit ¥{charged - spent:.4f}  ({(charged - spent) / charged:.1%} of revenue)"
          if charged > 0 else f"{head}  upstream spent ¥{spent:.4f}, nothing charged")
    if charged > 0 and abs(spent - recorded) > args.tolerance * max(spent, 1e-9):
        print(f"  WARNING: recorded cost differs from real upstream spend by more than {args.tolerance:.0%}; "
              f"set the account multiplier to {spent / std:.4f}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure", help="send test requests and derive U per model")
    m.add_argument("--model", action="append", required=True, help="repeatable")
    m.add_argument("--repeat", type=int, default=2, help="requests per model and size (default 2)")
    m.add_argument("--prices", default="https://opencc.app/api/v1/model-plaza",
                   help="model-plaza URL or JSON file with base prices (default: this site)")
    m.set_defaults(func=cmd_measure)
    r = sub.add_parser("reconcile", help="compare upstream balance drop with recorded usage")
    r.add_argument("--account-id", type=int, required=True, help="upstream account id in OpenCC")
    r.add_argument("--state", default="backups/cost-check.jsonl")
    r.add_argument("--psql", default=os.environ.get("OPENCC_PSQL", DEFAULT_PSQL))
    r.add_argument("--tolerance", type=float, default=0.05)
    r.set_defaults(func=cmd_reconcile)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
