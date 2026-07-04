#!/bin/bash
set -e
echo "=== Ejecutando migraciones Alembic ==="
alembic upgrade head
echo "=== Migraciones completadas. Iniciando servidor ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
