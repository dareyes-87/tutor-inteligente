"""
Benchmark de modelos candidatos de Together para reemplazar los retirados
(Qwen2.5-7B / Llama-3.3-70B, ver docs/despliegue-produccion.md).

Corre DENTRO del contenedor del backend (usa la BD local con los libros 3 =
Ciencias 4to y 4 = Matemáticas 4to ya indexados) y ejercita el código REAL de
la app con cada modelo (los tres roles apuntando al candidato):

  chat         15 preguntas del set RAGAS (Ciencias/Matemáticas, conceptual/
               factual/procedimental) + 3 fuera del libro, vía procesar_pregunta
               (pre-grounding, prompt, post-grounding y referencia de página).
  actividades  20 generaciones (5 tipos × 4, mitad Ciencias, mitad Matemáticas):
               % que pasa la validación determinística al primer intento y tras
               la regeneración como opcion_multiple (misma lógica que generar_actividad).
  micro        5 micro-lecciones (generar_micro_leccion, nivel 1).
  ruta         5 segmentos de la generación de la ruta de lecciones.

No escribe en la BD: cada sesión hace flush en vez de commit y rollback al final.
Respeta el timeout real del cliente (45 s + 1 reintento del SDK) y lo reporta.

Uso:
    docker compose exec backend python scripts/debug/benchmark_modelos.py \\
        --modelos Qwen/Qwen3.5-9B,openai/gpt-oss-120b --max-usd 2
    (--pruebas chat,actividades,micro,ruta  --n-chat 15 ...  --salida /tmp/bench.json)
"""
import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts")

import together  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.llm.client import llm_client  # noqa: E402
from app.models.actividad import TipoActividad  # noqa: E402
from app.models.fragmento import Fragmento  # noqa: E402
from app.models.leccion import Leccion  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.modules.actividades import generator as gen_act  # noqa: E402
from app.modules.chat.prompts import build_context_prompt  # noqa: E402
from app.modules.chat.service import (  # noqa: E402
    RESPUESTA_FUERA_DE_CONTEXTO, RESPUESTA_LLM_NO_DISPONIBLE, _es_rechazo, procesar_pregunta,
)
from app.modules.lecciones import generator as gen_ruta  # noqa: E402
from app.modules.lecciones.service import _parsear_rango_paginas, generar_micro_leccion  # noqa: E402
from app.modules.rag.search import es_ejercicio_del_libro  # noqa: E402
from costos_llm import Presupuesto, PresupuestoAgotado, agregar_argumento_max_usd  # noqa: E402

logging.basicConfig(level=logging.ERROR)

ESTUDIANTE = "carlos"  # grado_id=1, ve los dos libros locales
LIBROS = {"Ciencias Naturales": 3, "Matemáticas": 4}
LECCIONES = {  # repartidas a lo largo de cada libro (se evita la portada)
    "Ciencias Naturales": [179, 183, 188, 194, 201],
    "Matemáticas": [251, 255, 257, 260, 264],
}
FUERA_DEL_LIBRO = [
    ("¿Quién ganó la Copa del Mundo de fútbol de 2022?", 1),
    ("¿Cómo se hace una página web con HTML?", 2),
    ("¿Cuál es la receta del pepián?", 1),
]
TIPOS = list(TipoActividad)

# La app captura cualquier excepción del LLM (generate_json -> None, chat ->
# respaldo), así que el tope se verifica explícitamente antes de cada ítem.
PRESUPUESTO: Presupuesto | None = None


class Llamadas:
    """Cuenta llamadas al API y sus errores (timeouts, etc.) por prueba."""

    def __init__(self):
        self.total = 0
        self.errores: dict[str, int] = {}

    def instrumentar(self, cliente):
        completions = cliente.chat.completions
        original = completions.create

        def create(*args, **kwargs):
            self.total += 1
            try:
                return original(*args, **kwargs)
            except PresupuestoAgotado:
                raise
            except Exception as e:
                clave = type(e).__name__
                self.errores[clave] = self.errores.get(clave, 0) + 1
                raise

        completions.create = create


def p95(valores):
    if not valores:
        return None
    v = sorted(valores)
    return v[min(len(v) - 1, round(0.95 * (len(v) - 1)))]


def stats_latencia(valores):
    return {"media": round(statistics.mean(valores), 2) if valores else None, "p95": round(p95(valores), 2) if valores else None}


def preguntas_chat(n: int) -> list[tuple[str, int, str]]:
    """n preguntas del set RAGAS alternando asignatura y rotando el tipo."""
    with open("/app/scripts/evaluacion/preguntas_ragas.json", encoding="utf-8") as f:
        todas = json.load(f)
    por_clave: dict[tuple, list] = {}
    for p in todas:
        por_clave.setdefault((p["asignatura_id"], p["tipo"]), []).append(p)
    claves = sorted(por_clave, key=lambda k: (k[1], k[0]))
    elegidas, i = [], 0
    while len(elegidas) < n and any(por_clave.values()):
        k = claves[i % len(claves)]
        if por_clave[k]:
            p = por_clave[k].pop(0)
            elegidas.append((p["pregunta"], p["asignatura_id"], p["tipo"]))
        i += 1
    return elegidas


async def sesion_sin_escritura():
    db = AsyncSessionLocal()
    db.commit = db.flush  # la app hace commit: aquí solo flush, y rollback al final
    return db


async def prueba_chat(n: int, llamadas: Llamadas) -> dict:
    db = await sesion_sin_escritura()
    try:
        estudiante = (await db.execute(select(Usuario).where(Usuario.username == ESTUDIANTE))).scalar_one()
        dentro, fuera, ejemplos = [], [], []
        for pregunta, asig, tipo in preguntas_chat(n):
            PRESUPUESTO.verificar()
            antes = llamadas.total
            t = time.monotonic()
            r = await procesar_pregunta(db, pregunta, None, asig, estudiante)
            seg = time.monotonic() - t
            dentro.append({
                "pregunta": pregunta, "asignatura_id": asig, "tipo": tipo, "segundos": round(seg, 2),
                "llamo_llm": llamadas.total > antes, "respaldo": r["respuesta"] == RESPUESTA_LLM_NO_DISPONIBLE,
                "con_cita": bool(r["referencias"]), "rechazo": _es_rechazo(r["respuesta"]),
                "respuesta": r["respuesta"],
            })
        for pregunta, asig in FUERA_DEL_LIBRO:
            PRESUPUESTO.verificar()
            antes = llamadas.total
            r = await procesar_pregunta(db, pregunta, None, asig, estudiante)
            fuera.append({
                "pregunta": pregunta, "llamo_llm": llamadas.total > antes,
                "rechazo_correcto": r["respuesta"] == RESPUESTA_FUERA_DE_CONTEXTO
                or (_es_rechazo(r["respuesta"]) and r["respuesta"] != RESPUESTA_LLM_NO_DISPONIBLE),
                "respuesta": r["respuesta"],
            })
        # 3 ejemplos para juzgar el español: 1 conceptual Ciencias, 1 Matemáticas, 1 procedimental
        for filtro in (
            lambda d: d["asignatura_id"] == 1 and d["tipo"] == "conceptual",
            lambda d: d["asignatura_id"] == 2,
            lambda d: d["tipo"] == "procedimental",
        ):
            ej = next((d for d in dentro if filtro(d) and d not in ejemplos and d["llamo_llm"]), None)
            if ej:
                ejemplos.append(ej)
        con_llm = [d for d in dentro if d["llamo_llm"]]
        return {
            "latencia": stats_latencia([d["segundos"] for d in con_llm]),
            "pct_con_cita": round(100 * sum(d["con_cita"] for d in dentro) / len(dentro), 1),
            "respaldos_por_fallo_llm": sum(d["respaldo"] for d in dentro),
            "rechazos_en_preguntas_del_libro": sum(d["rechazo"] for d in dentro),
            "rechazo_correcto_fuera": f"{sum(f['rechazo_correcto'] for f in fuera)}/{len(fuera)}",
            "fuera_llegaron_al_llm": sum(f["llamo_llm"] for f in fuera),
            "ejemplos": [{"pregunta": e["pregunta"], "respuesta": e["respuesta"]} for e in ejemplos],
            "detalle": dentro + fuera,
        }
    finally:
        await db.rollback()
        await db.close()


async def _contexto_leccion(db, leccion_id: int) -> tuple[Leccion, str]:
    """Mismo contexto que crear_actividad (modo 2: rango de páginas de la lección)."""
    leccion = (await db.execute(select(Leccion).where(Leccion.id == leccion_id))).scalar_one()
    ini, fin = _parsear_rango_paginas(leccion.paginas)
    rows = (await db.execute(
        select(Fragmento).where(
            Fragmento.libro_id == leccion.libro_id,
            Fragmento.numero_pagina >= ini, Fragmento.numero_pagina <= fin,
        ).order_by(Fragmento.numero_pagina, Fragmento.id)
    )).scalars().all()
    frags = [{"page_num": r.numero_pagina, "text": r.contenido_texto} for r in rows]
    frags = [f for f in frags if not es_ejercicio_del_libro(f["text"])]
    return leccion, build_context_prompt(frags)


def _valida(tipo, result, rango_max) -> bool:
    if not result or gen_act._actividad_invalida(tipo, result, rango_max):
        return False
    return not (tipo == TipoActividad.ordenar and not gen_act._verificar_ordenar_es_secuencia(result))


def _generar_una(tipo, context, tema, asignatura, grado) -> tuple[bool, bool]:
    """(válida al primer intento, válida tras regeneración). Replica generar_actividad
    sin la etapa anti-repetición (aquí no hay preguntas previas de sesión)."""
    rango_max = gen_act._rango_numerico_grado(asignatura, grado)
    es_mat = "matem" in asignatura.lower()
    es_cie = "ciencia" in asignatura.lower()
    r1 = gen_act._llamar_llm(tipo, context, tema, [], rango_max, es_mat, es_cie, [])
    if _valida(tipo, r1, rango_max):
        return True, True
    if r1 is None:  # la app no regenera si el JSON falló dos veces: se descarta
        return False, False
    r2 = gen_act._llamar_llm(TipoActividad.opcion_multiple, context, tema, [], rango_max, es_mat, es_cie, [])
    return False, bool(r2) and not gen_act._actividad_invalida(TipoActividad.opcion_multiple, r2, rango_max)


async def prueba_actividades(n: int) -> dict:
    db = await sesion_sin_escritura()
    try:
        resultados = []
        for k in range(n):
            PRESUPUESTO.verificar()
            tipo = TIPOS[k % len(TIPOS)]
            asignatura = "Ciencias Naturales" if (k // len(TIPOS)) % 2 == 0 else "Matemáticas"
            leccion_id = LECCIONES[asignatura][(k // 2) % len(LECCIONES[asignatura])]
            leccion, context = await _contexto_leccion(db, leccion_id)
            t = time.monotonic()
            primero, final = await asyncio.to_thread(
                _generar_una, tipo, context, leccion.tema_clave or leccion.nombre, asignatura, "4to Primaria"
            )
            resultados.append({"tipo": tipo.value, "asignatura": asignatura, "primer_intento": primero,
                               "tras_regeneracion": final, "segundos": round(time.monotonic() - t, 2)})
        return {
            "pct_primer_intento": round(100 * sum(r["primer_intento"] for r in resultados) / len(resultados), 1),
            "pct_tras_regeneracion": round(100 * sum(r["tras_regeneracion"] for r in resultados) / len(resultados), 1),
            "latencia": stats_latencia([r["segundos"] for r in resultados]),
            "por_tipo": {
                t.value: f"{sum(r['primer_intento'] for r in resultados if r['tipo'] == t.value)}/"
                         f"{sum(r['tras_regeneracion'] for r in resultados if r['tipo'] == t.value)}/"
                         f"{sum(1 for r in resultados if r['tipo'] == t.value)}"
                for t in TIPOS
            },
            "detalle": resultados,
        }
    finally:
        await db.rollback()
        await db.close()


class ContadorJSON:
    """Cuenta cuántas llamadas a generate_json devolvieron JSON válido (dict)."""

    def __init__(self):
        self.ok = 0
        self.total = 0
        self._original = llm_client.generate_json

    def __enter__(self):
        def envuelta(*a, **kw):
            r = self._original(*a, **kw)
            self.total += 1
            self.ok += r is not None
            return r
        llm_client.generate_json = envuelta
        return self

    def __exit__(self, *exc):
        llm_client.generate_json = self._original


async def prueba_micro(n: int) -> dict:
    db = await sesion_sin_escritura()
    try:
        orden = [("Ciencias Naturales", i) for i in LECCIONES["Ciencias Naturales"]]
        orden = [x for par in zip(orden, [("Matemáticas", i) for i in LECCIONES["Matemáticas"]]) for x in par]
        resultados = []
        with ContadorJSON() as cj:
            for asignatura, leccion_id in orden[:n]:
                PRESUPUESTO.verificar()
                t = time.monotonic()
                try:
                    micro = await generar_micro_leccion(leccion_id, db, nivel=1)
                    ok, tarjetas = True, len(micro.tarjetas)
                except HTTPException:
                    ok, tarjetas = False, 0
                resultados.append({"leccion_id": leccion_id, "asignatura": asignatura, "ok": ok,
                                   "tarjetas": tarjetas, "segundos": round(time.monotonic() - t, 2)})
        return {
            "pct_ok": round(100 * sum(r["ok"] for r in resultados) / len(resultados), 1),
            "pct_json_valido_por_llamada": round(100 * cj.ok / cj.total, 1) if cj.total else None,
            "llamadas_json": cj.total,
            "latencia": stats_latencia([r["segundos"] for r in resultados]),
            "detalle": resultados,
        }
    finally:
        await db.rollback()
        await db.close()


async def prueba_ruta(n: int) -> dict:
    db = await sesion_sin_escritura()
    try:
        segmentos = []
        for asignatura, libro_id in LIBROS.items():
            frags = list((await db.execute(
                select(Fragmento).where(Fragmento.libro_id == libro_id).order_by(Fragmento.numero_pagina, Fragmento.id)
            )).scalars().all())
            segs = gen_ruta._segmentar(frags, gen_ruta._calcular_num_lecciones(frags))
            paso = max(1, len(segs) // 4)
            segmentos.append([(asignatura, i + 1, len(segs), segs[i]) for i in range(1, len(segs), paso)])
        intercalados = [x for par in zip(*segmentos) for x in par]
        resultados = []
        for asignatura, i, total, seg in intercalados[:n]:
            PRESUPUESTO.verificar()
            t = time.monotonic()
            data = await asyncio.to_thread(
                llm_client.generate_json, gen_ruta._build_messages_segmento(seg, i, total), max_tokens=512, rol="ruta"
            )
            item = gen_ruta._parsear(data)
            resultados.append({"asignatura": asignatura, "paginas": seg["paginas"], "ok": item is not None,
                               "nombre": item.nombre if item else None, "segundos": round(time.monotonic() - t, 2)})
        return {
            "pct_json_valido": round(100 * sum(r["ok"] for r in resultados) / len(resultados), 1),
            "latencia": stats_latencia([r["segundos"] for r in resultados]),
            "detalle": resultados,
        }
    finally:
        await db.rollback()
        await db.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modelos", required=True, help="IDs de Together separados por coma")
    parser.add_argument("--pruebas", default="chat,actividades,micro,ruta")
    parser.add_argument("--n-chat", type=int, default=15)
    parser.add_argument("--n-actividades", type=int, default=20)
    parser.add_argument("--n-micro", type=int, default=5)
    parser.add_argument("--n-ruta", type=int, default=5)
    parser.add_argument("--salida", default="/tmp/benchmark_modelos.json")
    agregar_argumento_max_usd(parser)
    args = parser.parse_args()

    global PRESUPUESTO
    presupuesto = PRESUPUESTO = Presupuesto(args.max_usd)
    presupuesto.instrumentar(llm_client._client)
    llamadas = Llamadas()
    llamadas.instrumentar(llm_client._client)

    pruebas = {
        "chat": lambda: prueba_chat(args.n_chat, llamadas),
        "actividades": lambda: prueba_actividades(args.n_actividades),
        "micro": lambda: prueba_micro(args.n_micro),
        "ruta": lambda: prueba_ruta(args.n_ruta),
    }
    resultados: dict = {}
    try:
        for modelo in [m.strip() for m in args.modelos.split(",") if m.strip()]:
            # Los tres roles apuntan al candidato, sin respaldos: se mide SOLO ese modelo.
            for campo in ("LLM_MODEL", "LLM_MODEL_MATEMATICAS", "LLM_MODEL_RUTA"):
                setattr(settings, campo, modelo)
            for campo in ("LLM_MODEL_FALLBACKS", "LLM_MODEL_MATEMATICAS_FALLBACKS", "LLM_MODEL_RUTA_FALLBACKS"):
                setattr(settings, campo, "")
            llm_client._no_disponibles.clear()
            resultados[modelo] = {}
            for nombre in [p.strip() for p in args.pruebas.split(",")]:
                llamadas.total, llamadas.errores = 0, {}
                usd_antes = presupuesto.total_usd
                t = time.monotonic()
                print(f"[{modelo}] {nombre}…", flush=True)
                r = await pruebas[nombre]()
                r["llamadas_api"] = llamadas.total
                r["errores_api"] = dict(llamadas.errores)  # APITimeoutError = excedió el timeout de 45 s (+1 reintento)
                r["usd"] = round(presupuesto.total_usd - usd_antes, 5)
                r["minutos"] = round((time.monotonic() - t) / 60, 1)
                resultados[modelo][nombre] = r
                print(f"[{modelo}] {nombre}: {json.dumps({k: v for k, v in r.items() if k not in ('detalle', 'ejemplos')}, ensure_ascii=False)}", flush=True)
                with open(args.salida, "w", encoding="utf-8") as f:
                    json.dump({"resultados": resultados, "costo": presupuesto.por_modelo}, f, ensure_ascii=False, indent=1)
    except PresupuestoAgotado as e:
        print(f"\nDETENIDO: {e}")
    finally:
        presupuesto.imprimir_resumen()
        with open(args.salida, "w", encoding="utf-8") as f:
            json.dump({"resultados": resultados, "costo": presupuesto.por_modelo}, f, ensure_ascii=False, indent=1)
        print(f"Resultados en {args.salida}")


if __name__ == "__main__":
    asyncio.run(main())
