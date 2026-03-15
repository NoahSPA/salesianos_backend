from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.http import SecurityHeadersMiddleware
from app.core.settings import settings
from app.core.treasury_logger import TreasuryRequestLogMiddleware
from app.db.indexes import ensure_indexes
from app.db.mongo import close_client, get_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    await ensure_indexes(get_db())
    yield
    await close_client()


app = FastAPI(
    title="Salesianos FC API",
    version="0.1.0",
    lifespan=lifespan,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TreasuryRequestLogMiddleware)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(api_router)

