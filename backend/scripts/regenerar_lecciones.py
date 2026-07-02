"""
regenerar_lecciones.py — borra y regenera la ruta de lecciones de un libro.

Las lecciones (nombres/segmentos) y sus micro-lecciones se arman a partir de los
fragmentos del libro. Como no existe un "actualizar lección", la única forma de que
tomen el texto ya corregido (p. ej. tras `fix_ocr_math_symbols.py`) es borrarlas y
regenerarlas. Este script hace eso de forma SEGURA:

  1. Cuenta el progreso de estudiantes en las lecciones del libro.
  2. Si hay CUALQUIER progreso (>0 filas) y NO se pasó --forzar, se NIEGA a borrar:
     imprime cuántas filas / cuántos estudiantes y termina sin tocar nada.
  3. Solo si no hay progreso (o con --forzar explícito) borra las lecciones (lo que
     arrastra su progreso por CASCADE) y las regenera desde los fragmentos actuales.

No toca fragmentos, ni Chroma, ni ningún otro módulo. La única tabla ligada a
`leccion` es `progreso_leccion` (FK ondelete=CASCADE); no hay tarjetas/quizzes
persistidos (las micro-lecciones se generan on-demand). No requiere migración.

Uso (DENTRO del contenedor backend, working dir /app):
    PYTHONPATH=/app python scripts/regenerar_lecciones.py --libro-id 2
    PYTHONPATH=/app python scripts/regenerar_lecciones.py --libro-id 2 --forzar
"""
import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.database import AsyncSessionLocal
from app.models.leccion import Leccion
from app.models.progreso_leccion import ProgresoLeccion
from app.modules.lecciones.generator import generar_lecciones_desde_libro


async def main(libro_id: int, forzar: bool) -> None:
    async with AsyncSessionLocal() as db:
        # IDs de las lecciones actuales de este libro.
        leccion_ids = (
            await db.execute(select(Leccion.id).where(Leccion.libro_id == libro_id))
        ).scalars().all()

        print(f"\n=== regenerar_lecciones · libro_id={libro_id} ===")
        print(f"Lecciones actuales del libro: {len(leccion_ids)}")

        # 1. Contar progreso de estudiantes en esas lecciones.
        if leccion_ids:
            total_progreso = (
                await db.execute(
                    select(func.count(ProgresoLeccion.id)).where(
                        ProgresoLeccion.leccion_id.in_(leccion_ids)
                    )
                )
            ).scalar_one()
            estudiantes_con_progreso = (
                await db.execute(
                    select(func.count(func.distinct(ProgresoLeccion.estudiante_id))).where(
                        ProgresoLeccion.leccion_id.in_(leccion_ids)
                    )
                )
            ).scalar_one()
        else:
            total_progreso = 0
            estudiantes_con_progreso = 0

        print(f"Progreso de estudiantes en estas lecciones: {total_progreso} fila(s), "
              f"{estudiantes_con_progreso} estudiante(s)")

        # 2. Candado de seguridad (por defecto obligatorio).
        if total_progreso > 0 and not forzar:
            # Desglose por estado para que se vea si es progreso real o placeholders.
            desglose = (
                await db.execute(
                    select(ProgresoLeccion.estado, func.count())
                    .where(ProgresoLeccion.leccion_id.in_(leccion_ids))
                    .group_by(ProgresoLeccion.estado)
                )
            ).all()
            print("\n🛑 ABORTADO: hay progreso de estudiantes en las lecciones de este libro.")
            print("   Desglose por estado:")
            for estado, n in desglose:
                nombre_estado = estado.value if hasattr(estado, "value") else estado
                print(f"     - {nombre_estado}: {n}")
            print("\n   No se borró nada. Si de verdad quieres regenerar y PERDER ese")
            print("   progreso, vuelve a correr el comando agregando --forzar.\n")
            return

        # 3. Borrar (progreso primero para reportar, luego lecciones) y regenerar.
        if forzar and total_progreso > 0:
            print("⚠️  --forzar activo: se borrará el progreso de estudiantes indicado arriba.")

        prog_borrado = (
            await db.execute(
                delete(ProgresoLeccion).where(ProgresoLeccion.leccion_id.in_(leccion_ids))
            )
        ).rowcount if leccion_ids else 0
        lec_borradas = (
            await db.execute(delete(Leccion).where(Leccion.libro_id == libro_id))
        ).rowcount
        await db.commit()
        print(f"\nBorradas: {prog_borrado} fila(s) de progreso, {lec_borradas} lección(es).")

        print("Regenerando lecciones desde los fragmentos (LLM Llama-70B)...")
        creadas = await generar_lecciones_desde_libro(libro_id, db)
        print(f"Regeneradas: {len(creadas)} lección(es).")

        # 5. Muestra de la primera lección regenerada (verificación rápida).
        primera = (
            await db.execute(
                select(Leccion).where(Leccion.libro_id == libro_id).order_by(Leccion.orden).limit(1)
            )
        ).scalar_one_or_none()
        if primera:
            print("\n=== Muestra de la primera lección regenerada ===")
            print(f"  orden:       {primera.orden}")
            print(f"  nombre:      {primera.nombre}")
            print(f"  descripción: {primera.descripcion}")
            print(f"  páginas:     {primera.paginas}")
            print(f"  tema_clave:  {primera.tema_clave}")
        print("\nNOTA: el contenido con notación (∈) vive en la MICRO-lección, que se")
        print("genera on-demand. Verifícalo pidiendo la micro-lección de la lección de")
        print("Conjuntos vía la API (GET /lecciones/{id}/micro-leccion?nivel=1).\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Borra y regenera las lecciones de un libro (con candado de progreso).")
    parser.add_argument("--libro-id", type=int, required=True, help="ID del libro cuyas lecciones regenerar")
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Regenerar AUNQUE haya progreso de estudiantes (lo borra). Por defecto NO.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.libro_id, args.forzar))
