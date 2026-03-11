# Despliegue Backend (Dokploy)

## Crear imagen y subir a Docker Hub

Usuario Docker Hub: **joseschmeisser**.

```bash
cd backend   # o la ruta del repo salesianos_backend

# Login (solo la primera vez o cuando expire)
docker login

# Crear la imagen
docker build -t joseschmeisser/salesianos-backend:latest .

# Etiquetar (si ya construiste con otro nombre)
docker tag salesianos-backend:latest joseschmeisser/salesianos-backend:latest

# Subir a Docker Hub
docker push joseschmeisser/salesianos-backend:latest
```

Para una versión concreta (ej. `v1.0.0`):

```bash
docker build -t joseschmeisser/salesianos-backend:v1.0.0 .
docker push joseschmeisser/salesianos-backend:v1.0.0
```

En Dokploy puedes usar **Build Type: Dockerfile** (que construye desde el repo) o, si prefieres usar la imagen preconstruida de Docker Hub, configurar la aplicación para **imagen** `joseschmeisser/salesianos-backend:latest` y no hacer build desde código.

---

## Build en Dokploy

**En la aplicación backend en Dokploy:**

1. **Build Type:** Dockerfile (no Nixpacks ni Auto).
2. **Dockerfile path:** `Dockerfile` (raíz del repo).
3. **Build context:** raíz (`.`).
4. **Puerto del contenedor:** 8000.
5. Guarda y desplegar.

---

## URLs de producción (VPS 76.13.160.196)

| Servicio | URL |
|----------|-----|
| Frontend | https://salesianos.jschmeisser.cl/ |
| Backend  | https://salesianosbackend.jschmeisser.cl/ |

## Build (resumen)

- **Método:** Dockerfile (obligatorio).
- **Contexto:** raíz del repo (`salesianos_backend`).
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

En Dokploy (backend) definir **CORS_ORIGINS** con la URL del frontend:

```
https://salesianos.jschmeisser.cl
```

(Sin barra final. Si usas www u otras variantes, añádelas separadas por comas.)

---

## Frontend (Dokploy) – variable de build

En el servicio **frontend** de Dokploy, definir en variables de entorno (build time):

- **VITE_API_BASE** = `https://salesianosbackend.jschmeisser.cl`

Así el frontend compilado apunta al API en producción. Sin esto, las peticiones irían a localhost.
