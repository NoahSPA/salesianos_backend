from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import health
from app.domains.auth.router import router as auth_router
from app.domains.audit.router import router as audit_router
from app.domains.series.router import router as series_router
from app.domains.tournaments.router import router as tournaments_router
from app.domains.players.router import router as players_router
from app.domains.matches.router import router as matches_router
from app.domains.convocations.router import router as convocations_router
from app.domains.fees.router import router as fees_router
from app.domains.fees.payments_router import router as payments_router
from app.domains.rivals.router import router as rivals_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(series_router)
api_router.include_router(tournaments_router)
api_router.include_router(players_router)
api_router.include_router(matches_router)
api_router.include_router(convocations_router)
api_router.include_router(fees_router)
api_router.include_router(payments_router)
api_router.include_router(rivals_router)

