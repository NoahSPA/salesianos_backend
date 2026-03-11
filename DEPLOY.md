# Despliegue Backend (Dokploy)

## Build

- **Método:** Dockerfile (no Nixpacks).
- **Contexto:** raíz del repo (`backend` es la raíz en `salesianos_backend`).
- **Puerto del contenedor:** 8000.
- **Health check:** `GET /api/health` → 200.

## Variables de entorno (obligatorias en Dokploy)

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `MONGODB_URI` | URI de MongoDB (Atlas o local) | `mongodb+srv://user:pass@cluster...` |
| `MONGODB_DB` | Nombre de la base | `salesianos_fc` |
| `JWT_SECRET` | Secreto para firmar JWT | string largo y aleatorio |
| `CORS_ORIGINS` | Orígenes permitidos (comas) | `https://tudominio.com,https://www.tudominio.com` |

## Variables opcionales

- `JWT_ALG` (default: HS256)
- `ACCESS_TOKEN_MINUTES` (default: 30)
- `REFRESH_TOKEN_DAYS` (default: 30)
- `COOKIE_SECURE` (default: false; true si usas HTTPS)
- `COOKIE_DOMAIN` (default: vacío)
- `BOOTSTRAP_TOKEN` (para crear el primer admin si no hay usuarios)
- `ENVIRONMENT` (default: dev; usar `prod` en producción)

## CORS

Incluir en `CORS_ORIGINS` la URL pública del frontend (la que usa Dokploy), por ejemplo:

```
https://salesianos.tudominio.com
```

Sin esa URL, el navegador bloqueará las peticiones al API.
