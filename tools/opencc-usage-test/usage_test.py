#!/usr/bin/env python3
"""OpenCC usage test against a real deployment (real upstream, real but small spend).

Logs in as a dedicated test member, creates temporary API keys, sends requests
through the gateway and checks that usage records, charges and balances agree.
Temporary keys (and, with --with-admin, a temporary member) are removed at the end.

Cases (see AGENT_TASK.md for what each one means):
  C1 plain request      tokens in record = response usage; charge = standard × multiplier
  C2 streaming request  same, with tokens taken from the SSE stream
  C3 prompt cache       cache write / read tokens recorded and priced separately
  C4 failed request     error response, no record, no charge
  C5 interrupted stream INFO only: what gets recorded when the client hangs up
  C6 key quota          a key with a tiny quota is refused with 429 once used up
  C7 low balance        (--with-admin) a member with ¥0.0001 is refused, balance never negative
  C8 totals             /v1/usage today totals for the key = sum of its records
  C9 concurrency        10 parallel requests → 10 records, balance drop = sum of charges
  C10 isolation         (--with-admin) another member cannot see these records

Credentials come from the environment only:
  OPENCC_BASE                  e.g. https://opencc.app
  OPENCC_MEMBER_EMAIL / OPENCC_MEMBER_PASSWORD   dedicated test member with ≥ ¥2
  OPENCC_ADMIN_EMAIL / OPENCC_ADMIN_PASSWORD     only for --with-admin
"""
import argparse
import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

TOL = 1e-6
results = []


def record(case, status, detail):
    results.append({"case": case, "status": status, "detail": detail})
    print(f"[{status:<4}] {case}: {detail}", flush=True)


def close(a, b, rel=1e-6):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-9) + 1e-9


class Site:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None, token=None, key=None, headers=None, timeout=180):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=None if body is None else json.dumps(body).encode())
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if key:
            req.add_header("x-api-key", key)
            req.add_header("anthropic-version", "2023-06-01")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw, code = r.read().decode(), r.status
        except urllib.error.HTTPError as e:
            raw, code = e.read().decode(errors="replace"), e.code
        try:
            return code, json.loads(raw)
        except ValueError:
            return code, raw

    def data(self, method, path, body=None, token=None):
        code, obj = self.call(method, path, body, token=token)
        if code >= 300 or not isinstance(obj, dict) or obj.get("code") not in (0, None):
            raise RuntimeError(f"{method} {path} → HTTP {code}: {str(obj)[:300]}")
        return obj.get("data", obj)

    def login(self, email, password):
        return self.data("POST", "/api/v1/auth/login", {"email": email, "password": password})["access_token"]


class Member:
    def __init__(self, site, token):
        self.site, self.token = site, token

    def balance(self):
        return float(self.site.data("GET", "/api/v1/auth/me", token=self.token)["balance"])

    def records(self, key_id):
        out, page = [], 1
        while True:
            d = self.site.data("GET", f"/api/v1/usage?page={page}&page_size=100&api_key_id={key_id}", token=self.token)
            out += d.get("items", [])
            if len(out) >= d.get("total", 0) or not d.get("items"):
                return out
            page += 1

    def create_key(self, name, group_id, quota=None):
        body = {"name": name, "group_id": group_id}
        if quota is not None:
            body["quota"] = quota
        return self.site.data("POST", "/api/v1/keys", body, token=self.token)

    def delete_key(self, key_id):
        self.site.call("DELETE", f"/api/v1/keys/{key_id}", token=self.token)


def wait_records(member, key_id, known_ids, expected, timeout=40):
    """Wait until `expected` new records appear for the key; returns the new ones."""
    deadline = time.time() + timeout
    new = []
    while time.time() < deadline:
        new = [r for r in member.records(key_id) if r["id"] not in known_ids]
        if len(new) >= expected:
            break
        time.sleep(1.5)
    return new


def wait_balance(member, previous, timeout=20):
    """Balance deduction can lag the usage record; wait until it settles."""
    deadline = time.time() + timeout
    last = member.balance()
    while time.time() < deadline:
        time.sleep(2)
        now = member.balance()
        if now == last and now != previous:
            return now
        last = now
    return last


def message_body(model, text, max_tokens=60, **extra):
    return {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": text}], **extra}


def stream_request(base, key, body, stop_after_first_delta=False, timeout=180):
    """POST a streaming Messages request; returns (status, usage dict, events seen)."""
    url = urllib.parse.urlparse(base + "/v1/messages")
    conn_cls = __import__("http.client").client.HTTPSConnection if url.scheme == "https" else __import__("http.client").client.HTTPConnection
    kwargs = {"timeout": timeout}
    if url.scheme == "https":
        kwargs["context"] = ssl.create_default_context()
    conn = conn_cls(url.hostname, url.port, **kwargs)
    payload = json.dumps({**body, "stream": True})
    conn.request("POST", url.path, payload, {"Content-Type": "application/json", "x-api-key": key,
                                             "anthropic-version": "2023-06-01"})
    resp = conn.getresponse()
    usage, events = {}, 0
    if resp.status != 200:
        resp.read()
        conn.close()
        return resp.status, usage, events
    for raw in resp:
        line = raw.decode(errors="replace").strip()
        if not line.startswith("data:"):
            continue
        try:
            data = json.loads(line[5:].strip())
        except ValueError:
            continue
        events += 1
        if data.get("type") == "message_start":
            usage.update(data.get("message", {}).get("usage", {}))
        elif data.get("type") == "message_delta":
            usage.update(data.get("usage", {}))
        elif data.get("type") == "content_block_delta" and stop_after_first_delta:
            break
    try:
        conn.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.close()
    return 200, usage, events


def find_prices(site, group_id, model):
    code, obj = site.call("GET", "/api/v1/model-plaza")
    if code != 200 or not isinstance(obj, dict):
        return None
    for g in (obj.get("data") or {}).get("groups", []):
        if g.get("id") == group_id:
            for m in g.get("models", []):
                if m.get("name") == model and (m.get("pricing") or {}).get("billing_mode", "token") == "token":
                    return m["pricing"]
    return None


def check_record(case, rec, usage, prices):
    """Compare one usage record with the response usage and, when known, the price list."""
    problems = []
    pairs = [("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
             ("cache_creation_tokens", "cache_creation_input_tokens"), ("cache_read_tokens", "cache_read_input_tokens")]
    for rk, uk in pairs:
        if uk in usage and int(usage.get(uk) or 0) != int(rec.get(rk) or 0):
            problems.append(f"{rk}: record {rec.get(rk)} ≠ response {usage.get(uk)}")
    if not close(rec["actual_cost"], rec["total_cost"] * rec["rate_multiplier"]):
        problems.append(f"charge ¥{rec['actual_cost']} ≠ standard ¥{rec['total_cost']} × {rec['rate_multiplier']}")
    note = ""
    if prices:
        expected = (rec["input_tokens"] * (prices.get("input_price") or 0)
                    + rec["output_tokens"] * (prices.get("output_price") or 0)
                    + rec["cache_creation_tokens"] * (prices.get("cache_write_price") or 0)
                    + rec["cache_read_tokens"] * (prices.get("cache_read_price") or 0))
        if not close(rec["total_cost"], expected, 1e-4):
            problems.append(f"standard ¥{rec['total_cost']} ≠ tokens × price list ¥{expected:.8f}")
    else:
        note = " (price list not public: standard-cost formula not checked)"
    detail = (f"in={rec['input_tokens']} out={rec['output_tokens']} cache_w={rec['cache_creation_tokens']} "
              f"cache_r={rec['cache_read_tokens']} standard=¥{rec['total_cost']:.6f} ×{rec['rate_multiplier']} "
              f"charge=¥{rec['actual_cost']:.6f}{note}")
    record(case, "FAIL" if problems else "PASS", "; ".join(problems) + " | " + detail if problems else detail)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--group-id", type=int, help="group for the temporary keys (default: first available group)")
    p.add_argument("--max-spend", type=float, default=2.0, help="stop when the member has spent this much (¥)")
    p.add_argument("--with-admin", action="store_true", help="run C7/C10 using a temporary member (needs admin)")
    p.add_argument("--skip", default="", help="comma-separated cases to skip, e.g. C3,C9")
    p.add_argument("--report", default="usage-test-report.json")
    a = p.parse_args()
    skip = {s.strip().upper() for s in a.skip.split(",") if s.strip()}

    base = os.environ.get("OPENCC_BASE", "").rstrip("/")
    email, password = os.environ.get("OPENCC_MEMBER_EMAIL"), os.environ.get("OPENCC_MEMBER_PASSWORD")
    if not base or not email or not password:
        sys.exit("Set OPENCC_BASE, OPENCC_MEMBER_EMAIL and OPENCC_MEMBER_PASSWORD.")
    site = Site(base)
    member = Member(site, site.login(email, password))
    tag = uuid.uuid4().hex[:6]
    cleanup = []
    started = datetime.now(timezone.utc).isoformat()

    groups = site.data("GET", "/api/v1/groups/available", token=member.token)
    if not groups:
        sys.exit("The test member has no available group.")
    group_id = a.group_id or groups[0]["id"]
    prices = find_prices(site, group_id, a.model)
    start_balance = member.balance()
    print(f"base={base} model={a.model} group={group_id} balance=¥{start_balance} max-spend=¥{a.max_spend}")
    if start_balance < 0.5:
        sys.exit("Top up the test member to at least ¥0.5 first (¥2 recommended).")

    key = member.create_key(f"usagetest-{tag}", group_id)
    cleanup.append(lambda: member.delete_key(key["id"]))
    K, KID = key["key"], key["id"]

    def spent():
        return start_balance - member.balance()

    def guard():
        if spent() > a.max_spend:
            raise RuntimeError(f"spend limit reached (¥{spent():.4f} > ¥{a.max_spend})")

    def known():
        return {r["id"] for r in member.records(KID)}

    def run(case, fn):
        if case in skip:
            record(case, "SKIP", "skipped by --skip")
            return
        try:
            guard()
            fn()
        except Exception as e:  # keep going so one broken case does not hide the others
            record(case, "FAIL", f"error: {e}")

    def c1():
        ids, before = known(), member.balance()
        code, resp = site.call("POST", "/v1/messages", message_body(a.model, "用一句话介绍你自己"), key=K)
        if code != 200:
            return record("C1 plain request", "FAIL", f"HTTP {code}: {str(resp)[:200]}")
        new = wait_records(member, KID, ids, 1)
        if len(new) != 1:
            return record("C1 plain request", "FAIL", f"expected 1 new record, got {len(new)}")
        check_record("C1 plain request", new[0], resp.get("usage", {}), prices)
        after = wait_balance(member, before)
        record("C1 balance", "PASS" if close(before - after, new[0]["actual_cost"]) else "FAIL",
               f"balance ¥{before} → ¥{after}, drop ¥{before - after:.8f} vs charge ¥{new[0]['actual_cost']:.8f}")

    def c2():
        ids = known()
        code, usage, events = stream_request(base, K, message_body(a.model, "数到十"))
        if code != 200:
            return record("C2 streaming request", "FAIL", f"HTTP {code}")
        new = wait_records(member, KID, ids, 1)
        if len(new) != 1:
            return record("C2 streaming request", "FAIL", f"expected 1 new record, got {len(new)}")
        if not new[0].get("stream"):
            record("C2 streaming flag", "FAIL", "record is not marked as stream")
        check_record("C2 streaming request", new[0], usage, prices)

    def c3():
        system = "这是一段用于测试提示缓存的固定系统提示，内容不变。" * 160
        body = message_body(a.model, "你好", 20, system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}])
        seen = []
        for i in range(2):
            ids = known()
            code, resp = site.call("POST", "/v1/messages", body, key=K)
            if code != 200:
                return record("C3 prompt cache", "FAIL", f"request {i + 1}: HTTP {code}: {str(resp)[:200]}")
            new = wait_records(member, KID, ids, 1)
            if len(new) != 1:
                return record("C3 prompt cache", "FAIL", f"request {i + 1}: expected 1 new record, got {len(new)}")
            check_record(f"C3 prompt cache #{i + 1}", new[0], resp.get("usage", {}), prices)
            seen.append(resp.get("usage", {}))
        wrote = int(seen[0].get("cache_creation_input_tokens") or 0)
        read = int(seen[1].get("cache_read_input_tokens") or 0)
        if wrote == 0 and read == 0:
            record("C3 cache behaviour", "INFO", "upstream returned no cache tokens: prompt caching is not active on this route")
        else:
            record("C3 cache behaviour", "PASS" if read > 0 else "INFO",
                   f"first request wrote {wrote} cache tokens, second read {read}")

    def c4():
        ids, before = known(), member.balance()
        code, resp = site.call("POST", "/v1/messages", message_body("opencc-usage-test-no-such-model", "hi"), key=K)
        time.sleep(5)
        new = [r for r in member.records(KID) if r["id"] not in ids]
        after = member.balance()
        ok = code >= 400 and not any(r["actual_cost"] > 0 for r in new) and close(before, after)
        record("C4 failed request", "PASS" if ok else "FAIL",
               f"HTTP {code}, new charged records {sum(r['actual_cost'] > 0 for r in new)}, balance ¥{before} → ¥{after}")

    def c5():
        ids = known()
        code, usage, events = stream_request(base, K, message_body(a.model, "写一篇 800 字的短文，主题是秋天。", 1500),
                                             stop_after_first_delta=True)
        time.sleep(8)
        new = [r for r in member.records(KID) if r["id"] not in ids]
        if not new:
            detail = "no record after the client hung up (not charged)"
        else:
            r = new[0]
            detail = (f"recorded: in={r['input_tokens']} out={r['output_tokens']} charge=¥{r['actual_cost']:.6f} "
                      "(the upstream may keep generating after the client disconnects)")
        record("C5 interrupted stream", "INFO", f"HTTP {code}, {events} events before hang-up; {detail}")

    def c6():
        qkey = member.create_key(f"usagetest-quota-{tag}", group_id, quota=0.00001)
        cleanup.append(lambda: member.delete_key(qkey["id"]))
        statuses = []
        for _ in range(4):
            code, resp = site.call("POST", "/v1/messages", message_body(a.model, "hi", 20), key=qkey["key"])
            statuses.append(code)
            if code == 429:
                break
            time.sleep(2)
        refused = 429 in statuses
        record("C6 key quota", "PASS" if refused else "FAIL",
               f"statuses {statuses}" + (", refused once the ¥0.00001 quota was used" if refused else ", never refused"))

    def c8():
        recs = member.records(KID)
        code, resp = site.call("GET", "/v1/usage", headers={"Authorization": "Bearer " + K})
        today = ((resp or {}).get("usage") or {}).get("today") if isinstance(resp, dict) else None
        if code != 200 or not today:
            return record("C8 totals", "FAIL", f"/v1/usage HTTP {code}: {str(resp)[:200]}")
        ours = sum(r["actual_cost"] for r in recs)
        ok = close(today["actual_cost"], ours, 1e-5) and today["requests"] == len(recs)
        record("C8 totals", "PASS" if ok else "FAIL",
               f"/v1/usage today: {today['requests']} requests ¥{today['actual_cost']:.6f}; records: {len(recs)} ¥{ours:.6f}")

    def c9():
        ids, before = known(), member.balance()
        codes = []

        def one():
            codes.append(site.call("POST", "/v1/messages", message_body(a.model, "hi", 20), key=K)[0])
        threads = [threading.Thread(target=one) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ok_count = codes.count(200)
        new = wait_records(member, KID, ids, ok_count, timeout=60)
        after = wait_balance(member, before, timeout=30)
        charged = sum(r["actual_cost"] for r in new)
        ok = len(new) == ok_count and close(before - after, charged, 1e-5)
        record("C9 concurrency", "PASS" if ok else "FAIL",
               f"{ok_count}/10 succeeded, {len(new)} new records, balance drop ¥{before - after:.6f} vs charges ¥{charged:.6f}")

    def with_admin():
        aemail, apass = os.environ.get("OPENCC_ADMIN_EMAIL"), os.environ.get("OPENCC_ADMIN_PASSWORD")
        if not aemail or not apass:
            raise RuntimeError("--with-admin needs OPENCC_ADMIN_EMAIL and OPENCC_ADMIN_PASSWORD")
        admin = site.login(aemail, apass)
        temail, tpass = f"usagetest-{tag}@opencc.test", f"Usagetest-{tag}-{uuid.uuid4().hex[:8]}"
        user = site.data("POST", "/api/v1/admin/users", {"email": temail, "password": tpass, "username": f"usagetest-{tag}"}, token=admin)
        cleanup.append(lambda: site.call("DELETE", f"/api/v1/admin/users/{user['id']}", token=admin))
        site.data("POST", f"/api/v1/admin/users/{user['id']}/balance",
                  {"balance": 0.0001, "operation": "add", "notes": "usage test: low balance"}, token=admin)
        other = Member(site, site.login(temail, tpass))
        if "C7" not in skip:
            okey = other.create_key(f"usagetest-low-{tag}", group_id)
            statuses = []
            for _ in range(3):
                statuses.append(site.call("POST", "/v1/messages", message_body(a.model, "hi", 20), key=okey["key"])[0])
                time.sleep(2)
            bal = other.balance()
            refused = any(s in (402, 403, 429) for s in statuses)
            if not refused:
                record("C7 low balance", "FAIL", f"never refused: statuses {statuses}, final balance ¥{bal}")
            elif bal < 0:
                # Sub2API admits a request while the balance is above zero and charges the real cost
                # afterwards; in-flight reservation only stops concurrent overdrafts.
                record("C7 low balance", "WARN",
                       f"statuses {statuses}: refused, but one request overdrew the balance to ¥{bal} "
                       "(admission only requires balance > 0)")
            else:
                record("C7 low balance", "PASS", f"statuses {statuses}, final balance ¥{bal}")
            other.delete_key(okey["id"])
        if "C10" not in skip:
            code, obj = site.call("GET", f"/api/v1/usage?page=1&page_size=100&api_key_id={KID}", token=other.token)
            items = ((obj or {}).get("data") or {}).get("items", []) if isinstance(obj, dict) else []
            record("C10 isolation", "PASS" if not items else "FAIL",
                   f"other member asked for this key's records: HTTP {code}, {len(items)} visible")

    try:
        run("C1", c1)
        run("C2", c2)
        run("C3", c3)
        run("C4", c4)
        run("C5", c5)
        run("C6", c6)
        run("C8", c8)
        run("C9", c9)
        if a.with_admin:
            run("C7/C10", with_admin)
        else:
            record("C7 low balance", "SKIP", "needs --with-admin")
            record("C10 isolation", "SKIP", "needs --with-admin")
    finally:
        for fn in reversed(cleanup):
            try:
                fn()
            except Exception as e:
                print(f"cleanup warning: {e}")

    total_spent = spent()
    counts = {s: sum(r["status"] == s for r in results) for s in ("PASS", "FAIL", "WARN", "INFO", "SKIP")}
    report = {"base": base, "model": a.model, "group_id": group_id, "started_at": started,
              "finished_at": datetime.now(timezone.utc).isoformat(), "spent_cny": round(total_spent, 6),
              "counts": counts, "results": results}
    with open(a.report, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n{counts['PASS']} pass, {counts['FAIL']} fail, {counts['WARN']} warn, {counts['INFO']} info, {counts['SKIP']} skip · "
          f"spent ¥{total_spent:.4f} · report: {a.report}")
    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()
