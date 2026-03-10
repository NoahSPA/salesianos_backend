from __future__ import annotations

from datetime import date, datetime
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user, require_roles
from app.core.enums import AttendanceStatus
from app.core.validators import normalize_rut
from app.domains.audit.service import log_audit
from app.domains.convocations.repo import (
    get_attendance_status,
    get_convocation,
    get_convocation_by_match,
    get_convocation_by_public_link,
    set_attendance,
    upsert_convocation,
)
from app.domains.convocations.schemas import (
    AttendanceOverride,
    AttendanceRespondPublic,
    ConvocationOut,
    ConvocationStatusOut,
    ConvocationUpsert,
    PublicConvocationInfo,
)
from app.domains.matches.repo import get_match
from app.domains.players.repo import get_player
from app.domains.series.repo import get_series

router = APIRouter(tags=["convocations"])


_BIRTH_DDMMYYYY = re.compile(r"^\s*(\d{2})[/-](\d{2})[/-](\d{4})\s*$")


def _parse_birth_date(value: str) -> date:
    v = (value or "").strip()
    # ISO (yyyy-mm-dd) ideal
    try:
        return date.fromisoformat(v)
    except Exception:
        pass
    # dd/mm/yyyy o dd-mm-yyyy (común en WhatsApp)
    m = _BIRTH_DDMMYYYY.match(v)
    if m:
        dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(yyyy, mm, dd)
    raise ValueError("birth_date inválida")


def _normalize_stored_birth(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception:
            return None
    return None


@router.post("/matches/{match_id}/convocation", response_model=ConvocationOut, dependencies=[Depends(require_roles("admin", "delegado"))])
async def upsert_match_convocation(match_id: str, payload: ConvocationUpsert, actor=Depends(get_current_user)) -> ConvocationOut:
    match = await get_match(match_id)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partido no encontrado")

    before = await get_convocation_by_match(match_id=match_id, series_id=match["series_id"])
    conv = await upsert_convocation(
        match_id=match_id,
        series_id=match["series_id"],
        invited_player_ids=list(dict.fromkeys(payload.invited_player_ids)),
        created_by_user_id=actor["id"],
    )
    await log_audit(
        actor=actor,
        action="convocation_upserted",
        entity_type="convocation",
        entity_id=conv["id"],
        before=before,
        after=conv,
        meta={"match_id": match_id, "series_id": match["series_id"]},
    )
    return ConvocationOut(**conv)


@router.get("/matches/{match_id}/convocation", response_model=ConvocationOut, dependencies=[Depends(get_current_user)])
async def get_match_convocation(match_id: str) -> ConvocationOut:
    match = await get_match(match_id)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partido no encontrado")
    conv = await get_convocation_by_match(match_id=match_id, series_id=match["series_id"])
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convocatoria no encontrada")
    return ConvocationOut(**conv)


@router.get("/convocations/{convocation_id}", response_model=ConvocationOut, dependencies=[Depends(get_current_user)])
async def convocation_get(convocation_id: str) -> ConvocationOut:
    conv = await get_convocation(convocation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return ConvocationOut(**conv)


@router.get("/convocations/{convocation_id}/status", response_model=ConvocationStatusOut, dependencies=[Depends(get_current_user)])
async def convocation_status(convocation_id: str) -> ConvocationStatusOut:
    conv = await get_convocation(convocation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    invited = conv["invited_player_ids"]
    status_rows = await get_attendance_status(convocation_id=convocation_id, invited_player_ids=invited)
    status_map = {r["player_id"]: r for r in status_rows}

    lines = []
    confirmed = declined = pending = 0
    for pid in invited:
        p = await get_player(pid)
        if not p:
            continue
        row = status_map.get(pid)
        st = AttendanceStatus((row or {}).get("status", AttendanceStatus.pending.value))
        if st == AttendanceStatus.confirmed:
            confirmed += 1
        elif st == AttendanceStatus.declined:
            declined += 1
        else:
            pending += 1
        lines.append(
            {
                "player_id": pid,
                "player_name": f"{p['first_name']} {p['last_name']}",
                "status": st,
                "comment": (row or {}).get("comment"),
                "updated_at": (row or {}).get("updated_at") or conv["updated_at"],
            }
        )

    return ConvocationStatusOut(
        convocation_id=convocation_id,
        match_id=conv["match_id"],
        series_id=conv["series_id"],
        public_link_id=conv["public_link_id"],
        invited_count=len(invited),
        confirmed_count=confirmed,
        declined_count=declined,
        pending_count=pending,
        lines=lines,
    )


@router.get("/public/convocations/{public_link_id}", response_model=PublicConvocationInfo)
async def public_convocation_info(public_link_id: str) -> PublicConvocationInfo:
    conv = await get_convocation_by_public_link(public_link_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    match = await get_match(conv["match_id"])
    series = await get_series(conv["series_id"])
    if not match or not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    return PublicConvocationInfo(
        public_link_id=public_link_id,
        series_name=series["name"],
        opponent=match["opponent"],
        match_date=str(match["match_date"]),
        call_time=match["call_time"],
        venue=match["venue"],
        field_number=match.get("field_number"),
    )


@router.post("/public/convocations/{public_link_id}/respond")
async def public_convocation_respond(public_link_id: str, payload: AttendanceRespondPublic, request: Request) -> dict:
    conv = await get_convocation_by_public_link(public_link_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    # Validación simple y segura (MVP): RUT + fecha de nacimiento
    rut = normalize_rut(payload.rut)
    try:
        birth = _parse_birth_date(payload.birth_date)
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo validar (verifica fecha)")

    # Busca jugador por RUT
    # (evitamos exponer si existe o no con mensajes genéricos)
    from app.db.mongo import get_db

    db = get_db()
    player_doc = await db.players.find_one({"rut": rut, "active": True})
    stored_birth = _normalize_stored_birth(player_doc.get("birth_date") if player_doc else None)
    if (not player_doc) or (stored_birth != birth):
        raise HTTPException(status_code=400, detail="No se pudo validar")

    player_id = str(player_doc["_id"])
    if player_id not in conv["invited_player_ids"]:
        raise HTTPException(status_code=400, detail="No se pudo validar (no estás convocado)")

    await set_attendance(
        convocation_id=conv["id"],
        match_id=conv["match_id"],
        series_id=conv["series_id"],
        player_id=player_id,
        status=payload.status,
        comment=payload.comment,
        origin="jugador",
        actor_user_id=None,
        meta={"public_link_id": public_link_id, "ip": getattr(request.client, "host", None)},
    )

    await log_audit(
        actor=None,
        action="attendance_public_responded",
        entity_type="attendance",
        entity_id=f"{conv['id']}:{player_id}",
        before=None,
        after={"status": payload.status.value, "comment": payload.comment},
        meta={"origin": "jugador", "public_link_id": public_link_id},
    )
    return {"ok": True}


@router.post("/convocations/{convocation_id}/override", dependencies=[Depends(require_roles("admin", "delegado"))])
async def convocation_override(convocation_id: str, payload: AttendanceOverride, actor=Depends(get_current_user)) -> dict:
    conv = await get_convocation(convocation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    if payload.player_id not in conv["invited_player_ids"]:
        raise HTTPException(status_code=400, detail="Jugador no está convocado")

    await set_attendance(
        convocation_id=convocation_id,
        match_id=conv["match_id"],
        series_id=conv["series_id"],
        player_id=payload.player_id,
        status=payload.status,
        comment=payload.comment,
        origin="delegado" if actor["role"] == "delegado" else "admin",
        actor_user_id=actor["id"],
        meta={"reason": payload.reason},
    )

    await log_audit(
        actor=actor,
        action="attendance_overridden",
        entity_type="attendance",
        entity_id=f"{convocation_id}:{payload.player_id}",
        after={"status": payload.status.value, "comment": payload.comment},
        meta={"reason": payload.reason},
    )
    return {"ok": True}

