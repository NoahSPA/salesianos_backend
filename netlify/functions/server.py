"""
Handler para Netlify Functions: expone la app FastAPI como función serverless (Lambda).
Usado por `netlify dev` y por el despliegue en Netlify.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Resolver root del backend: Lambda usa LAMBDA_TASK_ROOT, local usa path relativo.
_task_root = os.environ.get("LAMBDA_TASK_ROOT")
_backend_root = Path(_task_root) if _task_root else Path(__file__).resolve().parent.parent.parent
if not _backend_root.is_dir():
    _backend_root = Path(__file__).resolve().parent.parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.main import app
from mangum import Mangum

# Handler Lambda-compatible que Netlify invoca para cada request
handler = Mangum(app, lifespan="auto")
