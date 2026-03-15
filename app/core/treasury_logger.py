"""
Log de llamadas de Tesorería: tiempo desde petición hasta respuesta.
Un solo archivo con todas las llamadas a /api/fees, /api/payments, /api/series,
/api/tournaments, /api/players.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Rutas consideradas parte de Tesorería
_TREASURY_PREFIXES = ("/api/fees", "/api/payments", "/api/series", "/api/tournaments", "/api/players")
_LOCK = asyncio.Lock()


def _is_treasury_path(path: str) -> bool:
    return any(path.startswith(p) for p in _TREASURY_PREFIXES)


def _get_log_path() -> str:
    p = os.environ.get("TREASURY_LOG_PATH", "")
    if not p:
        return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "logs", "treasury_requests.log"))
    return os.path.abspath(p) if not os.path.isabs(p) else p


async def _append_line(line: str) -> None:
    path = _get_log_path()
    dir_path = os.path.dirname(path)
    os.makedirs(dir_path, exist_ok=True)
    async with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class TreasuryRequestLogMiddleware(BaseHTTPMiddleware):
    """Registra cada petición de Tesorería con método, path, duración (ms) y status."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not _is_treasury_path(request.url.path):
            return await call_next(request)

        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        line = f"{ts}\t{request.method}\t{request.url.path}\t{request.url.query or ''}\t{response.status_code}\t{elapsed_ms}"
        asyncio.create_task(_append_line(line))
        return response
