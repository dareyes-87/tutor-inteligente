import json, re, sys

SP = "/tmp/claude-1000/-home-dareyes-tutor-inteligente/d0d4f607-a122-4110-97ad-b736566a05f8/scratchpad"

# --- Filtro ACTUAL ---
MARC_OLD = ("mesa lista", "ahora es tu turno", "ejercicio", "practica")

# --- Filtro NUEVO propuesto: OLD + anclas instruccionales de bajo riesgo ---
# Se prefieren frases multi-palabra / verbos imperativos de instrucción que casi
# nunca aparecen en prosa de teoría. Se EVITAN sueltos genéricos como "responde",
# "actividad", "relaciona", "completa", "coloca" (salen en teoría) salvo anclados.
MARC_NEW = MARC_OLD + (
    # ALTA PRECISIÓN: frases ancladas de instrucción, casi imposibles en prosa
    # teórica. Se evitan sueltos ("encierra", "resuelve", "instrucciones",
    # "observa la imagen y", "une con", "relaciona con") que en V1 marcaron
    # teoría real (células, fotosíntesis) → falsos positivos.
    "instrucciones:",
    "realiza lo que se indica",
    "¿cómo lo aprendo",
    "lee y realiza lo",
    "resuelve cada", "resuelve los siguientes", "resuelve las siguientes",
    "resuelve el siguiente", "resuelve la siguiente",
    "encierra en un", "encierra la", "encierra el", "encierra las", "encierra los",
    "marca con una",
    "une cada", "une con una línea", "une los siguientes", "une mediante",
    "completa la tabla", "completa el cuadro", "completa las siguientes",
    "contesta las siguientes", "contesta lo siguiente", "contesta las preguntas",
    "escribe el nombre", "escribe la respuesta", "escribe en el recuadro",
    "observa y responde", "observa la imagen y responde",
    "subraya la respuesta", "subraya la palabra", "subraya las",
    "relaciona cada", "relaciona las columnas",
)

def flag(text, marcadores):
    t = (text or "").lower()
    return any(m in t for m in marcadores)

def parse_rango(p):
    if not p: return None
    n = [int(x) for x in re.findall(r"\d+", p)]
    return (min(n), max(n)) if n else None

def simular(libro):
    frags = json.load(open(f"{SP}/frags_libro{libro}.json"))
    ruta = json.load(open(f"{SP}/ruta_libro{libro}.json"))
    lecciones = ruta["lecciones"]
    total = len(frags)
    old_n = sum(1 for f in frags if flag(f["contenido_texto"], MARC_OLD))
    new_n = sum(1 for f in frags if flag(f["contenido_texto"], MARC_NEW))

    print("=" * 78)
    print(f"LIBRO {libro} — {ruta['asignatura']} — {total} fragmentos, {len(lecciones)} lecciones")
    print("=" * 78)
    print(f"  Filtro ACTUAL marca:  {old_n:>3} frags ({old_n/total*100:4.1f}%)")
    print(f"  Filtro NUEVO marca:   {new_n:>3} frags ({new_n/total*100:4.1f}%)")
    print()

    # Por lección: fragmentos en rango que SOBREVIVEN cada filtro.
    riesgo_new, riesgo_old = [], []
    peor = []
    for l in lecciones:
        r = parse_rango(l["paginas"])
        if r is None:
            continue
        ini, fin = r
        en_rango = [f for f in frags if f["numero_pagina"] is not None and ini <= f["numero_pagina"] <= fin]
        surv_old = [f for f in en_rango if not flag(f["contenido_texto"], MARC_OLD)]
        surv_new = [f for f in en_rango if not flag(f["contenido_texto"], MARC_NEW)]
        peor.append((len(surv_new), l["orden"], l["id"], l["paginas"], l["nombre"], len(en_rango), len(surv_old)))
        if len(surv_new) < 3:
            riesgo_new.append((l, len(en_rango), len(surv_old), len(surv_new)))
        if len(surv_old) < 3:
            riesgo_old.append((l, len(en_rango), len(surv_old), len(surv_new)))

    vacias_new = sum(1 for x in peor if x[0] == 0)
    men3_new = sum(1 for x in peor if x[0] < 3)
    print(f"  Lecciones que quedarían VACÍAS (0 frags) con NUEVO: {vacias_new}")
    print(f"  Lecciones con <3 frags con NUEVO: {men3_new}")
    print()
    print("  Lecciones MÁS AJUSTADAS con el filtro NUEVO (survivors_new, orden, id, pags, en_rango→surv_old→surv_new):")
    for sn, orden, lid, pags, nombre, nrango, so in sorted(peor)[:8]:
        marca = "  <<VACÍA"  if sn == 0 else ("  <<<3" if sn < 3 else "")
        print(f"    surv_new={sn:>2} | orden={orden:>2} id={lid} pags={pags:>7} '{nombre[:30]}' (rango={nrango}, old={so}){marca}")
    print()
    return {"libro": libro, "old_n": old_n, "new_n": new_n, "total": total,
            "vacias_new": vacias_new, "men3_new": men3_new, "peor": peor}

def muestra_falsos_positivos(libro, n=6):
    frags = json.load(open(f"{SP}/frags_libro{libro}.json"))
    nuevos = [f for f in frags if flag(f["contenido_texto"], MARC_NEW) and not flag(f["contenido_texto"], MARC_OLD)]
    print(f"  [libro {libro}] fragmentos NUEVOS marcados (no por OLD): {len(nuevos)}. Muestra para juzgar precisión:")
    for f in nuevos[:n]:
        t = f["contenido_texto"].replace("\n", " ")
        # qué marcador lo activó
        low = t.lower()
        cual = next((m for m in MARC_NEW if m not in MARC_OLD and m in low), "?")
        print(f"    p{f['numero_pagina']} [{cual!r}]: {t[:120]}")
    print()

if __name__ == "__main__":
    res = [simular(l) for l in (1, 2, 3)]
    print("\n########## MUESTRAS DE FALSOS POSITIVOS (para calibrar) ##########\n")
    for l in (1, 2, 3):
        muestra_falsos_positivos(l)
    print("########## RESUMEN ##########")
    for r in res:
        print(f"  libro {r['libro']}: OLD {r['old_n']}/{r['total']} → NEW {r['new_n']}/{r['total']} | "
              f"lecciones vacías(new)={r['vacias_new']} <3(new)={r['men3_new']}")
