#!/usr/bin/env python3
"""
Verificación local del Enfoque A: actividades de práctica acotadas a los
conceptos de la micro-lección (campo `conceptos_estudiados`), + mitigación de
repetición (memoria de preguntas persistida entre niveles).

Corre contra el backend local (http://localhost:8000) ya levantado. NO toca
producción. Crea un estudiante temporal vía admin y lo desactiva al terminar.

Uso:
    python3 scripts/debug/verificar_conceptos_practica.py

Env opcionales:
    BASE_URL   (default http://localhost:8000)
    NIVELES    (default 3)  — cuántos niveles simular en el test de repetición
    SOLO       (ciencias|matematicas|ambas, default ambas)
"""
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher

import requests

BASE = os.environ.get("BASE_URL", "http://localhost:8000")
NIVELES = int(os.environ.get("NIVELES", "3"))
SOLO = os.environ.get("SOLO", "ambas").lower()
# MODO=corta corre SOLO la verificación de respuesta_corta (rápido); por defecto
# corre el test completo (A/B + repetición + bugs 2/3) que también la incluye.
MODO = os.environ.get("MODO", "completo").lower()
# Forzar una lección concreta (por libro): "ciencias=178" o "matematicas=254".
LECCION_ID = {}
for _par in os.environ.get("LECCION_ID", "").split(","):
    if "=" in _par:
        _k, _v = _par.split("=", 1)
        LECCION_ID[_k.strip()] = int(_v)
TIMEOUT = 120

TIPOS = ["opcion_multiple", "verdadero_falso", "completar", "ordenar", "respuesta_corta"]

# Libro -> (asignatura_id, etiqueta). Resueltos en la sesión anterior.
LIBROS = {
    "ciencias": {"asignatura_id": 1, "etiqueta": "Ciencias Naturales"},
    "matematicas": {"asignatura_id": 2, "etiqueta": "Matemáticas"},
}


def _admin_creds():
    env = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", "..", ".env")) as f:
            for ln in f:
                if "=" in ln and not ln.strip().startswith("#"):
                    k, v = ln.split("=", 1)
                    env[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return env.get("ADMIN_USERNAME", "admin"), env.get("ADMIN_PASSWORD", "admin123")


def login(username, password):
    r = requests.post(
        f"{BASE}/auth/login",
        data={"username": username, "password": password},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ------------------------- normalización / similitud -------------------------

def norm(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", texto.lower()).strip()


def similares(a, b):
    """True si dos preguntas son casi-iguales (ratio difflib o Jaccard de
    tokens altos). Captura reformulaciones que el check verbatim del backend
    NO detecta."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if SequenceMatcher(None, na, nb).ratio() >= 0.75:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    jac = len(ta & tb) / len(ta | tb)
    return jac >= 0.6


def texto_pregunta(contenido):
    for campo in ("pregunta", "afirmacion", "oracion", "instruccion"):
        v = contenido.get(campo)
        if isinstance(v, str) and v.strip():
            return v
    return None


# --- Detectores de los 3 bugs reportados ---

_NEGACIONES = ("no", "ni", "nunca", "jamas", "tampoco", "sin")


def tiene_doble_negacion(texto):
    """Heurística: 2+ palabras de negación en la misma pregunta (Bug 3)."""
    toks = norm(texto).split()
    return sum(1 for t in toks if t in _NEGACIONES) >= 2


_MARCADORES_ANALOGIA = ("como un", "como una", "como los", "como las", "es como", "son como")


def parece_analogia(texto):
    """Marcadores de analogía/metáfora (Bug 2b: 'es como un río', 'como barcos')."""
    n = norm(texto)
    return any(m in n for m in _MARCADORES_ANALOGIA)


def n_palabras(texto):
    return len([w for w in (texto or "").split() if w != "___"])


def contar_duplicados(preguntas):
    """(#exactos, #casi-dups) sobre una lista de textos de pregunta."""
    exactos, casi = 0, 0
    vistos_norm = []
    vistos_txt = []
    for p in preguntas:
        n = norm(p)
        if n in vistos_norm:
            exactos += 1
        elif any(similares(p, q) for q in vistos_txt):
            casi += 1
        vistos_norm.append(n)
        vistos_txt.append(p)
    return exactos, casi


# ------------------------------- API helpers --------------------------------

def micro_leccion(tok, leccion_id, nivel):
    r = requests.get(
        f"{BASE}/lecciones/{leccion_id}/micro-leccion?nivel={nivel}",
        headers=h(tok), timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def conceptos_de_tarjetas(micro):
    out = []
    for t in micro.get("tarjetas", []):
        if t.get("tipo") != "concepto":
            continue
        cuerpo = (t.get("contenido") or "").strip()
        if not cuerpo:
            continue
        titulo = (t.get("titulo_concepto") or "").strip()
        out.append(f"{titulo}: {cuerpo}" if titulo else cuerpo)
    return out


def generar(tok, asignatura_id, tipo, tema, leccion_id, fragment_ids,
            evitar, conceptos):
    r = requests.post(
        f"{BASE}/actividades/generar",
        headers=h(tok),
        json={
            "asignatura_id": asignatura_id,
            "tipo": tipo,
            "tema": tema,
            "leccion_id": leccion_id,
            "fragment_ids": fragment_ids,
            "evitar_preguntas": evitar,
            "conceptos_estudiados": conceptos,
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return None
    return r.json()


def responder(tok, actividad_id, respuesta):
    """Envía una respuesta y devuelve el ResultadoResponse (incluye
    respuesta_correcta y puntaje). None si falla."""
    r = requests.post(
        f"{BASE}/actividades/responder",
        headers=h(tok),
        json={"actividad_id": actividad_id, "respuesta": respuesta},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return None
    return r.json()


def verificar_respuestas_cortas(tok, asig, tema, leccion_id, frags, conceptos, n=5):
    """Genera n respuesta_corta, responde cada una para leer la respuesta
    esperada (oculta en /generar) y verifica: (a) <=6 palabras, (b) al enviar la
    propia respuesta esperada se acepta (puntaje alto)."""
    print(f"\n--- Respuesta corta: {n} actividades (largo de respuesta + aceptación) ---")
    largas = 0
    evitar = []
    for i in range(n):
        a = generar(tok, asig, "respuesta_corta", tema, leccion_id, frags, evitar, conceptos)
        if not a or a.get("tipo") != "respuesta_corta":
            print(f"   {i+1}. (no se generó respuesta_corta; tipo={a.get('tipo') if a else None})")
            continue
        preg = a["contenido"].get("pregunta")
        evitar.append(preg or "")
        res = responder(tok, a["id"], {"respuesta": "zzz_dummy"})
        esperada = (res or {}).get("respuesta_correcta", {}).get("respuesta_correcta", "")
        npal = len(esperada.split())
        # Reenviar la PROPIA respuesta esperada: debe aceptarse (puntaje alto).
        res2 = responder(tok, a["id"], {"respuesta": esperada})
        pts = (res2 or {}).get("puntaje", 0)
        flag = "  ⚠️ >6" if npal > 6 else ""
        if npal > 6:
            largas += 1
        print(f"   {i+1}. P: {preg}")
        print(f"       R esperada ({npal}p{flag}): '{esperada}'  | aceptación propia: {pts}")
    print(f"   → respuestas >6 palabras: {largas}")
    return largas


# ------------------------------- escenario ----------------------------------

def elegir_leccion(tok, libro_id, clave):
    """Una lección con rango de páginas real (o la fijada por LECCION_ID)."""
    r = requests.get(f"{BASE}/lecciones/ruta?libro_id={libro_id}",
                     headers=h(tok), timeout=TIMEOUT)
    r.raise_for_status()
    lecs = r.json()["lecciones"]
    forzada = LECCION_ID.get(clave)
    if forzada is not None:
        match = next((l for l in lecs if l["id"] == forzada), None)
        if match:
            return match
        print(f"  (LECCION_ID {forzada} no está en el libro {libro_id}; se elige automática)")
    con_pag = [l for l in lecs if l.get("paginas")]
    if not con_pag:
        return lecs[len(lecs) // 2]
    return con_pag[len(con_pag) // 3]  # ~primer tercio con contenido


def probar_libro(tok, clave, libro_id):
    asig = LIBROS[clave]["asignatura_id"]
    etq = LIBROS[clave]["etiqueta"]
    print(f"\n{'='*72}\n  {etq}  (libro_id={libro_id}, asignatura_id={asig})\n{'='*72}")

    lec = elegir_leccion(tok, libro_id, clave)
    leccion_id = lec["id"]
    tema = lec.get("tema_clave") or lec["nombre"]
    print(f"Lección elegida: #{leccion_id} '{lec['nombre']}' (págs {lec.get('paginas')}) tema='{tema}'")

    micro = micro_leccion(tok, leccion_id, 1)
    conceptos = conceptos_de_tarjetas(micro)
    frags = micro.get("fragment_ids", [])
    print(f"Micro-lección nivel 1: {len(micro.get('tarjetas', []))} tarjetas, "
          f"{len(conceptos)} conceptos, {len(frags)} fragment_ids")
    print("Conceptos estudiados (títulos):")
    for c in conceptos:
        print(f"   • {c.split(':')[0][:70]}")

    if MODO == "corta":
        largas = verificar_respuestas_cortas(tok, asig, tema, leccion_id, frags, conceptos, n=5)
        return {"corta_largas": largas}

    # --- A/B: una actividad SIN vs CON conceptos ---
    print("\n--- A/B (opcion_multiple): SIN conceptos vs CON conceptos ---")
    sin = generar(tok, asig, "opcion_multiple", tema, leccion_id, frags, [], [])
    con = generar(tok, asig, "opcion_multiple", tema, leccion_id, frags, [], conceptos)
    print("SIN conceptos:", texto_pregunta(sin["contenido"]) if sin else "(falló)")
    print("CON conceptos:", texto_pregunta(con["contenido"]) if con else "(falló)")

    # --- Test de repetición ---
    # NUEVO: con conceptos + memoria de preguntas persistida entre niveles.
    # BASELINE: sin conceptos + memoria reseteada por nivel (comportamiento viejo).
    print(f"\n--- Repetición a lo largo de {NIVELES} niveles (5 tipos c/u) ---")

    def correr(usar_conceptos, memoria_cross_nivel):
        """Simula al estudiante: para cada nivel, ve la micro-lección y genera 5
        actividades acumulando evitar_preguntas (como el frontend). Devuelve la
        lista de actividades como dicts {tipo, texto, contenido}."""
        acts = []
        evitar_persistente = []
        for nivel in range(1, NIVELES + 1):
            m = micro_leccion(tok, leccion_id, nivel)
            cs = conceptos_de_tarjetas(m) if usar_conceptos else []
            fs = m.get("fragment_ids", [])
            evitar = evitar_persistente if memoria_cross_nivel else []
            for tipo in TIPOS:
                a = generar(tok, asig, tipo, tema, leccion_id, fs, evitar, cs)
                if not a:
                    continue
                txt = texto_pregunta(a["contenido"])
                if txt:
                    acts.append({"tipo": a.get("tipo"), "texto": txt, "contenido": a["contenido"]})
                    evitar.append(txt)
        return acts

    print("  Corriendo BASELINE (sin conceptos, memoria por-nivel)…")
    base = correr(usar_conceptos=False, memoria_cross_nivel=False)
    print("  Corriendo NUEVO (con conceptos, memoria cross-nivel)…")
    nuevo = correr(usar_conceptos=True, memoria_cross_nivel=True)

    txt_base = [a["texto"] for a in base]
    txt_nuevo = [a["texto"] for a in nuevo]
    be, bc = contar_duplicados(txt_base)
    ne, nc = contar_duplicados(txt_nuevo)

    # Chequeo de los 3 bugs sobre el set NUEVO (el que verá el estudiante).
    completar_largas = [a for a in nuevo if a["tipo"] == "completar"
                        and n_palabras(a["contenido"].get("oracion")) > 20]
    completar_analogia = [a for a in nuevo if a["tipo"] == "completar"
                         and parece_analogia(a["contenido"].get("oracion") or "")]
    doble_neg = [a for a in nuevo if tiene_doble_negacion(a["texto"])]

    print(f"\n  BASELINE: {len(base)} preguntas → {be} exactas dup, {bc} casi-dups")
    print(f"  NUEVO   : {len(nuevo)} preguntas → {ne} exactas dup, {nc} casi-dups")
    print(f"  Bug 2 (completar >20 palabras): {len(completar_largas)}")
    print(f"  Bug 2 (completar con analogía inventada): {len(completar_analogia)}")
    print(f"  Bug 3 (doble negación): {len(doble_neg)}")
    if completar_largas:
        for a in completar_largas:
            print(f"     LARGA ({n_palabras(a['contenido'].get('oracion'))}p): {a['contenido'].get('oracion')}")
    if completar_analogia:
        for a in completar_analogia:
            print(f"     ANALOGÍA: {a['contenido'].get('oracion')}")
    if doble_neg:
        for a in doble_neg:
            print(f"     DOBLE-NEG: {a['texto']}")
    print("\n  Preguntas NUEVO (revisar alineación + repetición):")
    for i, a in enumerate(nuevo, 1):
        marca = "  [completar]" if a["tipo"] == "completar" else ""
        print(f"   {i:2}. ({a['tipo']}){marca} {a['texto']}")
    return {
        "baseline": (len(base), be, bc),
        "nuevo": (len(nuevo), ne, nc),
        "bug2_largas": len(completar_largas),
        "bug2_analogia": len(completar_analogia),
        "bug3_doble_neg": len(doble_neg),
    }


def main():
    au, ap = _admin_creds()
    admin = login(au, ap)
    print(f"[admin] login OK ({au})")

    # Crear estudiante temporal (grado_id=1) para no tocar estudiantes reales.
    # Username único por corrida: el soft-delete deja el username ocupado, así
    # que reusar uno fijo da 409 al recrear y 401 al loguear (login rechaza
    # inactivos). Un sufijo por timestamp evita esa colisión.
    import time
    uname = f"verif_conceptos_{int(time.time())}"
    pwd = "verif12345"
    r = requests.post(
        f"{BASE}/admin/estudiantes",
        headers=h(admin),
        json={"nombre": "Verif", "apellido": "Conceptos", "grado_id": 1,
              "username": uname, "password": pwd},
        timeout=TIMEOUT,
    )
    est_id = None
    if r.status_code in (200, 201):
        est_id = r.json().get("id")
        print(f"[admin] estudiante temporal creado id={est_id}")
    else:
        # Puede existir de una corrida previa: intentar login igual.
        print(f"[admin] no se creó ({r.status_code}: {r.text[:120]}); intento login directo")

    try:
        stok = login(uname, pwd)
        print(f"[est] login OK ({uname})")
    except Exception as e:
        print(f"ERROR: no se pudo obtener token de estudiante: {e}")
        return 1

    resultados = {}
    try:
        objetivos = ["ciencias", "matematicas"] if SOLO == "ambas" else [SOLO]
        libro_por_clave = {"ciencias": 3, "matematicas": 4}
        for clave in objetivos:
            resultados[clave] = probar_libro(stok, clave, libro_por_clave[clave])
    finally:
        if est_id is not None:
            requests.put(f"{BASE}/admin/estudiantes/{est_id}",
                         headers=h(admin), json={"activo": False}, timeout=TIMEOUT)
            print(f"\n[admin] estudiante temporal id={est_id} desactivado")

    print(f"\n{'#'*72}\n  RESUMEN\n{'#'*72}")
    for clave, r in resultados.items():
        if "corta_largas" in r:
            print(f"{clave}: respuesta_corta con >6 palabras = {r['corta_largas']}")
        else:
            print(f"{clave}: (dup: total, exactas, casi) baseline={r['baseline']} nuevo={r['nuevo']} | "
                  f"Bug2_largas={r['bug2_largas']} Bug2_analogia={r['bug2_analogia']} "
                  f"Bug3_doble_neg={r['bug3_doble_neg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
