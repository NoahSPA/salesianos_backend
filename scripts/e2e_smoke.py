from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path


def _read_env_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(key + "="):
            continue
        value = line.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return value
    return None


def http_json(method: str, url: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    body = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if data else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"detail": raw}


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    env_path = backend_dir / ".env"

    base = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("ADMIN_PASSWORD")  # opcional

    # Login (si no hay pass, se espera que ya exista en sesión manual)
    if not admin_pass:
        print("ERROR: setea ADMIN_PASSWORD para ejecutar e2e_smoke (no lo guardo en repo).")
        return 2

    st, login = http_json("POST", f"{base}/api/auth/login", {"username": admin_user, "password": admin_pass})
    if st != 200:
        print("FAIL login", st, login)
        return 1
    token = login.get("access_token")
    if not token:
        print("FAIL login token missing", login)
        return 1
    auth = {"Authorization": f"Bearer {token}"}
    print("OK login")

    # Serie
    ts = int(time.time())
    st, serie = http_json("POST", f"{base}/api/series", {"name": f"E2E Serie {ts}", "code": f"E2E{ts}", "active": True}, auth)
    if st != 200:
        print("FAIL series create", st, serie)
        return 1
    series_id = serie["id"]
    print("OK series", series_id)

    # Torneo
    st, torneo = http_json(
        "POST",
        f"{base}/api/tournaments",
        {"name": f"E2E Torneo {ts}", "season_year": date.today().year, "active": True, "series_ids": [series_id]},
        auth,
    )
    if st != 200:
        print("FAIL tournament create", st, torneo)
        return 1
    tournament_id = torneo["id"]
    print("OK tournament", tournament_id)

    # Jugador
    st, player = http_json(
        "POST",
        f"{base}/api/players",
        {
            "first_name": "E2E",
            "last_name": f"Player{ts}",
            "rut": f"{ts % 90000000 + 10000000}-5",
            "birth_date": "1990-05-20",
            "phone": "+56911111111",
            "primary_series_id": series_id,
            "series_ids": [],
            "positions": ["cm", "dm"],
            "level_stars": 3,
            "active": True,
            "notes": None,
        },
        auth,
    )
    if st != 200:
        print("FAIL player create", st, player)
        return 1
    player_id = player["id"]
    print("OK player", player_id)

    # Partido
    st, match = http_json(
        "POST",
        f"{base}/api/matches",
        {
            "tournament_id": tournament_id,
            "series_id": series_id,
            "opponent": "E2E Rival",
            "match_date": "2026-03-25",
            "call_time": "10:00",
            "venue": "E2E Cancha",
            "field_number": "1",
            "notes": None,
            "status": "programado",
        },
        auth,
    )
    if st != 200:
        print("FAIL match create", st, match)
        return 1
    match_id = match["id"]
    print("OK match", match_id)

    # Convocatoria + link
    st, conv = http_json("POST", f"{base}/api/matches/{match_id}/convocation", {"invited_player_ids": [player_id]}, auth)
    if st != 200:
        print("FAIL convocation create", st, conv)
        return 1
    public_link_id = conv["public_link_id"]
    conv_id = conv["id"]
    print("OK convocation", conv_id, public_link_id)

    # Public info + respond
    st, info = http_json("GET", f"{base}/api/public/convocations/{public_link_id}")
    if st != 200:
        print("FAIL public convocation info", st, info)
        return 1
    st, resp = http_json(
        "POST",
        f"{base}/api/public/convocations/{public_link_id}/respond",
        {"rut": player["rut"], "birth_date": "20/05/1990", "status": "confirmed", "comment": "ok"},
    )
    if st != 200:
        print("FAIL public respond", st, resp)
        return 1
    print("OK public respond")

    # Fees: crear regla general + generar mes + status
    st, rule = http_json(
        "POST",
        f"{base}/api/fees/rules",
        {"scope": "general", "scope_id": None, "amount": 15000, "currency": "CLP", "active": True, "effective_from": str(date.today()), "effective_to": None},
        auth,
    )
    if st not in (200, 409, 400):
        # si ya existe una regla general con unique constraints/logic puede variar; no fallamos fuerte
        print("WARN fee rule create", st, rule)
    ym = f"{date.today().year:04d}-{date.today().month:02d}"
    st, gen = http_json("POST", f"{base}/api/fees/generate-month?yearMonth={ym}", None, auth)
    if st != 200:
        print("FAIL generate month", st, gen)
        return 1
    st, status_list = http_json("GET", f"{base}/api/fees/status", None, auth)
    if st != 200:
        print("FAIL fees status", st, status_list)
        return 1
    print("OK fees status")

    # Payments: crear + validar
    st, pay = http_json(
        "POST",
        f"{base}/api/payments",
        {"player_id": player_id, "amount": 150000, "currency": "CLP", "transfer_ref": f"E2E-{ts}", "notes_player": "pago"},
        auth,
    )
    if st != 200:
        print("FAIL payment create", st, pay)
        return 1
    pay_id = pay["id"]
    st, val = http_json("POST", f"{base}/api/payments/{pay_id}/validate", {"notes_treasurer": "e2e validate"}, auth)
    if st != 200:
        print("FAIL payment validate", st, val)
        return 1
    print("OK payment validate")

    # Audit list
    st, audit = http_json("GET", f"{base}/api/audit?limit=5", None, auth)
    if st != 200:
        print("FAIL audit", st, audit)
        return 1
    print("OK audit")

    print("E2E_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

