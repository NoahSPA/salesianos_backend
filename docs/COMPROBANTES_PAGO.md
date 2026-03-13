# Comprobantes de pago – opciones para subir archivos

## Objetivo
Guardar una imagen o PDF del comprobante asociado a cada pago en Tesorería, para que el tesorero pueda validar con la prueba visual.

## Opciones

### 1. **MongoDB GridFS** (recomendada para empezar)
- **Qué es:** Almacenamiento de archivos dentro de MongoDB (usa 2 colecciones: `fs.files` y `fs.chunks`).
- **Ventajas:** Sin servicios extra, ya usas MongoDB Atlas; implementación sencilla; backup junto con la base de datos.
- **Límites:** Documento máximo 16 MB por archivo (suficiente para fotos/PDFs de comprobantes). Si en el futuro suben muchos o muy grandes, se puede migrar a S3.
- **Implementación:** Endpoint `POST /payments/{id}/receipt` con `multipart/form-data` (file), guardar en GridFS, guardar `file_id` en el documento del pago.

### 2. **Almacenamiento S3-compatible (producción a largo plazo)**
- **Servicios:** AWS S3, **Cloudflare R2** (free tier generoso), MinIO (self-hosted), Backblaze B2.
- **Ventajas:** Escalable, barato, estándar; URLs públicas o firmadas para ver el comprobante.
- **Desventajas:** Configuración extra (bucket, credenciales, variable de entorno).
- **Implementación:** Subir el archivo al bucket, guardar la URL (o la key) en el pago. Librería: `boto3` (S3) o `httpx` para la API de R2/S3.

### 3. **Sistema de archivos local**
- **Qué es:** Guardar archivos en una carpeta del servidor (ej. `uploads/receipts/`).
- **Ventajas:** Muy simple, sin dependencias externas.
- **Desventajas:** En Docker hay que usar un volumen; si hay varias instancias, no se comparte el disco; backups hay que hacerlos aparte.
- **Implementación:** FastAPI recibe el file, lo escribe en disco, guarda la ruta relativa o un identificador en el pago; endpoint estático para servir el archivo.

---

## Recomendación

1. **Corto plazo / MVP:** **GridFS**.  
   - No añades servicios ni env vars nuevas.  
   - Un endpoint para subir y otro para descargar/ver el comprobante.  
   - En el modelo de pago: `receipt_file_id: str | None` (ObjectId de GridFS).

2. **Si más adelante crece el volumen o quieres CDN/URLs públicas:**  
   Migrar a **Cloudflare R2** (o S3): mismo flujo de “subir → guardar URL en el pago”, cambiando solo la capa de almacenamiento.

## Cambios sugeridos en el modelo

- **Backend:** En el documento `payments`: añadir campo opcional `receipt_file_id` (GridFS) o `receipt_url` (S3).
- **API:**  
  - `POST /payments/{payment_id}/receipt`: subir archivo (image/* o application/pdf), guardar en GridFS, actualizar el pago.  
  - `GET /payments/{payment_id}/receipt`: devolver el archivo (stream) o redirección a URL si usas S3.
- **Frontend (Treasury):** En el detalle/lista de pagos: botón “Subir comprobante” y enlace/thumbnail para “Ver comprobante” cuando exista.

Si quieres, el siguiente paso puede ser implementar la opción con **GridFS** (esquemas, router, servicio y uso en el frontend).
