"""
Recolecta respuestas del tutor + contextos recuperados para RAGAS, SIN el
endpoint /chat/preguntar-debug (eliminado, ver evaluar_ragas.py).

Corre DENTRO del contenedor del backend y llama a procesar_pregunta (el mismo
pipeline del chat) capturando los fragmentos que se le pasan al LLM. No escribe
en la BD (flush en vez de commit + rollback). Escribe <salida>/respuestas_cache.json
con el mismo formato que usa evaluar_ragas.py, que luego evalúa desde el host.

Muestra: --n preguntas estratificadas por (asignatura, tipo) en proporción al
set original, tomando en cada grupo las posiciones 0, 2, 4… (determinístico).

Uso:
    docker compose exec backend python scripts/evaluacion/recolectar_respuestas_local.py \\
        --n 20 --salida scripts/evaluacion/ragas_2026-10_deepseek --max-usd 1
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts")

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.llm.client import llm_client  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.modules.chat import service as chat_service  # noqa: E402
from costos_llm import Presupuesto, agregar_argumento_max_usd  # noqa: E402

logging.basicConfig(level=logging.ERROR)

DIR = Path(__file__).resolve().parent
ESTUDIANTE = "carlos"  # grado_id=1, ve los dos libros locales


def muestra_estratificada(preguntas: list[dict], n: int) -> list[dict]:
    grupos: dict[tuple, list] = {}
    for p in preguntas:
        grupos.setdefault((p["asignatura_id"], p["tipo"]), []).append(p)
    # shortcut: el redondeo puede dar ±1 respecto de n en otras proporciones; con 50→20 da 20 exactas.
    cuotas = {k: round(n * len(v) / len(preguntas)) for k, v in grupos.items()}
    elegidas = []
    for k, items in grupos.items():
        orden = items[::2] + items[1::2]  # posiciones pares primero
        elegidas += orden[:cuotas[k]]
    return sorted(elegidas, key=preguntas.index)


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--salida", required=True, help="carpeta de resultados (no se sobrescribe un cache existente)")
    agregar_argumento_max_usd(parser)
    args = parser.parse_args()

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cache = salida / "respuestas_cache.json"
    if cache.exists():
        print(f"ERROR: ya existe {cache}; usa otra --salida o bórralo a mano.", file=sys.stderr)
        sys.exit(1)

    preguntas = muestra_estratificada(json.loads((DIR / "preguntas_ragas.json").read_text(encoding="utf-8")), args.n)
    presupuesto = Presupuesto(args.max_usd)
    presupuesto.instrumentar(llm_client._client)

    # Captura los fragmentos que el chat le pasa al LLM (después de filtros y grounding).
    capturados: list[list[dict]] = []
    original = chat_service.build_context_prompt

    def capturar(fragments):
        capturados.append(list(fragments))
        return original(fragments)

    chat_service.build_context_prompt = capturar

    db = AsyncSessionLocal()
    db.commit = db.flush
    resultados = []
    try:
        estudiante = (await db.execute(select(Usuario).where(Usuario.username == ESTUDIANTE))).scalar_one()
        for i, p in enumerate(preguntas, 1):
            presupuesto.verificar()
            capturados.clear()
            r = await chat_service.procesar_pregunta(db, p["pregunta"], None, p["asignatura_id"], estudiante)
            contextos = [f.get("text", "") for f in (capturados[-1] if capturados else []) if f.get("text")]
            resultados.append({
                "pregunta": p["pregunta"], "asignatura": p["asignatura"], "asignatura_id": p["asignatura_id"],
                "tipo": p["tipo"], "grado": p.get("grado"), "respuesta_tutor": r["respuesta"],
                "retrieved_contexts": contextos, "num_contextos": len(contextos),
                "status": "OK" if contextos else "EMPTY",
            })
            print(f"{i}/{len(preguntas)} {'✓' if contextos else '∅'} {p['pregunta'][:60]}", flush=True)
    finally:
        await db.rollback()
        await db.close()
        chat_service.build_context_prompt = original

    cache.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    (salida / "config.json").write_text(json.dumps({
        "modelo_tutor": settings.LLM_MODEL, "modelo_tutor_matematicas": settings.LLM_MODEL_MATEMATICAS,
        "n_preguntas": len(resultados), "fuente": "procesar_pregunta local (BD local, libros 3 y 4)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    presupuesto.imprimir_resumen()
    print(f"Cache: {cache}")


if __name__ == "__main__":
    asyncio.run(main())
