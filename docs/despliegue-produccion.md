# Despliegue a producción — runbook del 2026-11-04

Traslado de la BD armada en local (cuentas reales, libros, lecciones y datos del piloto) a Railway,
en orden. Cada bloque se copia tal cual. **Nunca pegues secretos en un comando**: las URL y
contraseñas se leen con `read -rs` (no quedan en el historial).

## Estado de Railway (verificado hoy)

| Servicio | Root | Build | Notas |
|---|---|---|---|
| `tutor-inteligente` (backend) | `/backend` | Dockerfile | puerto 8000, healthcheck `/health` |
| `just-blessing` (web) | `/web` | Railpack, Node 22 | puerto 8080 |
| `chroma` | `/chroma` | Dockerfile (`chromadb/chroma:1.5.9`) | volumen en `/data`, `PERSIST_DIRECTORY=/data` |
| Postgres | — | — | **18.6** |

- Skipped Builds activado en los tres servicios con código; Watch Paths por servicio.
- Variables del backend: `ADMIN_PASSWORD` existe (temporal; se sincroniza en el paso e).
  `MODAL_FINETUNED_URL` y `MODAL_FINETUNED_GRADOS` vacías (Modal apagado). No hay `LLM_MODEL*` ni
  `ACCESS_TOKEN_EXPIRE_MINUTES`: valen los del código (DeepSeek-V4.1-Flash con gpt-oss-120b de
  respaldo; 720 min).
- `pg_dump`/`pg_restore` contra Railway: **siempre con la imagen `postgres:18`**. `pg_restore` 18
  restaura sin problema un dump `-Fc` del Postgres local 16.
- Fedora + SELinux: montar una carpeta en un contenedor exige `:Z` y `--user $(id -u):$(id -g)`
  (sin eso: `Permission denied`). Carpeta dedicada `~/respaldos-railway`, **nunca `$HOME`**.
- Respaldo previo de producción ya hecho: `~/respaldos-railway/respaldo_prod_2026-11-04.dump`
  (615 KB, `postgres:18`; Alembic en `4858c23833e7`, una migración por detrás del head).

Variables de sesión que usan los pasos (pegar cuando lo pida; `<URL_PUBLICA>` = Railway → Postgres →
Connect → URL pública, `postgresql://…proxy.rlwy.net:…/railway`):

```bash
cd ~/tutor-inteligente
read -rsp "URL pública de Postgres: " URL_PUBLICA; echo; export URL_PUBLICA
API=https://tutor-inteligente-production.up.railway.app
```

## a. Pre-merge (en local, rama `preparacion-demo`)

```bash
git checkout preparacion-demo && git status --short   # solo archivos sin seguimiento ajenos
docker compose up -d
docker cp datos/datos_simulados_cap5.csv "$(docker compose ps -q backend)":/tmp/
docker cp datos/mapeo_estudiantes_csv.csv "$(docker compose ps -q backend)":/tmp/mapeo.csv

docker compose exec -T backend pytest tests/ -q
docker compose exec -T backend python scripts/verificar_seed.py --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv
docker compose exec -T backend python scripts/verificar_consistencia.py
docker compose exec -T backend python scripts/limpiar_pruebas.py --mapeo /tmp/mapeo.csv   # dry-run (tarda ~15 min)
```

Esperado:
- pytest: todo verde.
- `verificar_seed.py`: 72/72, medias de la Tabla 14 OK, dominio final 59/7/6, mapa de calor OK en
  los 12 grado×asignatura, exit 0. En "Uso posterior al piloto" solo aparecen las 6 cuentas de
  `CUENTAS_DEMO` (`backend/scripts/cuentas_demo.py`) marcadas `demo`; cualquier otra es FALLA.
- `verificar_consistencia.py`: `✅ Sin discrepancias`.
- `limpiar_pruebas.py` (dry-run): las 6 cuentas de demo "se conservan", `Comprobación OK` y
  `dry-run: no se guardó nada`.

Si algo falla, **no seguir**.

## b. Merge `preparacion-demo` → `main` (fast-forward)

```bash
git checkout main && git pull --ff-only
git merge --ff-only preparacion-demo     # si se niega, main tiene commits nuevos: parar y revisar
git push origin main
git checkout preparacion-demo
```

Qué esperar en Railway:
- **Un build por servicio** (backend, web y chroma; con Skipped Builds, uno sin cambios en sus
  Watch Paths se salta).
- Backend: en los logs del deploy, `Running upgrade 4858c23833e7 -> a2a93c93a5e9` (la migración
  que le falta a producción) y luego uvicorn. **Esperar a que quede Active con el healthcheck en
  verde** antes de seguir. Si el build o el healthcheck fallan, Railway mantiene el deployment
  anterior sirviendo (ver h).
- `curl -s $API/health` → `{"estado_general":"ok", …, "postgres":"ok", "chroma":"ok"}`.

## c. Traslado: preparar la copia y el dump (en local)

1. Limpiar el uso de prueba posterior al piloto (salvo cuentas de demo) y confirmar:
   ```bash
   docker compose exec -T backend python scripts/limpiar_pruebas.py --mapeo /tmp/mapeo.csv --aplicar
   docker compose exec -T backend python scripts/verificar_seed.py --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv
   ```
2. Copia `tutor` → `tutor_prod` (no hace falta parar el backend local):
   ```bash
   docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists tutor_prod && createdb -U "$POSTGRES_USER" tutor_prod && pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | psql -q -U "$POSTGRES_USER" -d tutor_prod -v ON_ERROR_STOP=1'
   ```
3. Depurar la copia: conserva admin, docentes activos y los 87 estudiantes reales (aborta si no son
   22/19/9/15/12/10 por grado), borra las demás cuentas con sus datos y pone contraseñas nuevas a
   `admin` y `maria`, que **añade** al CSV (nunca por pantalla). Se niega a correr sobre `tutor` o
   con `DATABASE_URL` definida.
   ```bash
   docker compose exec -T -e POSTGRES_DB=tutor_prod backend python scripts/preparar_copia_prod.py --credenciales /tmp/cred_prod.csv --dry-run
   docker compose exec -T -e POSTGRES_DB=tutor_prod backend python scripts/preparar_copia_prod.py --credenciales /tmp/cred_prod.csv
   docker compose exec -T backend cat /tmp/cred_prod.csv | tail -n +2 >> datos/credenciales_produccion.csv   # ignorado por git
   docker compose exec -T backend rm /tmp/cred_prod.csv
   chmod 600 datos/credenciales_produccion.csv
   ```
   El CSV acumula filas: **vale la última de cada usuario**. Si se repite el paso 2, repetir el 3.
4. Dump de `tutor_prod`:
   ```bash
   mkdir -p ~/respaldos-railway
   docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc tutor_prod' > ~/respaldos-railway/tutor_prod.dump
   ls -la ~/respaldos-railway/
   ```

## d. Restore en Railway

1. **Pausar el backend** (`tutor-inteligente`) para que nadie escriba durante el `--clean`:
   Deployments → menú ⋮ del deployment activo → la opción que lo detiene (Stop / Remove). El servicio
   y sus variables no se tocan.
2. Comprobar el servidor y restaurar (desde `~/respaldos-railway`, con `:Z` y `--user`):
   ```bash
   docker run --rm postgres:18 psql "$URL_PUBLICA" -Atc "show server_version"     # 18.6
   docker run --rm -v ~/respaldos-railway:/w:Z --user $(id -u):$(id -g) postgres:18 \
     pg_restore --clean --if-exists --no-owner --no-acl -d "$URL_PUBLICA" /w/tutor_prod.dump
   docker run --rm postgres:18 psql "$URL_PUBLICA" -Atc "select version_num from alembic_version; select rol, count(*) from usuario group by rol order by rol; select count(*) from fragmento"
   ```
   Esperado: `pg_restore` sin errores; `a2a93c93a5e9`; 1 administrador, los docentes activos y 87
   estudiantes; el mismo nº de fragmentos que en local. Restaura también las secuencias y los IDs
   (`datos/mapeo_estudiantes_csv.csv` sigue valiendo).
3. **Reanudar el backend** (Redeploy del mismo deployment; con Skipped Builds no reconstruye).
   `alembic upgrade head` no hace nada (ya está en head) y el admin no se crea porque ya existe.
   Esperar Active + healthcheck verde.

## e. Sincronizar `ADMIN_PASSWORD`

`app/seed.py` crea el admin **solo si no existe**. Tras el restore el admin ya existe con la
contraseña que generó `preparar_copia_prod.py`, así que **la que vale para entrar es la del CSV**,
no la de la variable. Igual se sincroniza para que la variable no mienta (y porque el arranque exige
que no tenga el valor por defecto):

```bash
awk -F, '$1=="admin"{p=$2} END{print p}' datos/credenciales_produccion.csv   # última del admin
```

Copiarla en Railway → `tutor-inteligente` → Variables → `ADMIN_PASSWORD` → Deploy. Con Skipped
Builds solo reinicia el servicio (sin build). Esperar Active.

## f. Reconstruir Chroma desde Postgres

En la shell del backend de producción (`railway ssh --service tutor-inteligente`, o la consola del
panel). Recalcula los embeddings de todos los fragmentos sin OCR ni LLM (local: 460 s con 8 núcleos;
en Railway puede tardar varias veces más). Con `nohup` sobrevive a que se corte la shell:

```bash
cd /app
nohup python scripts/reconstruir_chroma.py --vaciar > /tmp/chroma.log 2>&1 &
tail -f /tmp/chroma.log      # termina con "Chroma: N vectores (Postgres: N)"; Ctrl+C solo corta el tail
python -c "from app.modules.ingesta.indexer import get_collection; print(get_collection().count())"
```

Si los conteos no coinciden, el script termina con `ERROR` (no seguir). Después:

1. Railway → `chroma` → Deployments → ⋮ → **Restart** (no Redeploy).
2. Repetir el `count()` de arriba: debe dar el mismo N (el volumen `/data` persiste).
3. Una pregunta del chat (paso g) que cite página confirma que el RAG lee esos vectores.

## g. Verificación

Contraseñas: admin y maria → última fila de `datos/credenciales_produccion.csv`; jgarcia y ecabrera
→ `datos/estudiantes/<grado>/credenciales*.csv`.

```bash
curl -s $API/health                                       # estado_general ok, postgres ok, chroma ok
for u in admin maria jgarcia ecabrera; do
  read -rsp "contraseña de $u: " P; echo
  printf '%s → ' $u; curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/auth/login \
    --data-urlencode "username=$u" --data-urlencode "password=$P"
done; unset P                                             # 200 los cuatro
```

En la web de producción:
- **Chat con cita de página**: jgarcia, Matemáticas, "¿qué es un producto notable?" → responde
  con cita de página del libro (en el ensayo, p. 8).
- **Mapa de calor**: entrar como `docente9no` → Diagnóstico → cada asignatura con celdas en ≥ 6
  lecciones (en el ensayo, 11).

Scripts:
```bash
# En la shell del backend de producción (usa su DATABASE_URL y SECRET_KEY; firma los tokens
# internamente, sin contraseñas). Crea filas de progreso_leccion que falten, como abrir la ruta.
python scripts/verificar_consistencia.py --base-url https://tutor-inteligente-production.up.railway.app
#  → "✅ Sin discrepancias (87 estudiantes)."

# En local, contra la BD de producción (los CSV están en el contenedor local):
docker compose exec -T -e DATABASE_URL="$URL_PUBLICA" backend python scripts/verificar_seed.py \
  --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv
#  → mismo resultado que en c.1 (72/72, Tabla 14, 59/7/6, mapa OK, uso posterior solo en demo).
```

Al terminar: `unset URL_PUBLICA`.

## h. Rollback

**Build nuevo falla (paso b)**: un build o healthcheck fallido no reemplaza al deployment activo;
producción sigue con el anterior. Arreglar en `preparacion-demo`, repetir a y b. Para volver a un
deployment anterior ya reemplazado: servicio → Deployments → deployment anterior → ⋮ →
**Rollback** (en cada servicio afectado). Ojo: el próximo push a `main` que toque sus Watch Paths
vuelve a desplegar `main`.

**Restaurar la BD previa** (`respaldo_prod_2026-11-04.dump`):
1. Pausar el backend (como en d.1).
2. Restaurar:
   ```bash
   docker run --rm -v ~/respaldos-railway:/w:Z --user $(id -u):$(id -g) postgres:18 \
     pg_restore --clean --if-exists --no-owner --no-acl -d "$URL_PUBLICA" /w/respaldo_prod_2026-11-04.dump
   ```
   Deja Alembic en `4858c23833e7`. Si el backend sigue con el código nuevo, al reanudar
   `start.sh` vuelve a aplicar `a2a93c93a5e9` (solo añade columnas). Si además se hace Rollback del
   código, el esquema coincide con el código viejo.
3. Reanudar el backend y, como Chroma tiene ya los vectores de la BD nueva, rehacerlo desde la BD
   restaurada: `python scripts/reconstruir_chroma.py --vaciar` (paso f).
4. Las contraseñas vuelven a ser las del respaldo (las de antes de hoy); `ADMIN_PASSWORD` no las
   cambia (el admin ya existe).

## Antes de la presentación

1. `docker compose exec backend python scripts/verificar_modelos.py` (con la misma configuración
   LLM que producción; < $0.01). Sale con 1 si un modelo principal no responde: en ese caso crear
   en Railway la `LLM_MODEL*` del rol con su primer respaldo OK.
2. Saldo de Together suficiente.
3. `GET /health` ok, una pregunta de calentamiento al chat y una micro-lección.
