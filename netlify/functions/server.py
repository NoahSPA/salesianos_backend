"""
Handler para Netlify Functions: expone la app FastAPI como función serverless (Lambda).
Usado por `netlify dev` y por el despliegue en Netlify.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Asegurar que el root del backend está en el path (Netlify ejecuta desde otra cwd)
_backend_root = Path(__file__).resolve().parent.parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.main import app
from mangum import Mangum

# Handler Lambda-compatible que Netlify invoca para cada request
handler = Mangum(app, lifespan="auto")
