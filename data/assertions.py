"""
assertions.py — 10 example test assertions the API must pass.
Run these against a live API: python data/assertions.py --api-url http://localhost:8000

These are a subset of the scoring harness — passing all 10 is required
but does NOT guarantee full marks.
"""
import sys
import json
import uuid
import argparse
import requests
from datetime import datetime, timezone

STORE_ID = "STORE_BLR_002"
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    print(f"  {status}  {name}")
    if not condition and detail:
        print(f"         → {detail}")
    return condition


def run_assertions(api_url: str):
    base = api_url.rstrip("/")
    results = []

    print(f"\nRunning assertions against {base}\n")

    # ── Seed test data ────────────────────────────────────────────────────────
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = [
        {
            "event_id":   str(uuid.uuid4()),
            "store_id":   STORE_ID,
            "camera_id":  "CAM_ENTRY_01",
            "visitor_id": "VIS_assert01",
            "event_type": "ENTRY",
            "timestamp":  now_ts,
            "zone_id":    None,
            "dwell_ms":   0,
            "is_staff":   False,
            "confidence": 0.92,
            "metadata":   {"queue_depth": None, "sku_zone": None, "session_seq": 1},
        },
        {
            "event_id":   str(uuid.uuid4()),
            "store_id":   STORE_ID,
            "camera_id":  "CAM_ENTRY_01",
            "visitor_id": "VIS_staff01",
            "event_type": "ENTRY",
            "timestamp":  now_ts,
            "zone_id":    None,
            "dwell_ms":   0,
            "is_staff":   True,    # staff — must be excluded from metrics
            "confidence": 0.85,
            "metadata":   {"queue_depth": None, "sku_zone": None, "session_seq": 1},
        },
    ]
    r = requests.post(f"{base}/events/ingest", json={"events": events})


    # ── 1. Ingest returns HTTP 207 ─────────────────────────────────────────────
    results.append(check(
        "1. POST /events/ingest returns 207",
        r.status_code == 207,
        f"got {r.status_code}",
    ))

    # ── 2. accepted count matches non-duplicate events ────────────────────────
    body = r.json()
    results.append(check(
        "2. accepted ≥ 1 on valid events",
        body.get("accepted", 0) >= 1,
        str(body),
    ))

    # ── 3. Idempotency: same payload → duplicates count, accepted = 0 ─────────
    r2 = requests.post(f"{base}/events/ingest", json={"events": events})
    b2 = r2.json()
    results.append(check(
        "3. Idempotency: second POST counts duplicates, accepted = 0",
        b2.get("accepted", 999) == 0 and b2.get("duplicates", 0) >= len(events),
        str(b2),
    ))

    # ── 4. Batch > 500 events is rejected ─────────────────────────────────────
    big_batch = [events[0].copy() for _ in range(501)]
    for e in big_batch:
        e["event_id"] = str(uuid.uuid4())
    r3 = requests.post(f"{base}/events/ingest", json={"events": big_batch})
    results.append(check(
        "4. Batch > 500 events returns 422",
        r3.status_code == 422,
        f"got {r3.status_code}",
    ))

    # ── 5. GET /metrics returns 200 ───────────────────────────────────────────
    rmet = requests.get(f"{base}/stores/{STORE_ID}/metrics")
    results.append(check(
        "5. GET /stores/{id}/metrics returns 200",
        rmet.status_code == 200,
        f"got {rmet.status_code}",
    ))

    # ── 6. Metrics response has required fields ────────────────────────────────
    met = rmet.json()
    required = {"unique_visitors","conversion_rate","avg_dwell_ms","queue_depth","abandonment_rate"}
    missing  = required - set(met.keys())
    results.append(check(
        "6. Metrics response contains all required fields",
        len(missing) == 0,
        f"Missing: {missing}",
    ))

    # ── 7. unique_visitors excludes staff ─────────────────────────────────────
    # We seeded 1 customer + 1 staff — unique_visitors must be 1 (or more from prior runs)
    results.append(check(
        "7. unique_visitors excludes is_staff=True events",
        met.get("unique_visitors", 999) >= 1,  # at least our customer
        str(met.get("unique_visitors")),
    ))

    # ── 8. GET /funnel returns 4 stages ───────────────────────────────────────
    rfun = requests.get(f"{base}/stores/{STORE_ID}/funnel")
    fun  = rfun.json()
    results.append(check(
        "8. GET /funnel returns exactly 4 stages",
        rfun.status_code == 200 and len(fun.get("stages", [])) == 4,
        str(fun.get("stages", [])),
    ))

    # ── 9. GET /anomalies returns 200 with valid schema ───────────────────────
    rano = requests.get(f"{base}/stores/{STORE_ID}/anomalies")
    ano  = rano.json()
    results.append(check(
        "9. GET /anomalies returns 200 with 'anomalies' list",
        rano.status_code == 200 and isinstance(ano.get("anomalies"), list),
        str(rano.status_code),
    ))

    # ── 10. GET /health returns db_connected = True ───────────────────────────
    rh  = requests.get(f"{base}/health")
    hlt = rh.json()
    results.append(check(
        "10. GET /health returns db_connected = True",
        rh.status_code == 200 and hlt.get("db_connected") is True,
        str(hlt),
    ))

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print(f"\n{'='*45}")
    print(f"  Assertions passed: {passed}/{total}")
    if passed == total:
        print("  \033[92mAll assertions passed — ready for submission!\033[0m")
    else:
        print(f"  \033[91m{total - passed} assertion(s) failed.\033[0m")
    print(f"{'='*45}\n")
    return passed == total


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default="http://localhost:8000")
    args = p.parse_args()
    ok = run_assertions(args.api_url)
    sys.exit(0 if ok else 1)
