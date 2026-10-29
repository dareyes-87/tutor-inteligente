# Despliegue a producción — reconstrucción desde cero

> Estado: **borrador**. Falta el script de seed (paso 6); se completará cuando exista.
> Producción (Railway) se reconstruye desde cero: Postgres, Chroma y los PDFs se vuelven a cargar.
> Versiones fijadas en `preparacion-demo`: `chromadb/chroma:1.5.9` (servidor) + `chromadb==1.5.9` (cliente).

## ⚠️ Bloqueante previo: modelo de Together

Desde octubre de 2026, Together ya no ofrece en serverless `Qwen/Qwen2.5-7B-Instruct-Turbo` ni
`meta-llama/Llama-3.3-70B-Instruct-Turbo` (`400 model_not_available`). Reemplazo elegido por benchmark
(2026-10-28): **DeepSeek-V4.1-Flash** en los 3 roles, con **gpt-oss-120b** de respaldo. Si en Railway
quedó `LLM_MODEL` con el valor viejo, **borrarla o actualizarla** (pisa el valor por defecto del código).

Los modelos se eligen solo por configuración (`backend/app/config.py`), uno por rol, cada uno con
respaldos que se usan únicamente si Together responde que el modelo no está disponible:

| Rol | Variable (valor por defecto) | Respaldos (valor por defecto) |
|---|---|---|
| chat, actividades y micro-lecciones (salvo Matemáticas) | `LLM_MODEL` (`deepseek-ai/DeepSeek-V4.1-Flash`) | `LLM_MODEL_FALLBACKS` (`openai/gpt-oss-120b`) |
| Matemáticas | `LLM_MODEL_MATEMATICAS` (`deepseek-ai/DeepSeek-V4.1-Flash`) | `LLM_MODEL_MATEMATICAS_FALLBACKS` (`openai/gpt-oss-120b`) |
| ruta de lecciones (ingesta) | `LLM_MODEL_RUTA` (`deepseek-ai/DeepSeek-V4.1-Flash`) | `LLM_MODEL_RUTA_FALLBACKS` (`openai/gpt-oss-120b`) |

Respaldos = IDs separados por coma. Comprobar con `verificar_modelos.py` (ver checklist al final).

## 1. Respaldo previo (aunque se vaya a borrar todo)

Sirve para recuperar progreso real del piloto o comparar después.

```bash
# DATABASE_URL pública de Postgres (panel de Railway → Postgres → Connect)
pg_dump "$DATABASE_URL_PUBLICA" -Fc -f respaldo_prod_$(date +%F).dump
```

- Guardar también los **PDFs originales** de los libros (fuera de Railway; son la fuente para re-ingestar).
- Chroma no se respalda: se regenera completo desde los PDFs.

## 2. Variables de entorno del backend (verificar ANTES de desplegar)

Obligatorias (si faltan o tienen el valor por defecto, el arranque **falla a propósito** con un mensaje que nombra la variable):

| Variable | Nota |
|---|---|
| `SECRET_KEY` | aleatoria: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_PASSWORD` | propia; el admin se crea con ella en el primer arranque |
| `DATABASE_URL` | la inyecta Railway (también activa la validación de secretos) |
| `TOGETHER_API_KEY` | con saldo |
| `CHROMA_HOST`, `CHROMA_PORT` | host interno del servicio Chroma en Railway |
| `ALLOWED_ORIGINS` | dominio(s) del frontend web, separados por comas |

Recomendadas: `ADMIN_USERNAME`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `LLM_MODEL*` y `LLM_MODEL*_FALLBACKS` (ver bloqueante), `BOOKS_DIR` (apuntar a un volumen persistente).

Modal apagado para la demo: dejar **vacías** `MODAL_FINETUNED_URL` y `MODAL_FINETUNED_GRADOS`, y `MODAL_KEEPWARM_ENABLED=false` (con eso ningún flujo contacta a Modal). No crear variables bool/int vacías: todas las `MODAL_KEEPWARM_*` son texto.

Frontend web: `NEXT_PUBLIC_API_URL` = URL pública del backend. APK: `EXPO_PUBLIC_API_URL` en `mobile/eas.json`.

## 3. Vaciado de volúmenes

En Railway, para cada servicio con datos (Postgres, Chroma y el volumen de `BOOKS_DIR` del backend): borrar/recrear el volumen. Confirmar que el respaldo del paso 1 existe antes de hacerlo.

## 4. Arranque (migraciones + admin)

Al desplegar el backend, `start.sh` ejecuta solo:

1. `alembic upgrade head` → crea las 11 tablas (head actual `a2a93c93a5e9`).
2. `uvicorn ... --workers 1` → el `lifespan` valida los secretos, crea el admin (`ADMIN_USERNAME`/`ADMIN_PASSWORD`), precarga el modelo de embeddings (viene dentro de la imagen; no descarga de Hugging Face) y conecta a Chroma.

Verificar: `GET /health` → `{"estado_general":"ok", "postgres":"ok", "chroma":"ok"}`.

## 5. Datos base con IDs consistentes

Con la BD vacía, los IDs salen en el orden de creación. **Crear en este orden exacto** (con token de admin):

**Asignaturas** (`POST /admin/asignaturas {"nombre": ...}`) — `web/lib/constants.ts` asume estos IDs y `emoji_map.py` usa estos nombres exactos:

| Orden | Nombre exacto | ID esperado |
|---|---|---|
| 1 | `Ciencias Naturales` | 1 |
| 2 | `Matemáticas` | 2 |
| 3 (opcional) | `Comunicación y Lenguaje` | 3 |

**Grados** (`POST /admin/grados {"nombre": ...}`): el nombre debe **empezar por el número** y contener `Primaria` o `Básico` (el código deriva de ahí el nivel, el registro del tutor y el rango numérico de Matemáticas). Nombres e IDs fijos en `docs/cuentas.md` (`4to Primaria`=1 … `9no Básico`=7; el 4 no se usa): con la vía de la sección 9 vienen ya en el dump. Anotar los IDs resultantes (los usa `MODAL_FINETUNED_GRADOS` si algún día se reactiva).

Comprobar: `GET /admin/asignaturas` y `GET /admin/grados` devuelven los IDs esperados.

## 6. Usuarios (seed) — PENDIENTE

> Se completará con el script de seed. Mientras tanto, la vía disponible es:
> - Docentes: `POST /admin/docentes` (con `grado_id`).
> - Estudiantes: `POST /admin/estudiantes/importar` con CSV `nombre,apellido,grado_id` (genera usuario `inicial+apellido` y contraseña `apellido+123`, devueltos **una sola vez**: guardarlos).

## 7. Ingesta de libros

Por cada libro (token de docente o admin):

```bash
curl -X POST "$API/ingesta/libros" -H "Authorization: Bearer $TOKEN" \
  -F titulo="Ciencias Naturales 4to Primaria" -F asignatura_id=1 -F grado_id=<id> \
  -F archivo=@libro.pdf
```

- Responde **202**; el procesamiento corre en el mismo proceso del backend (OCR + embeddings + Chroma + generación de lecciones). **Subir de a uno** y esperar a que termine antes del siguiente.
- Seguir con `GET /ingesta/libros/{id}/estado` hasta `completado`; revisar `confianza_ocr_promedio` y `total_fragmentos`.
- Las lecciones se generan al final de la ingesta (usa el LLM: requiere el bloqueante resuelto). Comprobar en `GET /docente/libros` que `total_lecciones > 0`.
- Si un libro de Matemáticas tiene el OCR de `∈` como `€`: `backend/scripts/fix_ocr_math_symbols.py` y luego `backend/scripts/regenerar_lecciones.py`.

## 8. Verificación

1. `GET /health` ok.
2. `scripts/debug/ensayo_piloto.py` contra producción (credenciales solo por variables `ENSAYO_*`; crea y desactiva un estudiante temporal) → genera `docs/reporte_ensayo_piloto.md`.
3. Manual, como estudiante: login → Mi Ruta → Estudiar (micro-lección) → Practicar (5 actividades) → completar nivel; chat con una pregunta del libro y una fuera del libro (debe responder el rechazo fijo).
4. Docente: `/docente`, `/docente/libros`, `/docente/estudiantes`.
5. Una pregunta de calentamiento al chat antes de la presentación.

## 9. Vía recomendada: armar todo en local y trasladarlo (ENSAYADA en local el 2026-10-28)

En lugar de los pasos 5–7 (re-ingestar en Railway: OCR de ~1 h por libro escaneado y LLM para las
lecciones), se arma la BD completa en local —grados, cuentas reales, libros, lecciones y datos del
piloto— y se traslada. El procedimiento se ensayó completo contra un stack limpio (otro Postgres 16 y
otro Chroma 1.5.9 vacíos, compose project aparte) con estos tiempos reales:

| Paso | Tiempo medido |
|---|---|
| 1. Copia `tutor` → `tutor_prod` | 1.0 s |
| 2. Depurar la copia (`preparar_copia_prod.py`) | 2.9 s |
| 3. `pg_dump -Fc` (2.1 MB) | 0.5 s |
| 4. `pg_restore` en el Postgres de destino | 1.7 s |
| 5. Arranque del backend contra la BD restaurada | 15 s |
| 6. `reconstruir_chroma.py` (8 882 fragmentos, CPU local de 8 núcleos) | **460 s (7.7 min)** |
| 7. Verificación (`verificar_seed.py` + login + chat + mapa) | ~15 s |

En Railway el paso 6 depende de su CPU (puede tardar varias veces más); lo demás es despreciable.

1. **Copia local** (no se toca la BD de trabajo ni hace falta parar el backend; `createdb -T` exigía
   cerrar todas las conexiones a `tutor`, por eso se usa `pg_dump | psql`):
   ```bash
   docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists tutor_prod && createdb -U "$POSTGRES_USER" tutor_prod && pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | psql -q -U "$POSTGRES_USER" -d tutor_prod -v ON_ERROR_STOP=1'
   ```
2. **Depurar la copia**: `backend/scripts/preparar_copia_prod.py` conserva el admin, los docentes activos
   y los 87 estudiantes reales (aborta si no son exactamente 22/19/9/15/12/10 por grado), borra el resto
   de cuentas con sus datos —en el ensayo, 15: `carlos`, `diagtemp`, `lmartinez`, `pramirez_test`,
   `sgomez`, `test_verif_bug249` y los `verif_conceptos_*`— y pone contraseñas aleatorias nuevas al
   `admin` y a `maria`, que AÑADE a un CSV (nunca por pantalla). Se niega a correr sobre `tutor`.
   ```bash
   docker compose exec -T -e POSTGRES_DB=tutor_prod backend python scripts/preparar_copia_prod.py --credenciales /tmp/cred_prod.csv --dry-run
   docker compose exec -T -e POSTGRES_DB=tutor_prod backend python scripts/preparar_copia_prod.py --credenciales /tmp/cred_prod.csv
   docker cp "$(docker compose ps -q backend)":/tmp/cred_prod.csv datos/credenciales_produccion.csv   # ignorado por git
   docker compose exec -T backend rm /tmp/cred_prod.csv
   ```
   Si se repite el paso 1, repetir también el 2 (genera contraseñas nuevas y las añade al CSV: vale la última).
3. **Dump**:
   ```bash
   docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc tutor_prod' > tutor_prod.dump
   ```
4. **Restore** en el Postgres de Railway. **Pausar antes el servicio backend** (en el ensayo se paró:
   así nadie escribe durante el `--clean`). El Postgres de destino puede tener ya el esquema migrado y
   el admin creado por el arranque: `--clean --if-exists` lo reemplaza sin errores (comprobado).
   ```bash
   docker run --rm -v "$PWD":/w postgres:16 pg_restore --clean --if-exists --no-owner --no-acl -d "$DATABASE_URL_PUBLICA" /w/tutor_prod.dump
   ```
   Restaura `alembic_version` (head `a2a93c93a5e9`), las secuencias y los IDs (el mapeo fila→estudiante
   de `datos/mapeo_estudiantes_csv.csv` sigue valiendo).

   **Verificar antes la versión del Postgres de Railway** (local: 16.14):
   ```bash
   docker run --rm postgres:16 psql "$DATABASE_URL_PUBLICA" -Atc "show server_version;"
   ```
   - **16.x**: seguir tal cual.
   - **17 o mayor**: el `pg_restore` debe ser **de la versión del servidor**: misma orden con la imagen `postgres:<versión>`.
   - **15 o menor**: un dump `-Fc` de la 16 no se restaura en una versión menor. Opciones: (a) recomendada, crear en Railway un Postgres 16 (imagen `postgres:16`) y apuntar `DATABASE_URL` del backend a él; o (b) volcar en texto plano (`pg_dump --no-owner --no-acl -Fp`) y aplicarlo con `psql` (no probado).
5. **Reanudar el backend** de Railway (aplica `alembic upgrade head`, que no hace nada: ya está en head).
6. **Reconstruir Chroma desde Postgres** (sin OCR ni LLM), en la shell del backend de producción:
   ```bash
   python scripts/reconstruir_chroma.py            # aborta si la colección ya tiene vectores
   python scripts/reconstruir_chroma.py --vaciar   # si el Chroma de producción tiene datos viejos
   ```
   Escribe por fragmento `id = chunk_id_vectordb`, `document = contenido_texto` y los metadatos de
   `chunking.py` (`grado`/`asignatura` por NOMBRE, `method` = "digital" si la confianza es 100), con los
   embeddings recalculados. Termina con error si `count()` ≠ nº de fragmentos. **Ensayo: la colección
   reconstruida es idéntica a la local** (8 882 IDs, documentos y metadatos iguales; coseno de los
   embeddings 1.0 en todos).
7. **Verificación** (todo OK en el ensayo):
   - `GET /health` → ok.
   - Login de una cuenta real (jgarcia: 200) y de admin/maria con las contraseñas NUEVAS (200; la de
     desarrollo da 401).
   - Una pregunta del chat con cita de página (jgarcia, Matemáticas: "producto notable" → cita la p. 8).
   - Mapa de calor de `docente9no`: 11 lecciones con celdas en cada asignatura.
   - `verificar_seed.py` contra la BD restaurada: 72/72, medias de la Tabla 14 y 59/7/6 OK.
     ```bash
     docker cp datos/datos_simulados_cap5.csv <backend>:/tmp/ && docker cp datos/mapeo_estudiantes_csv.csv <backend>:/tmp/mapeo.csv
     python scripts/verificar_seed.py --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv
     ```
     (en Railway hay que subir esos dos CSV a la shell del backend, o correrlo desde local con
     `POSTGRES_*`/`DATABASE_URL` apuntando a la BD pública; ojo: con `DATABASE_URL` definida se activan
     los chequeos de configuración de producción.)
8. **PDFs**: no hacen falta para el RAG; `libro_texto.archivo_pdf_path` apunta a archivos que no existen
   en el volumen de producción (solo importa para re-ingestar).

## Checklist del día de la presentación

1. **Modelos LLM disponibles** (cuesta < $0.01; no toca la BD):

   ```bash
   # desde la raíz del repo, con el .env que tenga la misma configuración que producción
   python3 backend/scripts/verificar_modelos.py
   # o dentro del contenedor
   docker compose exec backend python scripts/verificar_modelos.py
   ```

   Imprime por rol (chat / matematicas / ruta) si cada modelo principal y de respaldo está en el
   catálogo de Together, si responde, su latencia y su precio. Termina con código **1** si un modelo
   **principal** no responde (un respaldo caído solo se advierte). Si falla un principal: cambiar
   la variable `LLM_MODEL*` correspondiente en Railway por su primer respaldo que diga OK.
2. Saldo de Together suficiente (panel de Together → Billing).
3. `GET /health` → `estado_general: ok`.
4. Una pregunta de calentamiento al chat y una micro-lección (precarga y confirma el modelo real).
