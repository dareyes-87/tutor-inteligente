"""
Verificación puntual de dos fixes (emoji curado + ejercicios tratados como
teoría) para la lección 249 "Conjuntos y operaciones" (Matemáticas, págs 1-5),
que en producción mostró el bug: emoji 🧬 en un concepto de conjuntos, y
actividades basadas en el ejercicio "¡Mesa lista!" en vez de la teoría.

Uso:
    docker compose exec backend python3 scripts/debug/verificar_fix_emoji_ejercicios.py

Script de un solo uso para esta verificación; no forma parte de la app.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.models.actividad import TipoActividad
from app.modules.lecciones.service import generar_micro_leccion
from app.modules.actividades.service import crear_actividad

LECCION_ID = 249  # "Conjuntos y operaciones", Matemáticas 4to, páginas 1-5


def _revisar_mesa_lista(texto: str) -> None:
    t = texto.lower().replace(" ", "")
    if "mesalista" in t or ("a,b,c" in t and "w,x,y,z" in t):
        print("   !!! PARECE BASARSE EN EL EJERCICIO 'MESA LISTA' !!!")


async def main():
    async with AsyncSessionLocal() as db:
        estudiante = (
            await db.execute(select(Usuario).where(Usuario.grado_id == 1).limit(1))
        ).scalars().first()
        print(f"Estudiante de prueba: {estudiante.username} (grado_id={estudiante.grado_id})")

        print("\n=== MICRO-LECCIÓN (nivel 1) ===")
        micro = await generar_micro_leccion(LECCION_ID, db, nivel=1)
        print(f"Título: {micro.titulo}")
        for t in micro.tarjetas:
            etiqueta = t.titulo_concepto or t.tipo
            print(f"  [{t.emoji}] {etiqueta}: {(t.contenido or '')[:90]!r}")
            _revisar_mesa_lista(t.contenido or "")

        print("\n=== ACTIVIDAD (fragment_ids de la micro-lección) ===")
        actividad = await crear_actividad(
            db,
            asignatura_id=2,
            tipo=TipoActividad.opcion_multiple,
            estudiante=estudiante,
            leccion_id=LECCION_ID,
            fragment_ids=micro.fragment_ids,
        )
        if actividad is None:
            print("No se generó actividad (None).")
        else:
            print(f"Tema: {actividad.tema}")
            print(f"Contenido: {actividad.contenido}")
            print(f"Respuesta correcta: {actividad.respuesta_correcta}")
            _revisar_mesa_lista(str(actividad.contenido))

        print("\n=== ACTIVIDADES 'Relación de pertenencia y subconjuntos' (rango completo pág 1-5, incluye '¡Mesa lista!') ===")
        for tipo in [TipoActividad.opcion_multiple, TipoActividad.verdadero_falso, TipoActividad.completar]:
            act = await crear_actividad(
                db,
                asignatura_id=2,
                tipo=tipo,
                estudiante=estudiante,
                tema="Relación de pertenencia y subconjuntos",
                leccion_id=LECCION_ID,
            )
            if act is None:
                print(f"[{tipo.value}] No se generó actividad (None).")
                continue
            print(f"[{tipo.value}] contenido={act.contenido}")
            _revisar_mesa_lista(str(act.contenido))


if __name__ == "__main__":
    asyncio.run(main())
