"""
Verifica la BD contra datos/datos_simulados_cap5.csv tras correr seed_piloto.py.

Por estudiante (fila del CSV -> cuenta del mapeo): sesiones, consultas y actividades
exactas, tasa de acierto ±2 y dominio de inicio/final (mismas definiciones que
seed_piloto.py: contar_piloto). Global: medias de la Tabla 14 y distribución del
dominio final. Mapa de calor de cada grado (docente.service.diagnostico): celdas en al
menos 8 lecciones por asignatura y con los tres niveles. Sale con código 1 si algo no cuadra.

Uso (dentro del contenedor):
  python scripts/verificar_seed.py --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv
"""
import argparse
import asyncio
import csv
import os
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seed_piloto import CIENCIAS, MATEMATICAS, AsyncSessionLocal, contar_piloto, leer_csv  # noqa: E402

from app.modules.docente.service import diagnostico  # noqa: E402

TABLA_14 = {"consultas": 16.56, "actividades": 13.67, "tasa": 62.50, "sesiones": 9.24}
DOMINIO_FINAL = {"En proceso": 59, "Domina": 7, "Necesita refuerzo": 6}
MIN_LECCIONES_MAPA = 8


async def main_async(args) -> int:
    filas = {r["fila"]: r for r in leer_csv(args.csv)}
    with open(args.mapeo, encoding="utf-8") as f:
        mapeo = {int(m["fila_csv"]): m for m in csv.DictReader(f)}
    errores = 0
    obtenidos = {}
    async with AsyncSessionLocal() as db:
        for fila, r in sorted(filas.items()):
            h = obtenidos[fila] = await contar_piloto(db, int(mapeo[fila]["estudiante_id"]))
            fallas = [k for k in ("sesiones", "consultas", "actividades") if h[k] != r[k]]
            if h["tasa"] is None or abs(h["tasa"] - r["tasa_acierto"]) > 2:
                fallas.append("tasa")
            fallas += [k for k in ("dominio_inicio", "dominio_final") if h[k] != r[k]]
            errores += bool(fallas)
            if fallas or args.detalle:
                print(f"fila {fila:>2} {mapeo[fila]['username']:13} ses {h['sesiones']}/{r['sesiones']} "
                      f"cons {h['consultas']}/{r['consultas']} act {h['actividades']}/{r['actividades']} "
                      f"tasa {h['tasa'] if h['tasa'] is None else round(h['tasa'], 1)}/{r['tasa_acierto']} "
                      f"dominio {h['dominio_inicio']}->{h['dominio_final']} / {r['dominio_inicio']}->{r['dominio_final']}"
                      f"{'  FALLA ' + ','.join(fallas) if fallas else ''}")
    print(f"\nPor estudiante: {len(filas) - errores}/{len(filas)} filas cuadran")
    medias = {
        "consultas": mean(h["consultas"] for h in obtenidos.values()),
        "actividades": mean(h["actividades"] for h in obtenidos.values()),
        "tasa": mean(h["tasa"] or 0 for h in obtenidos.values()),
        "sesiones": mean(h["sesiones"] for h in obtenidos.values()),
    }
    print("Medias (BD / Tabla 14):")
    for k, v in medias.items():
        ok = abs(v - TABLA_14[k]) <= (0.5 if k == "tasa" else 0.005)
        errores += not ok
        print(f"  {k:12} {v:6.2f} / {TABLA_14[k]:6.2f}  {'OK' if ok else 'FALLA'}")
    dist = Counter(h["dominio_final"] for h in obtenidos.values())
    ok = dict(dist) == DOMINIO_FINAL
    errores += not ok
    print(f"Dominio final (BD / CSV): {dict(dist)} / {DOMINIO_FINAL}  {'OK' if ok else 'FALLA'}")
    print("Mapa de calor (lecciones con celdas · domina/en_proceso/refuerzo):")
    async with AsyncSessionLocal() as db:
        for g in sorted({r["grado_id"] for r in filas.values()}):
            for a in (CIENCIAS, MATEMATICAS):
                d = await diagnostico(db, g, a)
                celdas = [c for e in d.estudiantes for c in e.celdas if c.nivel != "sin_datos"]
                n_lecc = len({c.leccion_id for c in celdas})
                c = Counter(x.nivel for x in celdas)
                ok = n_lecc >= MIN_LECCIONES_MAPA and all(c[n] for n in ("domina", "en_proceso", "refuerzo"))
                errores += not ok
                print(f"  grado {g} {d.asignatura:20} {n_lecc:>2} lecc · {c['domina']}/{c['en_proceso']}/{c['refuerzo']}"
                      f"  {'OK' if ok else 'FALLA'}")
    return 1 if errores else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--mapeo", type=Path, required=True)
    ap.add_argument("--detalle", action="store_true", help="imprime todas las filas, no solo las que fallan")
    sys.exit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()
