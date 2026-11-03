"""
Verificación de consistencia estudiante ↔ docente (por HTTP).

Para cada estudiante real (activo, con grado) compara lo que ve el ESTUDIANTE
(inicio, mi progreso, ruta, ranking, perfil) contra lo que ve su DOCENTE (lista,
resumen, detalle, mapa de calor):

  - dominio general y por asignatura, temas practicados y su nivel
  - niveles aprobados (total y por asignatura), lección/nivel actual
  - puntos, racha actual y mejor racha (esta última no se expone al docente:
    se compara contra la BD)
  - cada celda del mapa de calor contra los resultados de actividades de esa
    lección en la BD
  - el promedio del Resumen contra la lista de estudiantes del docente

Imprime una tabla de discrepancias (estudiante, campo, valor estudiante, valor
docente) y sale con código != 0 si hay alguna.

Autenticación SIN contraseñas: firma JWT internamente con el SECRET_KEY de la
configuración (app/config.py). La BD se usa SOLO para leer la lista de usuarios
y la verdad de terreno del mapa de calor; todo lo comparado viaja por HTTP.
Por eso el SECRET_KEY y la BD deben ser los MISMOS del servidor de --base-url.

Ojo: GET /lecciones/ruta (y el detalle docente) crean las filas de
`progreso_leccion` que falten (igual que cuando el estudiante abre su ruta).
No cambia puntos, niveles ni dominio, pero sí escribe en la BD de destino.

Uso:
    local:      docker compose exec backend python scripts/verificar_consistencia.py
    producción: (con DATABASE_URL y SECRET_KEY de prod en el entorno)
                python scripts/verificar_consistencia.py --base-url https://<prod>
"""
import argparse
import asyncio
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Actividad, ResultadoActividad, RolUsuario, Usuario  # noqa: E402
from app.models.perfil_comprension import nivel_por_puntaje  # noqa: E402
from app.modules.auth.service import create_token_for_user  # noqa: E402


def js_round(x: float) -> int:
    """Math.round de JS (el front redondea así; round() de Python es bancario)."""
    return math.floor(x + 0.5)


def dominio(temas: list[dict]) -> int | None:
    """Mismo cálculo que `dominioDe` del front (promedio ponderado por actividades)."""
    tot = sum(t["total_actividades"] for t in temas)
    if tot == 0:
        return None
    return js_round(sum(t["puntaje_promedio"] * t["total_actividades"] for t in temas) / tot)


def resumen_ruta(ruta: dict) -> dict:
    """Lo que muestran inicio/Mi Ruta: niveles aprobados y lección/nivel actual."""
    lecs = ruta["lecciones"]
    actual = next((l for l in lecs if l["nivel_completado"] < 3), lecs[-1] if lecs else None)
    return {
        "niveles": sum(l["nivel_completado"] for l in lecs),
        "total_niveles": ruta["total_lecciones"] * 3,
        "actual": f"L{actual['orden']}·N{actual['nivel_actual']}" if actual else "—",
    }


def resumen_perfil(perfil: list[dict]) -> dict:
    """Dominio general, por asignatura y temas (con nivel) a partir del perfil."""
    por_asig = defaultdict(list)
    for t in perfil:
        por_asig[t["asignatura"]].append(t)
    return {
        "general": dominio(perfil),
        "asig": {a: dominio(ts) for a, ts in por_asig.items()},
        "temas": {(t["asignatura"], t["tema"]): (t["nivel"], t["puntaje_promedio"]) for t in perfil},
    }


class Verificador:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.discrepancias: list[tuple[str, str, object, object]] = []
        self.http = httpx.AsyncClient(base_url=self.base_url, timeout=60)

    def comparar(self, quien: str, campo: str, v_est, v_doc):
        if v_est != v_doc:
            self.discrepancias.append((quien, campo, v_est, v_doc))

    async def get(self, token: str, ruta: str):
        r = await self.http.get(ruta, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


async def cargar_bd():
    """Usuarios reales y verdad de terreno del mapa de calor (solo lectura)."""
    async with AsyncSessionLocal() as db:
        usuarios = (await db.execute(
            select(Usuario).where(Usuario.activo.is_(True))
        )).scalars().all()
        rows = (await db.execute(
            select(
                ResultadoActividad.estudiante_id,
                Actividad.leccion_id,
                func.avg(ResultadoActividad.puntaje),
                func.count(ResultadoActividad.id),
            )
            .join(Actividad, ResultadoActividad.actividad_id == Actividad.id)
            .where(Actividad.leccion_id.is_not(None))
            .group_by(ResultadoActividad.estudiante_id, Actividad.leccion_id)
        )).all()
    resultados = {(e, l): (float(p), n) for e, l, p, n in rows}
    return list(usuarios), resultados


async def main_async(base_url: str) -> int:
    usuarios, resultados_bd = await cargar_bd()
    estudiantes = [u for u in usuarios if u.rol == RolUsuario.estudiante and u.grado_id]
    docentes = {u.grado_id: u for u in usuarios if u.rol == RolUsuario.docente and u.grado_id}
    tokens = {u.id: create_token_for_user(u) for u in usuarios}
    v = Verificador(base_url)
    print(f"Verificando {len(estudiantes)} estudiantes contra {v.base_url}\n")

    # --- Lado docente, una vez por grado ---------------------------------
    por_grado: dict[int, dict] = {}
    for grado_id in sorted({e.grado_id for e in estudiantes}):
        doc = docentes.get(grado_id)
        if doc is None:
            v.discrepancias.append((f"grado {grado_id}", "docente", "—", "sin docente asignado"))
            continue
        t = tokens[doc.id]
        lista = await v.get(t, "/docente/estudiantes")
        stats = await v.get(t, "/docente/estadisticas")
        libros = await v.get(t, "/docente/libros")
        diag = {}
        for libro in libros:
            if libro["total_lecciones"]:
                d = await v.get(t, f"/docente/diagnostico?libro_id={libro['id']}")
                diag[d["asignatura"]] = {f["estudiante_id"]: f for f in d["estudiantes"]}
        por_grado[grado_id] = {
            "token": t, "lista": {e["id"]: e for e in lista}, "stats": stats, "diag": diag,
        }

        # Resumen vs lista: mismos estudiantes (los activos del grado) y mismo promedio.
        quien = f"grado {grado_id} (Resumen)"
        activos = sorted(e.id for e in estudiantes if e.grado_id == grado_id)
        v.comparar(quien, "estudiantes en la lista", activos, sorted(e["id"] for e in lista))
        v.comparar(quien, "total_estudiantes", len(activos), stats["total_estudiantes"])
        denom = stats["total_lecciones"] * 3 * len(lista)
        promedio_lista = round(sum(e["niveles_aprobados"] for e in lista) / denom * 100, 1) if denom else 0.0
        v.comparar(quien, "promedio_progreso (lista vs Resumen)", promedio_lista, stats["promedio_progreso"])

    # --- Por estudiante ----------------------------------------------------
    for i, est in enumerate(estudiantes, 1):
        quien = f"{est.username} ({est.id})"
        if sys.stdout.isatty():
            print(f"  [{i}/{len(estudiantes)}] {quien}", end="\r", flush=True)
        g = por_grado.get(est.grado_id)
        if g is None:
            continue
        t = tokens[est.id]

        # Estudiante
        perfil_e = resumen_perfil(await v.get(t, "/actividades/perfil"))
        libros_e = await v.get(t, "/lecciones/mis-libros")
        rutas_e = {}
        for libro in libros_e:
            ruta = await v.get(t, f"/lecciones/ruta?libro_id={libro['libro_id']}")
            rutas_e[ruta["asignatura"]] = ruta
        racha_e = await v.get(t, "/gamificacion/racha")
        ranking = await v.get(t, "/gamificacion/ranking")
        yo = ranking["ranking"][ranking["mi_posicion"] - 1] if ranking["mi_posicion"] else None

        # Docente
        fila = g["lista"].get(est.id)
        if fila is None:
            v.comparar(quien, "aparece en la lista docente", "sí", "no")
            continue
        detalle = await v.get(g["token"], f"/docente/estudiantes/{est.id}/detalle")
        perfil_d = resumen_perfil(detalle["perfil"])
        rutas_d = {r["asignatura"]: r for r in detalle["rutas"]}

        # Puntos y racha
        v.comparar(quien, "puntos (ranking vs lista)", yo and yo["puntos_totales"], fila["puntos_totales"])
        v.comparar(quien, "puntos (ranking vs detalle)", yo and yo["puntos_totales"], detalle["puntos_totales"])
        v.comparar(quien, "racha actual (lista)", racha_e["racha_actual"], fila["racha_actual"])
        v.comparar(quien, "racha actual (detalle)", racha_e["racha_actual"], detalle["racha_actual"])
        v.comparar(quien, "racha actual (ranking)", racha_e["racha_actual"], yo and yo["racha_actual"])
        v.comparar(quien, "mejor racha (vs BD)", racha_e["mejor_racha"], est.mejor_racha)

        # Dominio y temas
        v.comparar(quien, "dominio general", perfil_e["general"], perfil_d["general"])
        for a in sorted(set(perfil_e["asig"]) | set(perfil_d["asig"])):
            v.comparar(quien, f"dominio {a}", perfil_e["asig"].get(a), perfil_d["asig"].get(a))
            temas_e = {k: x for k, x in perfil_e["temas"].items() if k[0] == a}
            temas_d = {k: x for k, x in perfil_d["temas"].items() if k[0] == a}
            v.comparar(quien, f"temas practicados {a}", len(temas_e), len(temas_d))
            for k in sorted(set(temas_e) | set(temas_d)):
                v.comparar(quien, f"tema '{k[1]}' (nivel, puntaje)", temas_e.get(k), temas_d.get(k))

        # Niveles aprobados y lección/nivel actual, por asignatura
        niveles_e = sum(resumen_ruta(r)["niveles"] for r in rutas_e.values())
        v.comparar(quien, "niveles aprobados (rutas vs lista)", niveles_e, fila["niveles_aprobados"])
        v.comparar(quien, "niveles aprobados (rutas vs ranking)", niveles_e, yo and yo["niveles_aprobados"])
        lecciones_e = sum(r["total_lecciones"] for r in rutas_e.values())
        v.comparar(quien, "lecciones de la ruta (estudiante vs Resumen)", lecciones_e, g["stats"]["total_lecciones"])
        for a in sorted(set(rutas_e) | set(rutas_d)):
            re_ = resumen_ruta(rutas_e[a]) if a in rutas_e else None
            rd_ = resumen_ruta(rutas_d[a]) if a in rutas_d else None
            for campo in ("niveles", "total_niveles", "actual"):
                v.comparar(quien, f"{a}: {campo}", re_ and re_[campo], rd_ and rd_[campo])

            # Mapa de calor: cada celda vs resultados de actividades de esa lección.
            fila_diag = g["diag"].get(a, {}).get(est.id)
            if fila_diag is None:
                v.comparar(quien, f"{a}: fila en mapa de calor", "sí", "no")
                continue
            orden = {l["id"]: l["orden"] for l in rutas_e.get(a, {"lecciones": []})["lecciones"]}
            for celda in fila_diag["celdas"]:
                prom, n = resultados_bd.get((est.id, celda["leccion_id"]), (None, 0))
                esperado = (nivel_por_puntaje(prom), round(prom, 1), n) if prom is not None else ("sin_datos", None, 0)
                mostrado = (celda["nivel"], celda["puntaje_promedio"], celda["total_actividades"])
                v.comparar(quien, f"{a}: mapa L{orden.get(celda['leccion_id'], '?')} (nivel, prom, n)",
                           esperado, mostrado)

    await v.http.aclose()
    if sys.stdout.isatty():
        print(" " * 60, end="\r")

    if not v.discrepancias:
        print(f"✅ Sin discrepancias ({len(estudiantes)} estudiantes).")
        return 0
    print(f"❌ {len(v.discrepancias)} discrepancias:\n")
    filas = [("Estudiante", "Campo", "Valor estudiante", "Valor docente")] + [
        (q, c, str(a), str(b)) for q, c, a, b in v.discrepancias
    ]
    anchos = [min(48, max(len(f[i]) for f in filas)) for i in range(4)]
    for j, f in enumerate(filas):
        print(" | ".join(x[:anchos[i]].ljust(anchos[i]) for i, x in enumerate(f)))
        if j == 0:
            print("-+-".join("-" * w for w in anchos))
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL del backend a verificar")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args.base_url)))


if __name__ == "__main__":
    main()
