# Tutor Inteligente — Backend (Sprint 0)

Cimientos del sistema: FastAPI + PostgreSQL 16 + ChromaDB, todo en Docker,
con conexión de prueba a Together AI (modelo Qwen base).

## Requisitos previos (Fedora 44)

Instala Docker una sola vez:

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

Cierra sesión y vuelve a entrar (o reinicia) para que tu usuario quede en el
grupo `docker`. Verifica:

```bash
docker --version
docker compose version
```

## Puesta en marcha

1. Copia el archivo de variables de entorno y edítalo:

   ```bash
   cp .env.example .env
   ```

   Abre `.env` y cambia:
   - `POSTGRES_PASSWORD` por una contraseña tuya.
   - `TOGETHER_API_KEY` por tu clave de https://api.together.ai
     (regístrate, ve a Settings → API Keys, y carga algo de saldo).

2. Levanta todo:

   ```bash
   docker compose up --build
   ```

   La primera vez tarda unos minutos (descarga imágenes e instala dependencias).

3. Comprueba que funciona, abriendo en el navegador:
   - http://localhost:8000/health  → debe mostrar `estado_general: ok`
   - http://localhost:8000/llm/hello → debe mostrar un saludo generado por Qwen
   - http://localhost:8000/docs → documentación interactiva de la API

Para detener todo: `Ctrl+C` y luego `docker compose down`
(añade `-v` solo si quieres borrar también los datos).

## Comandos útiles

```bash
docker compose up               # levantar (sin reconstruir)
docker compose up --build       # levantar reconstruyendo
docker compose down             # detener
docker compose logs -f backend  # ver logs del backend en vivo
docker compose exec backend bash  # entrar al contenedor del backend
```

## Migraciones de base de datos (Alembic)

Alembic ya está configurado. Todavía no hay tablas (llegan en el Sprint 1).
Para verificar que está bien cableado:

```bash
docker compose exec backend alembic current
```

No debe dar error (no imprime nada porque aún no hay migraciones).

En el Sprint 1, tras crear los modelos, generarás la primera migración con:

```bash
docker compose exec backend alembic revision --autogenerate -m "tablas iniciales"
docker compose exec backend alembic upgrade head
```

## Estructura

```
backend/
  app/
    main.py        # API y endpoints /health y /llm/hello
    config.py      # configuración desde .env
    database.py    # conexión a PostgreSQL
    llm/client.py  # cliente Together AI (modelo en .env)
    models/        # tablas (Sprint 1)
  alembic/         # migraciones
  Dockerfile
  requirements.txt
docker-compose.yml
.env.example
```

## Subir a GitHub

```bash
git init
git add .
git commit -m "Sprint 0: cimientos (FastAPI + Postgres + ChromaDB + Together AI)"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/tutor-inteligente.git
git push -u origin main
```

El `.gitignore` ya evita que tu `.env` (con la API key) se suba. Verifícalo.
