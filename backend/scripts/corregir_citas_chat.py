"""
corregir_citas_chat.py — cuenta y corrige citas de página inválidas en respuestas ya guardadas del chat.

Hasta el commit que añadió _quitar_citas_invalidas, si el LLM citaba una página que no estaba
entre los fragmentos recuperados, la cita quedaba en el texto y se borraban las referencias y el
pie "📖 Basado en tu libro…". Este script, SIN LLM, por cada respuesta del asistente:
  1. recalcula los fragmentos de su pregunta con chat.service.recuperar_contexto (determinístico
     para el mismo índice; comprueba que coincida con las referencias guardadas cuando las hay);
  2. cuenta las que citan alguna página fuera de esos fragmentos (todas las asignaturas);
  3. con --aplicar, y solo en la ventana indicada, quita esas citas con _quitar_citas_invalidas y,
     si se habían borrado las referencias por la cita inválida, restaura referencias y pie.

Uso (dentro del contenedor backend):
    python scripts/corregir_citas_chat.py                         # solo cuenta
    python scripts/corregir_citas_chat.py --aplicar --desde 2026-09-01 --hasta 2026-10-01
"""
import argparse
import asyncio
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.asignatura import Asignatura  # noqa: E402
from app.models.conversacion import Conversacion  # noqa: E402
from app.models.grado import Grado  # noqa: E402
from app.models.mensaje import Mensaje, RolMensaje  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.modules.chat.service import (  # noqa: E402
    RESPUESTA_FUERA_DE_CONTEXTO, RESPUESTA_LLM_NO_DISPONIBLE, _es_rechazo, _paginas_citadas,
    _quitar_citas_invalidas, _referencia_paginas, _sin_footer_pagina, recuperar_contexto,
)

ZONA = ZoneInfo("America/Guatemala")


async def main(aplicar: bool, desde: date | None, hasta: date | None, ejemplos: int) -> None:
    async with AsyncSessionLocal() as db:
        asignaturas = dict((await db.execute(select(Asignatura.id, Asignatura.nombre))).all())
        grados = dict((await db.execute(select(Grado.id, Grado.nombre))).all())
        filas = (await db.execute(
            select(Mensaje, Conversacion.asignatura_id, Usuario.grado_id)
            .join(Conversacion, Mensaje.conversacion_id == Conversacion.id)
            .join(Usuario, Conversacion.estudiante_id == Usuario.id)
            .order_by(Mensaje.conversacion_id, Mensaje.id)
        )).all()

        pregunta, cache = {}, {}
        total = invalidas = corregidas = 0
        coinciden, comparadas = {True: 0, False: 0}, {True: 0, False: 0}
        por_asignatura = {}
        mostrados = 0
        for m, asig_id, grado_id in filas:
            if m.rol == RolMensaje.usuario:
                pregunta[m.conversacion_id] = m.contenido
                continue
            q = pregunta.get(m.conversacion_id)
            if q is None or m.contenido in (RESPUESTA_FUERA_DE_CONTEXTO, RESPUESTA_LLM_NO_DISPONIBLE):
                continue
            total += 1
            clave = (q, asig_id, grado_id)
            if clave not in cache:
                cache[clave] = (await recuperar_contexto(q, asignaturas.get(asig_id), grados.get(grado_id)))[0]
            fragments = cache[clave]
            paginas = {f["page_num"] for f in fragments if f.get("page_num") is not None}
            guardadas = (m.referencias or {}).get("fragmentos") or []
            fecha = m.fecha_creacion.astimezone(ZONA).date()
            en_ventana = not ((desde and fecha < desde) or (hasta and fecha >= hasta))
            if guardadas:
                comparadas[en_ventana] += 1
                coinciden[en_ventana] += {f.get("page_num") for f in guardadas} == paginas
            cuerpo = _sin_footer_pagina(m.contenido)
            if set(_paginas_citadas(cuerpo)) <= paginas:
                continue
            invalidas += 1
            nombre = asignaturas.get(asig_id)
            por_asignatura[nombre] = por_asignatura.get(nombre, 0) + 1
            if not aplicar or not en_ventana:
                continue
            nuevo = _quitar_citas_invalidas(cuerpo, paginas)
            if not _es_rechazo(nuevo) and fragments:
                nuevo += _referencia_paginas(fragments, nombre)
                m.referencias = {"fragmentos": [
                    {"page_num": f.get("page_num"), "libro_id": f.get("libro_id"), "distance": f.get("distance")}
                    for f in fragments]}
            if mostrados < ejemplos:
                mostrados += 1
                print(f"\n--- mensaje {m.id} ({nombre}, páginas recuperadas {sorted(paginas)})")
                print("ANTES:  ", m.contenido.replace("\n", " ⏎ "))
                print("DESPUÉS:", nuevo.replace("\n", " ⏎ "))
            m.contenido = nuevo
            corregidas += 1
        if aplicar:
            await db.commit()

    print(f"\nRespuestas del asistente con pregunta (sin las fijas de rechazo/respaldo): {total}")
    print(f"Recuperación recalculada = referencias guardadas: en la ventana {coinciden[True]}/{comparadas[True]}, "
          f"fuera {coinciden[False]}/{comparadas[False]}")
    print(f"Con alguna página citada fuera de sus fragmentos: {invalidas} {por_asignatura}")
    print(f"Corregidas: {corregidas}" if aplicar else "(sin --aplicar: no se cambió nada)")


def _fecha(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--desde", type=_fecha, help="fecha (GT) inicial inclusive de los mensajes a corregir")
    ap.add_argument("--hasta", type=_fecha, help="fecha (GT) final exclusiva")
    ap.add_argument("--ejemplos", type=int, default=3)
    args = ap.parse_args()
    asyncio.run(main(args.aplicar, args.desde, args.hasta, args.ejemplos))
