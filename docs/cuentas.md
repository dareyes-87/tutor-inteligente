# Grados y cuentas

Las contraseñas **no** están en el repositorio: las de estudiantes vienen en `datos/estudiantes/<grado>/credenciales*.csv` y las de docentes en `datos/credenciales_docentes.csv` (ambas rutas ignoradas por git).

## Grados (IDs fijos)

| id | nombre | nivel |
|---|---|---|
| 1 | 4to Primaria | primaria |
| 2 | 5to Primaria | primaria |
| 3 | 6to Primaria | primaria |
| 5 | 7mo Básico | basico |
| 6 | 8vo Básico | basico |
| 7 | 9no Básico | basico |

El id 4 no se usa. El nombre importa: Chroma guarda el **nombre** del grado en los metadatos de cada fragmento y el RAG filtra por él, así que renombrar un grado obliga a actualizar esos metadatos (o a reconstruir Chroma).

## Estudiantes

Los 87 estudiantes reales (4to 22, 5to 19, 6to 9, 7mo 15, 8vo 12, 9no 10) se cargan con:

```bash
docker cp datos/estudiantes "$(docker compose ps -q backend)":/tmp/estudiantes
docker compose exec backend python scripts/cargar_estudiantes.py /tmp/estudiantes [--dry-run]
docker compose exec backend rm -rf /tmp/estudiantes
```

Es idempotente (actualiza por `username`) y no imprime contraseñas.

## Docentes

| usuario | grado |
|---|---|
| maria | 4to Primaria |
| docente5to | 5to Primaria |
| docente6to | 6to Primaria |
| docente7mo | 7mo Básico |
| docente8vo | 8vo Básico |
| docente9no | 9no Básico |

`maria` y el estudiante `carlos` (4to) los usan las pruebas automáticas (`backend/tests/conftest.py`).
