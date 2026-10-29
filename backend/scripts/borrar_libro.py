"""
borrar_libro.py — elimina un libro y todo lo que depende de él.

Borra, en este orden:
  1. Actividades de sus lecciones (leccion_id) o que citan sus fragmentos
     (fragmentos_fuente_ids), con sus resultados (FK ondelete=CASCADE). Hay que
     borrarlas a mano: la FK actividad.leccion_id es SET NULL, no CASCADE.
  2. Sus vectores en Chroma (where libro_id).
  3. El libro en Postgres, que arrastra por CASCADE fragmentos, lecciones y progreso.
  4. El PDF del volumen de libros.

No recalcula PerfilComprension (promedio acumulado por tema) ni toca los mensajes
del chat que citaron el libro (sus `referencias` quedan apuntando a páginas que ya
no existen). Pensado para revertir la subida en vivo de la demo.

Uso (DENTRO del contenedor backend, working dir /app):
    PYTHONPATH=/app python scripts/borrar_libro.py --libro-id 15 --dry-run
    PYTHONPATH=/app python scripts/borrar_libro.py --libro-id 15
"""
import argparse
import asyncio
import os

from sqlalchemy import delete, func, or_, select

from app.database import AsyncSessionLocal
from app.models.actividad import Actividad, ResultadoActividad
from app.models.fragmento import Fragmento
from app.models.leccion import Leccion
from app.models.libro import LibroTexto
from app.models.progreso_leccion import ProgresoLeccion
from app.modules.ingesta.indexer import get_collection


async def main(libro_id: int, dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        libro = (await db.execute(select(LibroTexto).where(LibroTexto.id == libro_id))).scalar_one_or_none()
        if libro is None:
            raise SystemExit(f"No existe el libro {libro_id}")

        leccion_ids = (await db.execute(select(Leccion.id).where(Leccion.libro_id == libro_id))).scalars().all()
        fragmento_ids = set((await db.execute(
            select(Fragmento.id).where(Fragmento.libro_id == libro_id))).scalars().all())
        # fragmentos_fuente_ids es JSONB: se filtra en Python (solo las que tienen fuentes).
        con_fuentes = (await db.execute(select(Actividad.id, Actividad.fragmentos_fuente_ids)
                                        .where(Actividad.fragmentos_fuente_ids.is_not(None)))).all()
        por_fragmento = {a for a, fs in con_fuentes if fragmento_ids & {int(x) for x in fs}}
        actividad_ids = set((await db.execute(select(Actividad.id).where(
            or_(Actividad.leccion_id.in_(leccion_ids), Actividad.id.in_(por_fragmento))))).scalars().all())
        resultados = (await db.execute(select(func.count()).select_from(ResultadoActividad)
                                       .where(ResultadoActividad.actividad_id.in_(actividad_ids)))).scalar()
        progreso = (await db.execute(select(func.count()).select_from(ProgresoLeccion)
                                     .where(ProgresoLeccion.leccion_id.in_(leccion_ids)))).scalar()
        coleccion = get_collection()
        vectores = len(coleccion.get(where={"libro_id": libro_id}, include=[])["ids"])

        print(f"Libro {libro_id}: «{libro.titulo}» (asignatura {libro.asignatura_id}, grado {libro.grado_id})")
        print(f"  fragmentos: {len(fragmento_ids)}  vectores en Chroma: {vectores}")
        print(f"  lecciones: {len(leccion_ids)}  progreso de estudiantes: {progreso}")
        print(f"  actividades: {len(actividad_ids)}  resultados: {resultados}")
        print(f"  PDF: {libro.archivo_pdf_path} ({'existe' if os.path.exists(libro.archivo_pdf_path) else 'no existe'})")
        if dry_run:
            print("dry-run: no se borró nada.")
            return

        await db.execute(delete(Actividad).where(Actividad.id.in_(actividad_ids)))
        coleccion.delete(where={"libro_id": libro_id})
        await db.delete(libro)
        await db.commit()
        if os.path.exists(libro.archivo_pdf_path):
            os.remove(libro.archivo_pdf_path)
        print("Borrado.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--libro-id", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true", help="muestra qué borraría, sin borrar")
    args = ap.parse_args()
    asyncio.run(main(args.libro_id, args.dry_run))
