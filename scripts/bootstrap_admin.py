from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.error
import urllib.request
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


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    env_path = backend_dir / ".env"

    base_url = os.environ.get("API_BASE_URL", "http://localhost:8001").rstrip("/")
    token = os.environ.get("BOOTSTRAP_TOKEN") or _read_env_value(env_path, "BOOTSTRAP_TOKEN")
    if not token:
        print("ERROR: No se encontró BOOTSTRAP_TOKEN (env var o backend/.env).")
        return 2

    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(24)

    payload = {"token": token, "username": username, "password": password}
    req = urllib.request.Request(
        url=f"{base_url}/api/auth/bootstrap-admin",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:
            detail = body or str(e)
        print(f"ERROR: HTTP {e.code} - {detail}")
        return 1
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    # No imprimimos el token nunca.
    print("ADMIN_CREATED:", json.dumps(data, ensure_ascii=False))
    print("ADMIN_USERNAME:", username)
    print("ADMIN_PASSWORD:", password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

