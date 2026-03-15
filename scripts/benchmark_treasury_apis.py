#!/usr/bin/env python3
"""
Test de eficiencia de las APIs de Tesorería.
Mide tiempos de respuesta y analiza hasta 200 ms como umbral objetivo.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

NUM_RUNS = 20
TARGET_MS = 200  # Umbral objetivo (ms)


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"detail": raw}


def http_get(url: str, headers: dict | None = None) -> tuple[int, dict, float]:
    """GET request; returns (status, body_dict, elapsed_ms)."""
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url=url, headers=h, method="GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
            elapsed = (time.perf_counter() - t0) * 1000
            return resp.status, json.loads(data) if data else {}, elapsed
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - t0) * 1000
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw), elapsed
        except Exception:
            return e.code, {"detail": raw}, elapsed


def stats(times_ms: list[float]) -> dict:
    if not times_ms:
        return {"min": 0, "max": 0, "avg": 0, "median": 0, "p95": 0}
    sorted_t = sorted(times_ms)
    n = len(sorted_t)
    p95_idx = int(n * 0.95) - 1 if n >= 1 else 0
    p95_idx = max(0, p95_idx)
    return {
        "min": round(min(times_ms), 2),
        "max": round(max(times_ms), 2),
        "avg": round(statistics.mean(times_ms), 2),
        "median": round(statistics.median(times_ms), 2),
        "p95": round(sorted_t[p95_idx], 2),
    }


def main() -> int:
    base = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("ADMIN_PASSWORD")

    if not admin_pass:
        print("ERROR: define ADMIN_PASSWORD para ejecutar el benchmark.")
        return 2

    # Login (POST)
    st, login = _post_json(f"{base}/api/auth/login", {"username": admin_user, "password": admin_pass})
    if st != 200:
        print("FAIL login", st, login)
        return 1

    token = login.get("access_token")
    if not token:
        print("FAIL login token missing", login)
        return 1

    auth = {"Authorization": f"Bearer {token}"}
    print("OK login\n")

    # Endpoints de Tesorería (sin params para baseline)
    endpoints = [
        ("GET /api/payments?status=pending_validation&limit=200", f"{base}/api/payments?status=pending_validation&limit=200"),
        ("GET /api/series", f"{base}/api/series"),
        ("GET /api/tournaments", f"{base}/api/tournaments"),
        ("GET /api/players?active=true", f"{base}/api/players?active=true"),
        ("GET /api/fees/rules", f"{base}/api/fees/rules"),
        ("GET /api/fees/dashboard-totals", f"{base}/api/fees/dashboard-totals"),
        ("GET /api/fees/dashboard-periods", f"{base}/api/fees/dashboard-periods"),
        ("GET /api/fees/dashboard-breakdown", f"{base}/api/fees/dashboard-breakdown"),
        ("GET /api/fees/player-period-matrix", f"{base}/api/fees/player-period-matrix"),
        ("GET /api/fees/status", f"{base}/api/fees/status"),
    ]

    results: list[tuple[str, dict, list[float]]] = []
    for label, url in endpoints:
        times: list[float] = []
        errors = 0
        for _ in range(NUM_RUNS):
            status, _, elapsed = http_get(url, headers=auth)
            if 200 <= status < 300:
                times.append(elapsed)
            else:
                errors += 1
        s = stats(times) if times else {"min": 0, "max": 0, "avg": 0, "median": 0, "p95": 0}
        results.append((label, s, times))

    # Reporte
    print("=" * 70)
    print("BENCHMARK APIs Tesorería")
    print(f"  Runs por endpoint: {NUM_RUNS}  |  Umbral objetivo: {TARGET_MS} ms")
    print("=" * 70)

    over: list[str] = []
    for label, s, times in results:
        ok = "✓" if s["p95"] <= TARGET_MS else "⚠"
        if s["p95"] > TARGET_MS:
            over.append(f"{label} (p95={s['p95']} ms)")
        print(f"\n{label}")
        print(f"  min={s['min']} ms  max={s['max']} ms  avg={s['avg']} ms  median={s['median']} ms  p95={s['p95']} ms  {ok}")

    print("\n" + "=" * 70)
    if over:
        print(f"⚠ Endpoints por encima de {TARGET_MS} ms (p95):")
        for x in over:
            print(f"  - {x}")
        return 0  # no falla, solo reporta
    else:
        print(f"✓ Todos los endpoints bajo {TARGET_MS} ms (p95)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
