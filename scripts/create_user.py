"""
Crea un usuario (tesorero, delegado o jugador) en la base de datos.

Uso (desde la raíz del backend, con .env cargado):
  python -m scripts.create_user USERNAME PASSWORD ROLE

  ROLE: tesorero | delegado | jugador

Ejemplo:
  python -m scripts.create_user tesorero1 MiClaveSegura123 tesorero
  python -m scripts.create_user delegado1 MiClaveSegura123 delegado
  python -m scripts.create_user jugador1 MiClaveSegura123 jugador

Requisitos: contraseña mínimo 8 caracteres. Usuario mínimo 3 caracteres.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add backend root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_password
from app.db.mongo import get_db, now_utc

ROLES = ("tesorero", "delegado", "jugador")


async def main(username: str, password: str, role: str) -> int:
    if len(username) < 3:
        print("ERROR: Usuario debe tener al menos 3 caracteres.")
        return 2
    if len(password) < 8:
        print("ERROR: Contraseña debe tener al menos 8 caracteres.")
        return 2
    if role not in ROLES:
        print(f"ERROR: Rol debe ser uno de: {', '.join(ROLES)}")
        return 2

    db = get_db()
    existing = await db.users.find_one({"username": username})
    if existing:
        print(f"ERROR: Ya existe un usuario con nombre '{username}'.")
        return 1

    now = now_utc()
    doc = {
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(doc)
    print(f"Usuario creado: {username} (rol: {role})")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crea un usuario tesorero, delegado o jugador.",
        epilog="Ejemplo: python -m scripts.create_user tesorero1 MiClave123 tesorero",
    )
    parser.add_argument("username", help="Nombre de usuario (mín. 3 caracteres)")
    parser.add_argument("password", help="Contraseña (mín. 8 caracteres)")
    parser.add_argument("role", choices=ROLES, help="Rol del usuario")
    args = parser.parse_args()

    exit_code = asyncio.run(main(args.username, args.password, args.role))
    sys.exit(exit_code)
