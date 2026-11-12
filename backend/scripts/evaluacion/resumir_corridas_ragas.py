"""
Junta N corridas de evaluar_ragas_4metricas.py en media ± desviación estándar
(muestral, entre corridas) por métrica: global, por asignatura y por tipo.

Uso:
    python backend/scripts/evaluacion/resumir_corridas_ragas.py \
        backend/scripts/evaluacion/ragas_2026-11_produccion_e5/corrida_{1,2,3}
Salida: resumen_corridas.json junto a las corridas + tabla Markdown en stdout.
"""
import json
import statistics
import sys
from pathlib import Path

METRICAS = {"faithfulness": "Faithfulness", "answer_relevancy": "Answer Relevancy",
            "llm_context_precision_with_reference": "Context Precision (ref.)",
            "answer_correctness": "Answer Correctness"}


def ms(xs):
    xs = [x for x in xs if x is not None]
    return (round(statistics.mean(xs), 4), round(statistics.stdev(xs), 4) if len(xs) > 1 else 0.0)


def main(dirs):
    corridas = [json.loads((Path(d) / "resumen.json").read_text()) for d in dirs]
    grupos = {"Global": lambda r: r["global"]}
    grupos |= {a: (lambda r, a=a: r["por_asignatura"][a]) for a in corridas[0]["por_asignatura"]}
    grupos |= {t.capitalize(): (lambda r, t=t: r["por_tipo"][t]) for t in corridas[0]["por_tipo"]}

    salida = {"corridas": [str(d) for d in dirs], "ragas": corridas[0]["ragas"], "evaluador": corridas[0]["evaluador"],
              "costo_total_usd": round(sum(c["costo_usd"] for c in corridas), 4),
              "costo_por_corrida_usd": [c["costo_usd"] for c in corridas],
              "nan_por_corrida": [c["nan_por_metrica"] for c in corridas],
              "faithfulness_sobre_umbral_por_corrida": [c["faithfulness_sobre_umbral"] for c in corridas],
              "grupos": {}}
    print("| Grupo | n | " + " | ".join(METRICAS.values()) + " |")
    print("|---|---|" + "---|" * len(METRICAS))
    for nombre, f in grupos.items():
        fila = {m: ms([f(c)[m] for c in corridas]) for m in METRICAS}
        salida["grupos"][nombre] = {"n": f(corridas[0])["n"], **{m: {"media": v[0], "de": v[1]} for m, v in fila.items()}}
        celdas = [f"{v[0]:.3f} ± {v[1]:.3f}".replace(".", ",") for v in fila.values()]
        print(f"| {nombre} | {f(corridas[0])['n']} | " + " | ".join(celdas) + " |")
    (Path(dirs[0]).parent / "resumen_corridas.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in salida.items() if k != "grupos"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    assert ms([1.0, 0.5, None]) == (0.75, 0.3536)
    main(sys.argv[1:])
