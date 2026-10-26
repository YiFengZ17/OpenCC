#!/usr/bin/env python3
"""OpenCC billing self-test against a running OpenCC server and mock_upstream.py.

Creates a uniquely named group, upstream account, channel, member and API key,
sends requests through the gateway, then checks:

  1. the upstream only ever saw the server-side upstream key
  2. recorded tokens match what the upstream returned
  3. standard cost  = tokens x channel base prices
  4. member charge  = standard cost x group multiplier D
  5. account cost   = standard cost x account multiplier U
  6. member balance dropped by exactly the member charge
  7. admin dashboard gross profit grew by charge - account cost
  8. the upstream billing probe reads the mock's declared multiplier
  9. opencc-cost-check.py reconcile reports the mock's real spend (needs --psql)

Exit code 0 only when every check passes. Run it only against a test instance:
it creates users, groups and accounts.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
COST_CHECK = os.path.join(HERE, "..", "..", "deploy", "opencc-cost-check.py")
COMPLIANCE_PHRASE = "我已阅读、理解并同意 Sub2API 部署与运营合规承诺"
REL_TOL = 1e-6

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def close(a, b):
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b), 1e-9) + 1e-12


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None, token=None, key=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=None if body is None else json.dumps(body).encode())
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if key:
            req.add_header("x-api-key", key)
            req.add_header("anthropic-version", "2023-06-01")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw, code = r.read().decode(), r.status
        except urllib.error.HTTPError as e:
            raw, code = e.read().decode(), e.code
        try:
            return code, json.loads(raw)
        except ValueError:
            return code, raw

    def data(self, method, path, body=None, token=None):
        code, obj = self.call(method, path, body, token=token)
        if code >= 300 or not isinstance(obj, dict) or obj.get("code") not in (0, None):
            sys.exit(f"{method} {path} failed: HTTP {code} {str(obj)[:400]}")
        return obj.get("data", obj)


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def dashboard(api, admin):
    stats = api.data("GET", "/api/v1/admin/dashboard/snapshot-v2?include_trend=false&include_model_stats=false"
                     "&include_group_stats=false&include_users_trend=false", token=admin)["stats"]
    return stats.get("today_actual_cost") or 0.0, stats.get("today_account_cost") or 0.0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://127.0.0.1:8088", help="OpenCC server")
    p.add_argument("--mock", default="http://127.0.0.1:18080", help="mock upstream, as reachable from the server")
    p.add_argument("--admin-email", default=os.environ.get("OPENCC_ADMIN_EMAIL"))
    p.add_argument("--admin-password", default=os.environ.get("OPENCC_ADMIN_PASSWORD"))
    p.add_argument("--sell", type=float, default=1.2, help="group multiplier D")
    p.add_argument("--cost", type=float, default=0.8, help="account multiplier U")
    p.add_argument("--input-price", type=float, default=3e-6, help="must match mock_upstream.py")
    p.add_argument("--output-price", type=float, default=1.5e-5, help="must match mock_upstream.py")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--requests", type=int, default=3, help="plain requests; one streaming request is added")
    p.add_argument("--psql", default=os.environ.get("OPENCC_PSQL"), help="psql command for the reconcile check")
    p.add_argument("--accept-compliance", action="store_true",
                   help="accept the Sub2API admin compliance commitment for this test admin")
    p.add_argument("--allow-remote", action="store_true", help="allow a non-localhost --base")
    a = p.parse_args()

    host = urllib.parse.urlparse(a.base).hostname
    if host not in ("127.0.0.1", "localhost", "::1") and not a.allow_remote:
        sys.exit(f"Refusing to run against {a.base}: this test creates users and accounts. "
                 "Use a test instance, or pass --allow-remote if you are sure.")
    if not a.admin_email or not a.admin_password:
        sys.exit("Set OPENCC_ADMIN_EMAIL and OPENCC_ADMIN_PASSWORD (or --admin-email/--admin-password).")

    api = Client(a.base)
    tag = uuid.uuid4().hex[:6]
    admin = api.data("POST", "/api/v1/auth/login", {"email": a.admin_email, "password": a.admin_password})["access_token"]

    code, _ = api.call("GET", "/api/v1/admin/groups?page=1&page_size=1", token=admin)
    if code == 423:
        if not a.accept_compliance:
            sys.exit("The admin console is locked until the operator accepts the Sub2API compliance commitment "
                     "(docs/legal/admin-compliance.zh.md). Accept it in the admin UI, or re-run with "
                     "--accept-compliance on a test instance.")
        api.data("POST", "/api/v1/admin/compliance/accept", {"phrase": COMPLIANCE_PHRASE, "language": "zh"}, token=admin)

    requests_before = len(get_json(a.mock + "/__requests"))

    group = api.data("POST", "/api/v1/admin/groups", {
        "name": f"selftest-{tag}", "platform": "anthropic", "rate_multiplier": a.sell,
        "subscription_type": "standard"}, token=admin)
    upstream_key = f"sk-selftest-upstream-{tag}"
    account = api.data("POST", "/api/v1/admin/accounts", {
        "name": f"selftest-upstream-{tag}", "platform": "anthropic", "type": "apikey",
        "credentials": {"api_key": upstream_key, "base_url": a.mock},
        "concurrency": 5, "rate_multiplier": a.cost, "group_ids": [group["id"]],
        "upstream_billing_probe_enabled": True}, token=admin)
    api.data("POST", "/api/v1/admin/channels", {
        "name": f"selftest-{tag}", "group_ids": [group["id"]], "restrict_models": True,
        "model_pricing": [{"platform": "anthropic", "models": [a.model], "billing_mode": "token",
                           "input_price": a.input_price, "output_price": a.output_price}]}, token=admin)
    email, password = f"selftest-{tag}@opencc.test", f"Selftest-{tag}-pw"
    member = api.data("POST", "/api/v1/admin/users", {"email": email, "password": password, "username": f"selftest-{tag}"}, token=admin)
    api.data("POST", f"/api/v1/admin/users/{member['id']}/balance",
             {"balance": 10, "operation": "add", "notes": "billing self-test"}, token=admin)
    member_token = api.data("POST", "/api/v1/auth/login", {"email": email, "password": password})["access_token"]
    member_key = api.data("POST", "/api/v1/keys", {"name": "selftest", "group_id": group["id"]}, token=member_token)["key"]
    print(f"setup: group {group['id']} (D={a.sell}), account {account['id']} (U={a.cost}), member {member['id']} with ¥10")

    profit_before = dashboard(api, admin)
    balance_before = api.data("GET", "/api/v1/auth/me", token=member_token)["balance"]

    body = {"model": a.model, "max_tokens": 120, "messages": [{"role": "user", "content": "billing self-test"}]}
    for i in range(a.requests + 1):
        code, resp = api.call("POST", "/v1/messages", {**body, "stream": i == a.requests}, key=member_key)
        if code != 200:
            sys.exit(f"gateway request failed: HTTP {code} {str(resp)[:300]}")
    sent = a.requests + 1

    logs = []
    for _ in range(30):
        logs = api.data("GET", f"/api/v1/admin/usage?page=1&page_size=100&account_id={account['id']}", token=admin).get("items", [])
        if len(logs) >= sent:
            break
        time.sleep(1)
    upstream_reqs = [r for r in get_json(a.mock + "/__requests")[requests_before:] if r["path"].startswith("/v1/messages")]

    check("upstream saw only the server-side key",
          len(upstream_reqs) == sent and all(r["key"] == upstream_key for r in upstream_reqs),
          f"{len(upstream_reqs)} requests, member key forwarded: {any(r['key'] == member_key for r in upstream_reqs)}")
    check("usage logs written", len(logs) == sent, f"{len(logs)}/{sent}")

    tokens_up = sorted((r["usage"]["input_tokens"], r["usage"]["output_tokens"]) for r in upstream_reqs)
    tokens_ours = sorted((l["input_tokens"], l["output_tokens"]) for l in logs)
    check("recorded tokens match upstream usage", tokens_up == tokens_ours, f"upstream {tokens_up} / ours {tokens_ours}")

    std_ok = charge_ok = cost_ok = True
    total_std = total_charge = total_cost = 0.0
    for l in logs:
        std = l["input_tokens"] * a.input_price + l["output_tokens"] * a.output_price
        account_cost = (l.get("account_stats_cost") if l.get("account_stats_cost") is not None else l["total_cost"]) \
            * (l.get("account_rate_multiplier") or 1.0)
        std_ok &= close(l["total_cost"], std)
        charge_ok &= close(l["actual_cost"], l["total_cost"] * a.sell)
        cost_ok &= close(account_cost, l["total_cost"] * a.cost)
        total_std += l["total_cost"]
        total_charge += l["actual_cost"]
        total_cost += account_cost
    check("standard cost = tokens × base price", std_ok, f"¥{total_std:.6f}")
    check("member charge = standard × D", charge_ok, f"¥{total_charge:.6f}")
    check("account cost = standard × U", cost_ok, f"¥{total_cost:.6f}")

    balance_after = api.data("GET", "/api/v1/auth/me", token=member_token)["balance"]
    check("member balance dropped by the charge", close(balance_before - balance_after, total_charge),
          f"¥{balance_before} → ¥{balance_after}")

    expected_profit = total_charge - total_cost
    profit_delta = None
    for _ in range(24):  # dashboard aggregation runs about once a minute
        actual, cost = dashboard(api, admin)
        if actual - profit_before[0] >= total_charge * (1 - 1e-6):
            profit_delta = (actual - cost) - (profit_before[0] - profit_before[1])
            break
        time.sleep(5)
    check("dashboard gross profit grew by charge − cost",
          profit_delta is not None and abs(profit_delta - expected_profit) < 1e-6,
          f"expected ¥{expected_profit:.6f}, dashboard ¥{profit_delta if profit_delta is None else round(profit_delta, 6)}")

    probe = api.data("POST", f"/api/v1/admin/accounts/{account['id']}/upstream-billing-probe", {}, token=admin)
    declared = ((probe.get("snapshot") or {}).get("data") or {}).get("resolved_rate_multiplier")
    mock_multiplier = None
    try:
        mock_multiplier = get_json(a.mock + "/v1/sub2api/billing")["resolved_rate_multiplier"]
    except (urllib.error.URLError, KeyError):
        pass
    check("upstream billing probe reads the declared multiplier",
          declared is not None and close(declared, mock_multiplier or -1), f"probe {declared}, mock {mock_multiplier}")

    if not a.psql:
        print("[SKIP] reconcile check — pass --psql (or OPENCC_PSQL) to run it")
    else:
        state = os.path.join("/tmp", f"opencc-selftest-{tag}.jsonl")
        env = {**os.environ, "OPENCC_UPSTREAM_BASE": a.mock, "OPENCC_UPSTREAM_KEY": upstream_key}
        run = lambda: subprocess.run([sys.executable, COST_CHECK, "reconcile", "--account-id", str(account["id"]),
                                      "--state", state, "--psql", a.psql], env=env, capture_output=True, text=True)
        first = run()
        api.call("POST", "/v1/messages", body, key=member_key)
        time.sleep(3)
        second = run()
        os.remove(state)
        out = first.stdout + second.stdout + first.stderr + second.stderr
        check("reconcile compares upstream spend with recorded usage",
              second.returncode == 0 and "real U=" in second.stdout, out.strip().replace("\n", " | ")[:400])

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
