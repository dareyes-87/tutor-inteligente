# Subida de un libro en vivo durante la demo

**Debe ser el ÚLTIMO paso de la demo.** Al terminar de indexarse, el libro nuevo pasa a ser el
más reciente de su grado y asignatura: el mapa de calor del docente (`/docente/diagnostico`) lo
elige por defecto (comprobado: el de `docente9no` pasó del libro del grado al de la demo, sin
datos), y el chat de los estudiantes de ese grado mezcla sus fragmentos con los del libro del
grado (el RAG filtra por grado y asignatura, no por libro). La ruta del estudiante (`mi-libro`)
no cambió en la prueba. Todo lo que se muestre después se vería distinto.

## PDF preparado

`datos/demo/Matematica_7mo_Unidad1_demo.pdf` (ignorado por git: material del MINEDUC): 16
páginas digitales del libro 1B de Matemática (pp. 7–22, Unidad 1, "Clase 1" en adelante).

Medido en local (2026-10-28, con la ingesta en un proceso hijo):

| Paso | Tiempo |
|---|---|
| Subida (respuesta 202) | < 0.1 s |
| Indexado (`estado: completado`, 69 fragmentos) | ~16 s |
| Con lecciones generadas (4 lecciones, LLM) | ~32 s |

Durante la ingesta, `/health` y el chat siguen respondiendo (medido: < 2 s).

Subirlo desde `/docente/libros` con **Matemáticas** y el grado del docente con el que se hace
la demo (p. ej. `docente7mo`, 7mo Básico).

## Revertirlo después de la demo

Dentro del contenedor del backend (en Railway: shell del servicio backend):

```bash
# 1. Ver el id del libro subido (el más reciente)
PYTHONPATH=/app python -c "
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.libro import LibroTexto
async def m():
    async with AsyncSessionLocal() as db:
        for l in (await db.execute(select(LibroTexto).order_by(LibroTexto.id.desc()).limit(3))).scalars():
            print(l.id, l.titulo, l.grado_id, l.fecha_subida)
asyncio.run(m())"

# 2. Ver qué se borraría y borrarlo
PYTHONPATH=/app python scripts/borrar_libro.py --libro-id N --dry-run
PYTHONPATH=/app python scripts/borrar_libro.py --libro-id N
```

`borrar_libro.py` elimina los fragmentos (Postgres y Chroma), las lecciones con su progreso,
las actividades de esas lecciones o que citan sus fragmentos con sus resultados, y el PDF. No
recalcula el perfil de comprensión ni toca los mensajes del chat que hayan citado el libro: si
en la demo alguien practicó o preguntó sobre el libro nuevo, esos rastros quedan (por eso,
también, conviene que sea lo último).
