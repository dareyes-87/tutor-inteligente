"""
Limpia el uso de PRUEBA posterior al piloto en los 72 estudiantes del piloto (los del mapeo).

Borra, por estudiante, lo que tenga fecha posterior al 2026-09-30 23:59 (hora de Guatemala):
resultados de actividades (y las actividades que solo esos resultados usaban), mensajes y
conversaciones. Después recalcula desde lo que queda, con las funciones reales del backend:
  - perfil de comprensión: promedio y conteo por (asignatura, tema) de los resultados restantes;
  - avance de ruta y puntos: se rehace la ruta desde cero repitiendo cada ronda de ruta del piloto
    con lecciones.service.completar_nivel a la hora de la ronda (como seed_piloto.py). Las rondas
    se reconocen por el banco del seed (debug/seed_piloto_pool.json: actividad -> lección:nivel);
  - racha: seed_piloto.recalcular_racha sobre los días de uso restantes.

Todo corre en UNA transacción. Comprobación: los estudiantes sin nada que borrar deben quedar
idénticos tras recalcular; si alguno cambia, el método no reproduce el seed y no se guarda nada.
Por defecto es --dry-run (muestra qué borraría y qué cambiaría, y deshace); --aplicar guarda.

Uso (dentro del contenedor):
  python scripts/limpiar_pruebas.py --mapeo /tmp/mapeo.csv            # dry-run
  python scripts/limpiar_pruebas.py --mapeo /tmp/mapeo.csv --aplicar
"""
import argparse
import asyncio
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seed_piloto import (  # noqa: E402
    ACTIVIDADES_POR_RONDA, APROBADA, ZONA, _cargar_pool, iniciar_leccion_si_falta, leccion_actual,
    libros_y_lecciones, recalcular_racha,
)
from sqlalchemy import delete, func, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import engine  # noqa: E402
from app.models.actividad import Actividad, ResultadoActividad  # noqa: E402
from app.models.conversacion import Conversacion  # noqa: E402
from app.models.leccion import Leccion  # noqa: E402
from app.models.mensaje import Mensaje  # noqa: E402
from app.models.perfil_comprension import PerfilComprension  # noqa: E402
from app.models.progreso_leccion import EstadoLeccion, ProgresoLeccion  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402

CORTE = datetime(2026, 10, 1, tzinfo=ZONA)  # posterior a 2026-09-30 23:59 en Guatemala


async def foto(db, est_id: int) -> dict:
    """Estado derivado del estudiante que este script recalcula (para comparar antes/después)."""
    u = (await db.execute(select(Usuario).where(Usuario.id == est_id))).scalar_one()
    await db.refresh(u)
    perfil = {(p.asignatura_id, p.tema): (round(p.puntaje_promedio, 6), p.total_actividades)
              for p in (await db.execute(select(PerfilComprension).where(
                  PerfilComprension.estudiante_id == est_id))).scalars()}
    # Solo las filas con avance: las recién creadas (lección 1 'disponible', el resto 'bloqueada')
    # las crea GET /ruta al vuelo.
    filas = (await db.execute(select(ProgresoLeccion, Leccion.orden).join(Leccion).where(
        ProgresoLeccion.estudiante_id == est_id))).all()
    ruta = {p.leccion_id: (p.estado.value, p.nivel_actual, p.nivel_completado, p.intentos_nivel)
            for p, orden in filas
            if (p.estado, p.nivel_completado, p.intentos_nivel)
            != (EstadoLeccion.disponible if orden == 1 else EstadoLeccion.bloqueada, 0, 0)}
    return {"racha": (u.racha_actual, u.mejor_racha, u.ultima_actividad), "puntos": u.puntos_totales,
            "perfil": perfil, "ruta": ruta}


async def borrar_posteriores(db, est_id: int) -> dict:
    res = (await db.execute(select(ResultadoActividad.id, ResultadoActividad.actividad_id).where(
        ResultadoActividad.estudiante_id == est_id, ResultadoActividad.fecha >= CORTE))).all()
    act_ids = {a for _, a in res}
    await db.execute(delete(ResultadoActividad).where(ResultadoActividad.id.in_([i for i, _ in res])))
    # Actividades que ya nadie más respondió (Actividad no guarda quién la pidió).
    usadas = set((await db.execute(select(ResultadoActividad.actividad_id).where(
        ResultadoActividad.actividad_id.in_(act_ids)))).scalars())
    n_act = (await db.execute(delete(Actividad).where(Actividad.id.in_(act_ids - usadas)))).rowcount
    convs = list((await db.execute(select(Conversacion.id).where(
        Conversacion.estudiante_id == est_id, Conversacion.fecha_creacion >= CORTE))).scalars())
    propias = select(Conversacion.id).where(Conversacion.estudiante_id == est_id)
    n_msg = (await db.execute(delete(Mensaje).where(
        Mensaje.conversacion_id.in_(propias), Mensaje.fecha_creacion >= CORTE))).rowcount
    await db.execute(delete(Conversacion).where(Conversacion.id.in_(convs)))
    # Las conversaciones anteriores al corte que siguieron recibiendo mensajes.
    ultimo = (select(func.max(Mensaje.fecha_creacion)).where(Mensaje.conversacion_id == Conversacion.id)
              .scalar_subquery())
    await db.execute(update(Conversacion).where(Conversacion.estudiante_id == est_id,
                                                Conversacion.fecha_ultimo_mensaje >= CORTE)
                     .values(fecha_ultimo_mensaje=func.coalesce(ultimo, Conversacion.fecha_creacion))
                     .execution_options(synchronize_session=False))
    await db.flush()
    return {"resultados": len(res), "actividades": n_act, "mensajes": n_msg, "conversaciones": len(convs)}


async def rehacer_perfil(db, est_id: int) -> None:
    await db.execute(delete(PerfilComprension).where(PerfilComprension.estudiante_id == est_id))
    tema = func.coalesce(Actividad.tema, "General")
    filas = (await db.execute(
        select(Actividad.asignatura_id, tema,
               func.avg(ResultadoActividad.puntaje), func.count(), func.max(ResultadoActividad.fecha))
        .join(Actividad, Actividad.id == ResultadoActividad.actividad_id)
        .where(ResultadoActividad.estudiante_id == est_id).group_by(Actividad.asignatura_id, tema))).all()
    db.add_all(PerfilComprension(estudiante_id=est_id, asignatura_id=a, tema=t, puntaje_promedio=p,
                                 total_actividades=n, fecha_actualizacion=f) for a, t, p, n, f in filas)
    await db.flush()


def rondas_de_ruta(resultados, banco: dict) -> list[list]:
    """Agrupa los resultados (en orden) en rondas de ruta: seguidos, del mismo banco y del mismo día,
    empezando por la 1ª actividad del banco (una ronda usa acts[0:tam]). Las de 5 llamaron a
    completar_nivel; un bloque que el seed partió entre dos sesiones (días) quedan dos parciales."""
    rondas, actual = [], None
    for r in resultados:
        clave, pos = banco.get(r.actividad_id, (None, None))
        if clave is None or not clave.split(":")[1].isdigit():  # práctica libre ("p") o fuera del pool
            actual = None
            continue
        dia = r.fecha.astimezone(ZONA).date()
        if actual is None or pos == 0 or actual["clave"] != clave or actual["dia"] != dia:
            actual = {"clave": clave, "dia": dia, "res": []}
            rondas.append(actual)
        actual["res"].append(r)
    return [x["res"] for x in rondas]


async def rehacer_ruta(db, est: Usuario, banco: dict, libros: dict) -> None:
    """Ruta y puntos desde cero, repitiendo las rondas de 5 como seed_piloto.sembrar_estudiante."""
    from freezegun import freeze_time

    from app.modules.lecciones.service import completar_nivel
    await db.execute(delete(ProgresoLeccion).where(ProgresoLeccion.estudiante_id == est.id))
    await db.execute(update(Usuario).where(Usuario.id == est.id).values(puntos_totales=0))
    await db.flush()
    resultados = (await db.execute(
        select(ResultadoActividad, Actividad.leccion_id).join(Actividad)
        .where(ResultadoActividad.estudiante_id == est.id)
        .order_by(ResultadoActividad.fecha, ResultadoActividad.id))).all()
    leccion_de = {r.actividad_id: lid for r, lid in resultados}
    asignatura_de = {l.id: a for (g, a), lb in libros.items() if g == est.grado_id for l in lb["lecciones"].values()}
    for ronda in rondas_de_ruta([r for r, _ in resultados], banco):
        leccion_id = leccion_de[ronda[0].actividad_id]
        libro = libros[(est.grado_id, asignatura_de[leccion_id])]
        with freeze_time(ronda[0].fecha - timedelta(seconds=30), tick=True, real_asyncio=True):
            leccion, nivel = await leccion_actual(db, libro, est.id)
            if (leccion.id, nivel) != (leccion_id, int(banco[ronda[0].actividad_id][0].split(":")[1])):
                raise RuntimeError(f"{est.username}: ronda en {leccion_id} fuera de la lección/nivel actual")
            await iniciar_leccion_si_falta(db, leccion, est.id)  # también en bloques parciales, como el seed
        if len(ronda) != ACTIVIDADES_POR_RONDA:
            continue  # ronda parcial: el seed no la cierra con completar_nivel
        puntajes = [r.puntaje for r in ronda]
        with freeze_time(ronda[-1].fecha + timedelta(seconds=5), tick=True, real_asyncio=True):
            await completar_nivel(est.id, leccion_id, nivel, sum(p >= APROBADA for p in puntajes),
                                  int(puntajes[-1]), db, total_actividades=len(ronda))


async def main_async(args) -> int:
    with open(args.mapeo, encoding="utf-8") as f:
        ids = [int(m["estudiante_id"]) for m in csv.DictReader(f)]
    pool = _cargar_pool()
    banco = {i: (clave, pos) for clave, v in pool["actividades"].items() for pos, i in enumerate(v)}
    async with engine.connect() as conn:
        trans = await conn.begin()
        # commit() de los servicios cierra un SAVEPOINT; solo trans.commit() guarda de verdad.
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        libros = await libros_y_lecciones(db)
        cambiados, distintos_sin_borrar = 0, []
        for est_id in ids:
            est = (await db.execute(select(Usuario).where(Usuario.id == est_id))).scalar_one()
            antes = await foto(db, est_id)
            borrado = await borrar_posteriores(db, est_id)
            await rehacer_perfil(db, est_id)
            await rehacer_ruta(db, est, banco, libros)
            await recalcular_racha(db, est_id)
            despues = await foto(db, est_id)
            hubo_borrado = any(borrado.values())
            diff = [k for k in antes if antes[k] != despues[k]]
            if diff and not hubo_borrado:
                distintos_sin_borrar.append(est.username)
            if hubo_borrado or diff:
                cambiados += 1
                print(f"{est.username:14} borra {borrado}")
                for k in diff:
                    print(f"    {k}: {_resumen(k, antes[k])} -> {_resumen(k, despues[k])}")
        print(f"\n{cambiados} de {len(ids)} estudiantes con datos posteriores al corte.")
        if distintos_sin_borrar:
            print(f"FALLA: el recálculo cambia estudiantes sin datos nuevos: {distintos_sin_borrar}. No se guarda.")
            await trans.rollback()
            return 1
        print("Comprobación OK: el recálculo deja idénticos a los estudiantes sin datos nuevos.")
        if args.aplicar:
            await trans.commit()
            print("Cambios guardados.")
        else:
            await trans.rollback()
            print("dry-run: no se guardó nada (usar --aplicar).")
    return 0


def _resumen(k: str, v):
    if k == "ruta":
        return {lid: x for lid, x in sorted(v.items())}
    if k == "perfil":
        return f"{len(v)} temas, {sum(n for _, n in v.values())} actividades"
    return v


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mapeo", type=Path, required=True, help="mapeo fila -> estudiante (los 72 del piloto)")
    ap.add_argument("--aplicar", action="store_true", help="guarda los cambios (por defecto, dry-run)")
    sys.exit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()
