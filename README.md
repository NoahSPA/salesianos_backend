# Salesianos FC — Backend

API REST del backend para la gestión del equipo de fútbol amateur Salesianos FC.

## Stack

- **Python** 3.x
- **FastAPI**
- **MongoDB Atlas**
- **JWT** (autenticación) + cookies

## Requisitos

- Python 3.11+
- Cuenta en MongoDB Atlas (o MongoDB local)

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/NoahSPA/salesianos_backend.git
cd salesianos_backend

# Entorno virtual
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

# Dependencias
pip install -r requirements.txt

# Variables de entorno: copiar plantilla y editar
copy .env.example .env
# Editar .env con tu MONGODB_URI, JWT_SECRET, etc.
```

## Ejecución

### Modo servidor (desarrollo local clásico)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000  
- Documentación Swagger: http://localhost:8000/docs  
- ReDoc: http://localhost:8000/redoc  

### Despliegue (Dokploy / Docker)

Para producción en un VPS con [Dokploy](https://dokploy.com/), usar el **Dockerfile** de la raíz. Ver **[DEPLOY.md](DEPLOY.md)** para pasos y variables de entorno.

```bash
# Local con Docker (opcional)
docker compose up -d
```

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `MONGODB_URI` | URI de conexión a MongoDB Atlas |
| `MONGODB_DB` | Nombre de la base de datos |
| `JWT_SECRET` | Secreto para firmar tokens (cambiar en producción) |
| `JWT_ALG` | Algoritmo JWT (p. ej. HS256) |
| `ACCESS_TOKEN_MINUTES` | Duración del access token |
| `REFRESH_TOKEN_DAYS` | Duración del refresh token |
| `CORS_ORIGINS` | Orígenes permitidos (separados por comas) |
| `BOOTSTRAP_TOKEN` | Token para crear el primer admin (solo desarrollo) |

Ver `.env.example` para la lista completa.

## Scripts

- `scripts/bootstrap_admin.py` — Crear el primer usuario administrador (requiere `BOOTSTRAP_TOKEN`).
- `scripts/create_user.py` — Crear usuarios desde línea de comandos.
- `scripts/e2e_smoke.py` — Pruebas de humo E2E.

## Seguridad

- No subir `.env` ni credenciales al repositorio.
- Usar `JWT_SECRET` fuerte y único en producción.
- Configurar `CORS_ORIGINS` solo con los orígenes del frontend permitidos.
