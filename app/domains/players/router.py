from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user, require_roles
from app.core.validators import normalize_rut
from app.db.ids import oid
from app.domains.audit.service import log_audit
from app.domains.players.repo import create_player, get_player, list_players, update_player, upsert_by_rut
from app.domains.players.schemas import PlayerCreate, PlayerImportResult, PlayerOut, PlayerUpdate

router = APIRouter(prefix="/players", tags=["players"])


def _ensure_primary_in_series(primary: str, series: list[str]) -> list[str]:
    if primary not in series:
        return [primary, *series]
    return series


@router.get("", response_model=list[PlayerOut], dependencies=[Depends(get_current_user)])
async def players_list(active: bool | None = None, series_id: str | None = None, q: str | None = None) -> list[PlayerOut]:
    docs = await list_players(active=active, series_id=series_id, q=q)
    return [PlayerOut(**d) for d in docs]


@router.post("", response_model=PlayerOut, dependencies=[Depends(require_roles("admin"))])
async def players_create(payload: PlayerCreate, actor=Depends(get_current_user)) -> PlayerOut:
    data = payload.model_dump()
    raw_primary = (data.get("primary_series_id") or "").strip()
    if not raw_primary:
        raise HTTPException(status_code=400, detail="Falta serie principal")
    try:
        data["primary_series_id"] = oid(raw_primary)
    except ValueError:
        raise HTTPException(status_code=400, detail="Serie principal inválida")
    data["series_ids"] = [oid(x) for x in _ensure_primary_in_series(payload.primary_series_id, payload.series_ids)]
    # Mongo solo acepta tipos simples: positions como list[str]
    data["positions"] = [p.value if hasattr(p, "value") else str(p) for p in (data.get("positions") or [])]
    data.pop("position_primary", None)
    data.pop("position_secondary", None)
    data.pop("level", None)
    created = await create_player(data)
    await log_audit(
        actor=actor,
        action="player_created",
        entity_type="player",
        entity_id=created["id"],
        after=created,
    )
    return PlayerOut(**created)


@router.get("/{player_id}", response_model=PlayerOut, dependencies=[Depends(get_current_user)])
async def players_get(player_id: str) -> PlayerOut:
    doc = await get_player(player_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return PlayerOut(**doc)


@router.patch("/{player_id}", response_model=PlayerOut, dependencies=[Depends(require_roles("admin"))])
async def players_patch(player_id: str, payload: PlayerUpdate, actor=Depends(get_current_user)) -> PlayerOut:
    before = await get_player(player_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    patch = payload.model_dump(exclude_unset=True)
    if patch.get("primary_series_id") and patch.get("series_ids") is not None:
        patch["series_ids"] = _ensure_primary_in_series(patch["primary_series_id"], patch["series_ids"])
    if "positions" in patch and patch["positions"] is not None:
        patch["positions"] = [p.value if hasattr(p, "value") else str(p) for p in patch["positions"]]
    patch.pop("position_primary", None)
    patch.pop("position_secondary", None)
    patch.pop("level", None)
    after = await update_player(player_id, patch)
    await log_audit(
        actor=actor,
        action="player_updated",
        entity_type="player",
        entity_id=player_id,
        before=before,
        after=after,
    )
    return PlayerOut(**after)


@router.post("/import-csv", response_model=PlayerImportResult, dependencies=[Depends(require_roles("admin"))])
async def players_import_csv(
    actor=Depends(get_current_user),
    file: UploadFile = File(...),
) -> PlayerImportResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Archivo debe ser CSV")
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=400, detail="CSV demasiado grande (máx 2MB)")

    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    inserted = updated = skipped = 0
    errors: list[dict] = []

    for idx, row in enumerate(reader, start=2):  # header=1
        try:
            first_name = (row.get("first_name") or row.get("nombre") or "").strip()
            last_name = (row.get("last_name") or row.get("apellido") or "").strip()
            rut = normalize_rut(row.get("rut") or "")
            birth = (row.get("birth_date") or row.get("fecha_nacimiento") or "").strip()
            phone = (row.get("phone") or row.get("telefono") or "").strip()
            primary_series_id = (row.get("primary_series_id") or row.get("serie_principal_id") or "").strip()
            series_ids_raw = (row.get("series_ids") or row.get("series_ids_csv") or row.get("series") or "").strip()
            position_primary = (row.get("position_primary") or row.get("posicion_principal") or "").strip()
            position_secondary = (row.get("position_secondary") or row.get("posicion_secundaria") or "").strip() or None
            level = (row.get("level") or row.get("nivel") or "").strip()
            notes = (row.get("notes") or row.get("observaciones") or "").strip() or None

            if not (first_name and last_name and birth and phone and primary_series_id and position_primary and level):
                raise ValueError("Faltan campos obligatorios")

            birth_date = date.fromisoformat(birth)
            series_ids = [x.strip() for x in series_ids_raw.split(",") if x.strip()] if series_ids_raw else []
            series_ids = _ensure_primary_in_series(primary_series_id, series_ids)

            # posiciones: primary + secondary -> lista única
            positions = [x.strip() for x in [position_primary, position_secondary or ""] if x.strip()]

            # nivel: aceptar 1..5 o palabras (bajo/medio/alto)
            level_stars: int
            try:
                level_stars = int(level)
            except Exception:
                lvl = level.strip().lower()
                level_stars = 2 if lvl == "bajo" else 3 if lvl == "medio" else 4 if lvl == "alto" else 3
            level_stars = max(1, min(5, level_stars))

            doc = {
                "first_name": first_name,
                "last_name": last_name,
                "rut": rut,
                "birth_date": birth_date,
                "phone": phone,
                "primary_series_id": oid(primary_series_id),
                "series_ids": [oid(x) for x in series_ids],
                "positions": positions,
                "level_stars": level_stars,
                "active": True,
                "notes": notes,
            }

            mode, out = await upsert_by_rut(rut=rut, doc=doc)
            if mode == "inserted":
                inserted += 1
                await log_audit(actor=actor, action="player_created_csv", entity_type="player", entity_id=out["id"], after=out)
            else:
                updated += 1
                await log_audit(actor=actor, action="player_updated_csv", entity_type="player", entity_id=out["id"], after=out)
        except Exception as e:
            skipped += 1
            errors.append({"line": idx, "error": str(e), "row": {k: (v or "") for k, v in row.items()}})

    return PlayerImportResult(inserted=inserted, updated=updated, skipped=skipped, errors=errors)

