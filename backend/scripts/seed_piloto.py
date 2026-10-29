"""
Seed del piloto (1–30 de septiembre de 2026) a partir de datos/datos_simulados_cap5.csv.

Reproduce, sobre las cuentas REALES de estudiantes (no crea ni modifica cuentas),
el uso que describe cada fila del CSV, llamando a las FUNCIONES DE SERVICIO reales
con la hora congelada (freezegun) en la fecha simulada de cada evento:
  - consultas   -> chat.service.procesar_pregunta (pipeline RAG + DeepSeek real),
  - actividades -> una parte en la RUTA (lecciones.service.iniciar_leccion -> 5 x
                   actividades.service.responder_actividad -> lecciones.service.completar_nivel,
                   con la regla real de 4 de 5) y el resto como PRÁCTICA POR LECCIÓN
                   (crear_actividad con leccion_id + responder_actividad, sin completar_nivel)
                   en 8–12 lecciones repartidas por los dos libros: septiembre es el mes de
                   repaso para las evaluaciones finales,
  - las consultas del chat salen de las mismas lecciones que practica cada estudiante,
  - perfil de comprensión, racha y puntos salen de esas mismas funciones.

Definiciones (las usa también verificar_seed.py):
  - sesión = día (hora de Guatemala) con al menos una conversación o una práctica;
  - tasa de acierto = promedio de puntaje de sus resultados;
  - dominio inicio/final = nivel (≥80 domina, ≥50 en proceso, <50 necesita refuerzo)
    del promedio de su primer / último cuarto de actividades (entre 2 y 5: ventana()).
    Con 5 fijas, 7 filas cortas (7–10 actividades) eran imposibles: las dos ventanas
    cubrían casi todas sus actividades.
El planificador busca, por estudiante, una secuencia de puntajes que cumpla a la
vez la tasa (±2), el dominio de inicio y el final; con tendencia creciente salvo en
las filas incompatibles con ella (opción A: curva no creciente, marcada en el mapeo).
El puntaje parcial solo existe en "ordenar" (posiciones correctas / total), así que
el banco de 5 actividades de cada lección lleva dos de ordenar para ajustar la tasa.

Uso (dentro del contenedor; requirements-dev.txt instalado):
  docker cp datos/datos_simulados_cap5.csv "$(docker compose ps -q backend)":/tmp/
  python scripts/seed_piloto.py --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv --dry-run
  python scripts/seed_piloto.py --csv ... --mapeo ... [--grado 7] [--max-usd 3]
  python scripts/seed_piloto.py --borrar        # datos del piloto de los estudiantes reales; no toca cuentas
Reanudable: un estudiante ya sembrado completo se salta; uno a medias se borra y se rehace.
"""
import argparse
import asyncio
import csv
import itertools
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import delete, func, select, update  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.actividad import Actividad, ResultadoActividad, TipoActividad  # noqa: E402
from app.models.conversacion import Conversacion  # noqa: E402
from app.models.fragmento import Fragmento  # noqa: E402
from app.models.grado import Grado  # noqa: E402
from app.models.leccion import Leccion  # noqa: E402
from app.models.libro import EstadoIndexacion, LibroTexto  # noqa: E402
from app.models.mensaje import Mensaje, RolMensaje  # noqa: E402
from app.models.perfil_comprension import PerfilComprension, nivel_por_puntaje  # noqa: E402
from app.models.progreso_leccion import EstadoLeccion, ProgresoLeccion  # noqa: E402
from app.models.usuario import RolUsuario, Usuario  # noqa: E402
from costos_llm import Presupuesto, PresupuestoAgotado, agregar_argumento_max_usd  # noqa: E402

ZONA = ZoneInfo("America/Guatemala")
INICIO_PILOTO = date(2026, 9, 1)
DIAS_PILOTO = 30
VENTANA_UTC = (datetime(2026, 9, 1, tzinfo=ZONA), datetime(2026, 10, 1, tzinfo=ZONA))
SEMILLA = 2026
CIENCIAS, MATEMATICAS = 1, 2
ACTIVIDADES_POR_RONDA = 5
APROBADA = 70          # el web cuenta como aprobada una actividad con puntaje >= 70
FRACCION_APROBAR = 0.8  # lecciones.service: ceil(0.8 · total) aprobadas para pasar de nivel
TIPOS_RONDA = [TipoActividad.opcion_multiple, TipoActividad.ordenar, TipoActividad.verdadero_falso,
               TipoActividad.ordenar, TipoActividad.completar]
SLOTS_ORDENAR = (1, 3)  # posiciones de "ordenar" en la ronda: las únicas con puntaje parcial


def valores_ordenar(n: int) -> list[int]:
    """Puntajes posibles de un "ordenar" de n elementos: round(100·k/n), k ≠ n-1 (imposible)."""
    return [round(100 * k / n) for k in range(n + 1) if k != n - 1]
LECCIONES_PRACTICA_POR_LIBRO = 10   # por grado y asignatura, repartidas por todo el libro
LECCIONES_POR_ESTUDIANTE = (8, 12)   # lecciones de práctica de cada estudiante (si le alcanzan las actividades)
RONDAS_RUTA_EXTRA_DESDE = 21         # con más actividades que esto, dos rondas de ruta en vez de una
POOL_PATH = Path(__file__).parent / "debug" / "seed_piloto_pool.json"
CUENTAS_DE_PRUEBA = {"carlos"}  # activo en 4to; lo usan las pruebas automáticas, no es de los 87

# Grados del CSV -> grado_id (equivalencias del colegio) y movimientos de filas acordados.
GRADO_CSV = {"4to Primaria": 1, "5to Primaria": 2, "6to Primaria": 3,
             "1ro Basico": 5, "2do Basico": 6, "3ro Basico": 7}
MOVER_FILAS = {30: 1, 31: 1, 62: 5, 67: 5}  # 6to -> 4to y 9no -> 7mo, mismo nivel y perfil típico
CUENTAS_DEMO = {66: "jgarcia", 11: "naldana", 34: "layala", 61: "cpaz"}
ESTUDIANTES_ESPERADOS = {1: 22, 2: 19, 3: 9, 5: 15, 6: 12, 7: 10}

# Estimación de tokens por llamada (para --dry-run; la corrida real registra el uso real).
TOKENS = {"chat": (3000, 350), "actividad": (2500, 450), "preguntas": (1500, 500)}
LLAMADAS_POR_ACTIVIDAD = 1.5  # generar_actividad reintenta / verifica a veces


# ---------------------------------------------------------------- planificación pura

RANGO_NIVEL = {"Necesita refuerzo": (0, 49.99), "En proceso": (50, 79.99), "Domina": (80, 100)}
MARGEN = 2.0  # holgura dentro del rango, por el ajuste fino de "ordenar" en la corrida real


def nivel_csv(puntaje: float) -> str:
    return {"domina": "Domina", "en_proceso": "En proceso", "refuerzo": "Necesita refuerzo"}[nivel_por_puntaje(puntaje)]


def _fuera(x: float, nivel: str, margen: float = MARGEN) -> float:
    lo, hi = RANGO_NIVEL[nivel]
    lo = lo + margen if lo > 0 else lo
    hi = hi - margen if hi < 100 else hi
    return max(0.0, lo - x) + max(0.0, x - hi)


def ventana(actividades: int) -> int:
    """Nº de actividades del inicio y del final con que se mide el dominio."""
    return max(2, min(ACTIVIDADES_POR_RONDA, actividades // 4)) if actividades >= 2 else 1


def tamanos_rondas(actividades: int) -> list[int]:
    n, resto = divmod(actividades, ACTIVIDADES_POR_RONDA)
    return [ACTIVIDADES_POR_RONDA] * n + ([resto] if resto else [])


def compatible_creciente(tasa: float, inicio: str, final: str) -> bool:
    """Con tendencia creciente, la media global queda entre la de la 1ª y la última ventana."""
    return RANGO_NIVEL[inicio][0] <= tasa <= RANGO_NIVEL[final][1]


def planificar_puntajes(actividades: int, tasa: float, inicio: str, final: str, rng: random.Random,
                        slots: dict[int, list[int]] | None = None):
    """Secuencia de puntajes: 0/100, o en las posiciones de "ordenar" (`slots`: posición ->
    puntajes posibles) uno de esos valores. Sin `slots`, rondas de 5 con ordenar de 5 elementos."""
    if slots is None:
        slots = {}
        for r, tam in enumerate(tamanos_rondas(actividades)):
            slots.update({r * ACTIVIDADES_POR_RONDA + j: valores_ordenar(5) for j in SLOTS_ORDENAR if j < tam})
    w = ventana(actividades)
    creciente = compatible_creciente(tasa, inicio, final)
    lo_i, hi_i = RANGO_NIVEL[inicio]
    lo_f, hi_f = RANGO_NIVEL[final]
    a = min(max(tasa - 12, lo_i + 5), hi_i - 5)
    b = min(max(tasa + 12, lo_f + 5), hi_f - 5)
    tendencia = [a + (b - a) * i / max(1, actividades - 1) for i in range(actividades)]

    def penal(s):
        p = 1000 * (_fuera(sum(s[:w]) / w, inicio) + _fuera(sum(s[-w:]) / w, final))
        p += 300 * max(0.0, abs(sum(s) / len(s) - tasa) - 1.0)
        if creciente:
            p += 0.02 * sum((x - t) ** 2 for x, t in zip(s, tendencia)) / len(s)
        return p

    mejor, pm = None, math.inf
    for _ in range(8):  # reinicios: la búsqueda local se atasca en algunas filas cortas
        s = [100 if rng.random() * 100 < t else 0 for t in tendencia]
        ps = penal(s)
        for _ in range(4000):
            i = rng.randrange(actividades)
            opciones = slots.get(i, [0, 100])
            nuevo = list(s)
            nuevo[i] = rng.choice([v for v in opciones if v != s[i]])
            pn = penal(nuevo)
            if pn <= ps:
                s, ps = nuevo, pn
        if ps < pm:
            mejor, pm = s, ps

    def cumple(s):
        return (_fuera(sum(s[:w]) / w, inicio, 0) == 0 and _fuera(sum(s[-w:]) / w, final, 0) == 0
                and abs(sum(s) / len(s) - tasa) <= 2.0)

    if not cumple(mejor) and actividades <= 12:  # respaldo exacto: búsqueda exhaustiva
        valores = [slots.get(i, [0, 100]) for i in range(actividades)]
        candidatos = [list(c) for c in itertools.product(*valores) if cumple(c)]
        if candidatos:
            mejor = min(candidatos, key=penal)
    return mejor, cumple(mejor), creciente


def fechas_sesiones(n: int, rng: random.Random) -> list[datetime]:
    """n días distintos de septiembre (fines de semana con menos peso), hora 15:00–20:30 GT."""
    dias = [INICIO_PILOTO + timedelta(d) for d in range(DIAS_PILOTO)]
    pesos = {d: (0.25 if d.weekday() >= 5 else 1.0) for d in dias}
    elegidos = []
    while len(elegidos) < n:
        d = rng.choices([d for d in dias if d not in elegidos], weights=[pesos[d] for d in dias if d not in elegidos])[0]
        elegidos.append(d)
    return [datetime.combine(d, time(15, 0), ZONA) + timedelta(minutes=rng.randrange(0, 330))
            for d in sorted(elegidos)]


def lecciones_de_practica(total: int) -> list[int]:
    """Órdenes de las lecciones de práctica de un libro, repartidas entre la 2ª y la penúltima
    (la última de las Guías es un cuento o la bibliografía)."""
    n = LECCIONES_PRACTICA_POR_LIBRO
    return sorted({round(2 + i * (total - 3) / (n - 1)) for i in range(n)})


def plan_bloques(actividades: int, elegidas: list[tuple[int, int]], rng: random.Random) -> list[dict]:
    """Bloques en orden temporal. Ruta: rondas de 5 (la primera al inicio, alternando asignatura).
    Práctica: un bloque por lección elegida (asignatura, orden), de 1–5 actividades tomadas del
    banco de 5 de esa lección desde `offset` (la sesión de práctica que se deja a medias)."""
    n_ruta = (actividades >= ACTIVIDADES_POR_RONDA) + (actividades >= RONDAS_RUTA_EXTRA_DESDE)
    resto = actividades - n_ruta * ACTIVIDADES_POR_RONDA
    lecciones = elegidas[:min(len(elegidas), resto)]
    tams = [resto // len(lecciones) + (i < resto % len(lecciones)) for i in range(len(lecciones))]
    assert all(t <= ACTIVIDADES_POR_RONDA for t in tams), "más actividades que el banco de la lección"
    practica = [{"tipo": "practica", "asignatura": a, "orden": o, "tam": t,
                 "offset": rng.randrange(ACTIVIDADES_POR_RONDA - t + 1)} for (a, o), t in zip(lecciones, tams)]
    rng.shuffle(practica)
    primera = rng.choice((CIENCIAS, MATEMATICAS))
    bloques = practica
    for i in range(n_ruta):
        ruta = {"tipo": "ruta", "asignatura": primera if i % 2 == 0 else CIENCIAS + MATEMATICAS - primera,
                "orden": None, "tam": ACTIVIDADES_POR_RONDA, "offset": 0}
        bloques.insert(i * (len(bloques) + 1) // n_ruta, ruta)
    return bloques


def slots_ordenar(bloques: list[dict]) -> dict[int, list[int]]:
    """Posiciones globales de las actividades de ordenar (las únicas con puntaje parcial) ->
    puntajes posibles, suponiendo 5 elementos (bancos aún no generados)."""
    slots, k = {}, 0
    for b in bloques:
        slots.update({k + j: valores_ordenar(5) for j in range(b["tam"]) if b["offset"] + j in SLOTS_ORDENAR})
        k += b["tam"]
    return slots


def plan_sesiones(sesiones: int, consultas: int, bloques: list[dict], elegidas: list[tuple[int, int]],
                  rng: random.Random):
    """Reparte bloques y consultas en las sesiones; cada sesión recibe al menos uno de los dos.
    Las consultas de una sesión son sobre la lección de su primer bloque (o, si no practica ese
    día, sobre una de sus lecciones elegidas). Devuelve [{fecha, consultas, chat, bloques}] o None."""
    bloques = [dict(b) for b in bloques]
    # Más sesiones que bloques + consultas: se parten bloques (práctica que se deja a medias
    # y se retoma otro día), primero los de práctica; la mitad 2ª sigue en el mismo banco.
    while sesiones > len(bloques) + consultas and any(b["tam"] > 1 for b in bloques):
        i = max(range(len(bloques)), key=lambda i: (bloques[i]["tam"] > 1, bloques[i]["tipo"] == "practica",
                                                     bloques[i]["tam"], i))
        b = bloques[i]
        a = b["tam"] - b["tam"] // 2
        bloques[i:i + 1] = [dict(b, tam=a), dict(b, tam=b["tam"] - a, offset=b["offset"] + a)]
    if sesiones > len(bloques) + consultas:
        return None
    plan = [{"bloques": [], "consultas": 0} for _ in range(sesiones)]
    for i, b in enumerate(bloques):
        plan[min(sesiones - 1, i * sesiones // len(bloques))]["bloques"].append(b)
    vacias = [p for p in plan if not p["bloques"]]
    for p in vacias[:consultas]:
        p["consultas"] += 1
    for _ in range(consultas - min(consultas, len(vacias))):
        rng.choice(plan)["consultas"] += 1
    for p, f in zip(plan, fechas_sesiones(sesiones, rng)):
        p["fecha"] = f
        if p["bloques"]:
            b = p["bloques"][0]
            p["chat"] = (b["asignatura"], b["orden"])  # orden None = la lección actual de la ruta
        else:
            p["chat"] = rng.choice(elegidas) if elegidas else (rng.choice((CIENCIAS, MATEMATICAS)), None)
    return plan


def simular_progreso(estado: dict, puntajes: list[int]) -> tuple[int, int]:
    """Aplica una ronda a {orden, nivel} con las reglas de completar_nivel; devuelve
    (orden, nivel) en el que se practicó."""
    practicado = (estado["orden"], estado["nivel"])
    if len(puntajes) == ACTIVIDADES_POR_RONDA:
        aprobadas = sum(p >= APROBADA for p in puntajes)
        if aprobadas >= math.ceil(FRACCION_APROBAR * len(puntajes)):
            if estado["nivel"] == 3:
                if estado["orden"] < estado["total"]:
                    estado["orden"], estado["nivel"] = estado["orden"] + 1, 1
            else:
                estado["nivel"] += 1
    return practicado


# ---------------------------------------------------------------- mapeo CSV -> cuentas reales

def leer_csv(ruta: Path) -> list[dict]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    for r in filas:
        r["fila"] = int(r["estudiante"])
        for k in ("sesiones", "actividades", "consultas"):
            r[k] = int(r[k])
        r["tasa_acierto"] = float(r["tasa_acierto"])
        r["grado_id"] = MOVER_FILAS.get(r["fila"], GRADO_CSV[r["grado"]])
    return filas


async def estudiantes_reales(db) -> dict[int, list[Usuario]]:
    filas = (await db.execute(
        select(Usuario).where(Usuario.rol == RolUsuario.estudiante, Usuario.activo.is_(True),
                              Usuario.username.not_in(CUENTAS_DE_PRUEBA)).order_by(Usuario.username)
    )).scalars().all()
    por_grado = defaultdict(list)
    for u in filas:
        por_grado[u.grado_id].append(u)
    for g, n in ESTUDIANTES_ESPERADOS.items():
        if len(por_grado[g]) != n:
            sys.exit(f"grado {g}: se esperaban {n} estudiantes reales activos, hay {len(por_grado[g])}")
    return por_grado


def mapear(filas: list[dict], por_grado: dict[int, list[Usuario]]) -> dict[int, Usuario]:
    rng = random.Random(SEMILLA)
    por_username = {u.username: u for us in por_grado.values() for u in us}
    asignado = {fila: por_username[u] for fila, u in CUENTAS_DEMO.items()}
    for g, us in sorted(por_grado.items()):
        libres = [u for u in us if u not in asignado.values()]
        rng.shuffle(libres)
        pendientes = [r for r in filas if r["grado_id"] == g and r["fila"] not in asignado]
        if len(pendientes) > len(libres):
            sys.exit(f"grado {g}: {len(pendientes)} filas y solo {len(libres)} estudiantes libres")
        for r, u in zip(pendientes, libres):
            asignado[r["fila"]] = u
    for r in filas:
        if asignado[r["fila"]].grado_id != r["grado_id"]:
            sys.exit(f"fila {r['fila']}: grado del estudiante ≠ grado asignado")
    return asignado


# ---------------------------------------------------------------- acceso a BD

async def libros_y_lecciones(db) -> dict[tuple[int, int], dict]:
    """(grado_id, asignatura_id) -> {libro, lecciones: {orden: Leccion}} del libro más reciente."""
    libros = (await db.execute(
        select(LibroTexto).where(LibroTexto.estado_indexacion == EstadoIndexacion.completado)
        .order_by(LibroTexto.fecha_subida)
    )).scalars().all()
    out = {}
    for lb in libros:
        lecc = (await db.execute(select(Leccion).where(Leccion.libro_id == lb.id))).scalars().all()
        if lecc:
            out[(lb.grado_id, lb.asignatura_id)] = {"libro": lb, "lecciones": {l.orden: l for l in lecc}}
    return out


def _en_ventana(col):
    return col.between(VENTANA_UTC[0], VENTANA_UTC[1])


async def contar_piloto(db, estudiante_id: int) -> dict:
    """Conteos del piloto de un estudiante (mismas definiciones que verificar_seed.py)."""
    convs = (await db.execute(select(Conversacion).where(
        Conversacion.estudiante_id == estudiante_id, _en_ventana(Conversacion.fecha_creacion)))).scalars().all()
    consultas = (await db.execute(select(func.count()).select_from(Mensaje).join(Conversacion).where(
        Conversacion.estudiante_id == estudiante_id, Mensaje.rol == RolMensaje.usuario,
        _en_ventana(Mensaje.fecha_creacion)))).scalar()
    res = (await db.execute(select(ResultadoActividad).where(
        ResultadoActividad.estudiante_id == estudiante_id, _en_ventana(ResultadoActividad.fecha))
        .order_by(ResultadoActividad.fecha, ResultadoActividad.id))).scalars().all()
    dias = {c.fecha_creacion.astimezone(ZONA).date() for c in convs} | {r.fecha.astimezone(ZONA).date() for r in res}
    puntajes = [r.puntaje for r in res]
    w = ventana(len(puntajes))
    return {
        "sesiones": len(dias), "conversaciones": len(convs), "consultas": consultas, "actividades": len(res),
        "tasa": sum(puntajes) / len(puntajes) if puntajes else None,
        "dominio_inicio": nivel_csv(sum(puntajes[:w]) / w) if puntajes else None,
        "dominio_final": nivel_csv(sum(puntajes[-w:]) / w) if puntajes else None,
    }


async def borrar_estudiante(db, estudiante_id: int) -> None:
    """Borra TODOS los datos de uso del estudiante (no la cuenta) y reinicia su gamificación."""
    await db.execute(delete(Conversacion).where(Conversacion.estudiante_id == estudiante_id))
    await db.execute(delete(ResultadoActividad).where(ResultadoActividad.estudiante_id == estudiante_id))
    await db.execute(delete(PerfilComprension).where(PerfilComprension.estudiante_id == estudiante_id))
    await db.execute(delete(ProgresoLeccion).where(ProgresoLeccion.estudiante_id == estudiante_id))
    await db.execute(update(Usuario).where(Usuario.id == estudiante_id).values(
        racha_actual=0, mejor_racha=0, ultima_actividad=None, puntos_totales=0))
    await db.commit()


async def borrar_actividades_estudiante(db, estudiante_id: int) -> None:
    """Como borrar_estudiante pero conserva las conversaciones (para rehacer solo las actividades)."""
    await db.execute(delete(ResultadoActividad).where(ResultadoActividad.estudiante_id == estudiante_id))
    await db.execute(delete(PerfilComprension).where(PerfilComprension.estudiante_id == estudiante_id))
    await db.execute(delete(ProgresoLeccion).where(ProgresoLeccion.estudiante_id == estudiante_id))
    await db.execute(update(Usuario).where(Usuario.id == estudiante_id).values(
        racha_actual=0, mejor_racha=0, ultima_actividad=None, puntos_totales=0))
    await db.commit()


def cuadra(h: dict, r: dict) -> bool:
    """Mismo criterio que verificar_seed.py para una fila."""
    return (all(h[k] == r[k] for k in ("sesiones", "consultas", "actividades", "dominio_inicio", "dominio_final"))
            and h["tasa"] is not None and abs(h["tasa"] - r["tasa_acierto"]) <= 2)


async def tipos_del_pool(db, pool: dict) -> dict[str, list]:
    """Clave del banco -> por actividad, sus puntajes posibles si es de ordenar, o None."""
    ids = [i for v in pool["actividades"].values() for i in v]
    acts = {a.id: a for a in (await db.execute(select(Actividad).where(Actividad.id.in_(ids)))).scalars()}

    def valores(a):
        orden = (a.respuesta_correcta or {}).get("orden_correcto")
        return valores_ordenar(len(orden)) if a.tipo == TipoActividad.ordenar and orden else None
    return {clave: [valores(acts[i]) for i in v if i in acts] for clave, v in pool["actividades"].items()}


# ---------------------------------------------------------------- corrida real

def _cargar_pool() -> dict:
    return json.loads(POOL_PATH.read_text()) if POOL_PATH.exists() else {"actividades": {}, "preguntas": {}}


def _guardar_pool(pool: dict) -> None:
    POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=1))


async def _texto_leccion(db, leccion: Leccion) -> str:
    from app.modules.rag.search import es_ejercicio_del_libro
    nums = [int(x) for x in (leccion.paginas or "").replace("-", " ").split() if x.isdigit()]
    if not nums:
        return ""
    frags = (await db.execute(select(Fragmento.contenido_texto).where(
        Fragmento.libro_id == leccion.libro_id, Fragmento.numero_pagina.between(min(nums), max(nums)))
        .order_by(Fragmento.numero_pagina))).scalars().all()
    return " ".join(t for t in frags if not es_ejercicio_del_libro(t))[:1500]


async def preguntas_de_leccion(db, pool, leccion: Leccion, grado: str, asignatura: str, presupuesto) -> list[str]:
    from app.llm.client import llm_client
    clave = str(leccion.id)
    if clave not in pool["preguntas"]:
        presupuesto.verificar()
        contenido = await _texto_leccion(db, leccion)
        mensajes = [
            {"role": "system", "content": "Generas preguntas realistas que un estudiante guatemalteco le haría a su tutor virtual. Responde SOLO JSON."},
            {"role": "user", "content": (
                f"Grado: {grado}. Asignatura: {asignatura}. Lección: {leccion.nombre} (tema: {leccion.tema_clave}).\n"
                f"Contenido del libro:\n{contenido}\n\n"
                "Escribe 10 preguntas cortas y variadas (dudas, definiciones, ejemplos, '¿por qué…?'), "
                "como las escribiría un estudiante de ese grado, que se respondan con ese contenido. "
                'Formato: {"preguntas": ["...", "..."]}'
            )},
        ]
        datos = await asyncio.to_thread(llm_client.generate_json, mensajes, 700, "chat")
        preguntas = [p.strip() for p in (datos or {}).get("preguntas", []) if isinstance(p, str) and p.strip()]
        if not preguntas:
            raise RuntimeError(f"no se pudieron generar preguntas para la lección {leccion.id}")
        pool["preguntas"][clave] = preguntas
        _guardar_pool(pool)
    return pool["preguntas"][clave]


async def actividades_de_ronda(db, pool, leccion: Leccion, nivel: int | str, asignatura_id: int, estudiante: Usuario,
                               presupuesto, hasta: int = ACTIVIDADES_POR_RONDA) -> list[Actividad]:
    """Las primeras `hasta` actividades del banco de (lección, nivel) — nivel "p" = práctica por
    lección —; genera las que falten la primera vez que se necesitan."""
    from app.modules.actividades.service import crear_actividad
    clave = f"{leccion.id}:{nivel}"
    ids = pool["actividades"].get(clave, [])
    actividades = [a for a in (await db.execute(select(Actividad).where(Actividad.id.in_(ids)))).scalars()]
    actividades.sort(key=lambda a: ids.index(a.id))
    while len(actividades) < hasta:
        presupuesto.verificar()
        tipo = TIPOS_RONDA[len(actividades)]
        act = None
        for _ in range(3):
            act = await crear_actividad(db, asignatura_id, tipo, estudiante, leccion_id=leccion.id,
                                        evitar_preguntas=[json.dumps(a.contenido, ensure_ascii=False) for a in actividades])
            if act is not None:
                break
        if act is None:
            raise RuntimeError(f"no se pudo generar actividad {tipo.value} para {clave}")
        actividades.append(act)
        pool["actividades"][clave] = [a.id for a in actividades]
        _guardar_pool(pool)
    return actividades


def respuesta_para(act: Actividad, objetivo: int) -> tuple[dict, int]:
    """Respuesta que obtiene (lo más cerca posible) el puntaje objetivo; devuelve (respuesta, esperado)."""
    rc, c = act.respuesta_correcta, act.contenido
    acierta = objetivo >= 50
    if act.tipo == TipoActividad.ordenar and rc.get("orden_correcto"):
        orden = list(rc["orden_correcto"])
        n = len(orden)
        posibles = [k for k in range(n + 1) if k != n - 1]  # n-1 fijas es imposible
        k = min(posibles, key=lambda k: abs(100 * k / n - objetivo))
        resto = orden[k:]
        resto = resto[1:] + resto[:1] if len(resto) > 1 else resto  # rotación: ninguna fija
        return {"orden": orden[:k] + resto}, round(100 * k / n)
    if act.tipo == TipoActividad.verdadero_falso:
        correcta = rc.get("respuesta_correcta")
        if isinstance(correcta, str):
            correcta = correcta.lower() in ("true", "verdadero", "v", "si", "sí")
        return {"respuesta": correcta if acierta else not correcta}, 100 if acierta else 0
    correcta = str(rc.get("respuesta_correcta", ""))
    if acierta:
        return {"respuesta": correcta}, 100
    if act.tipo == TipoActividad.opcion_multiple:
        otras = [o for o in (c.get("opciones") or []) if str(o).strip().lower() != correcta.strip().lower()]
        return {"respuesta": otras[0] if otras else "no sé"}, 0
    return {"respuesta": "no sé"}, 0


async def leccion_actual(db, libro_lecciones: dict, estudiante_id: int) -> tuple[Leccion, int]:
    lecciones = libro_lecciones["lecciones"]
    progresos = {p.leccion_id: p for p in (await db.execute(select(ProgresoLeccion).where(
        ProgresoLeccion.estudiante_id == estudiante_id,
        ProgresoLeccion.leccion_id.in_([l.id for l in lecciones.values()])))).scalars()}
    for orden in sorted(lecciones):
        p = progresos.get(lecciones[orden].id)
        if p is None or p.estado != EstadoLeccion.completada:
            return lecciones[orden], (p.nivel_actual if p else 1)
    ultima = lecciones[max(lecciones)]
    return ultima, 3


async def sembrar_estudiante(db, fila: dict, est: Usuario, plan: dict, libros: dict, pool: dict, presupuesto,
                             con_chat: bool = True) -> None:
    from freezegun import freeze_time

    from app.modules.actividades.service import responder_actividad
    from app.modules.chat.service import RESPUESTA_LLM_NO_DISPONIBLE, procesar_pregunta
    from app.modules.lecciones.service import completar_nivel, iniciar_leccion

    grado = (await db.execute(select(Grado.nombre).where(Grado.id == est.grado_id))).scalar()
    rng = random.Random(SEMILLA * 1000 + fila["fila"])
    puntajes = list(plan["puntajes"])
    k = 0
    desvio = 0  # diferencia acumulada (real - objetivo) por el ajuste de "ordenar"
    for sesion in plan["sesiones"]:
        t = sesion["fecha"]
        conv_id = None
        if sesion["consultas"] and con_chat:
            asig, orden = sesion["chat"]
            libro = libros[(est.grado_id, asig)]
            leccion = libro["lecciones"][orden] if orden else (await leccion_actual(db, libro, est.id))[0]
            nombre_asig = "Ciencias Naturales" if asig == CIENCIAS else "Matemáticas"
            preguntas = await preguntas_de_leccion(db, pool, leccion, grado, nombre_asig, presupuesto)
            for pregunta in rng.sample(preguntas, min(len(preguntas), sesion["consultas"])) + \
                    [rng.choice(preguntas) for _ in range(max(0, sesion["consultas"] - len(preguntas)))]:
                presupuesto.verificar()
                t += timedelta(seconds=rng.randrange(40, 150))
                with freeze_time(t, tick=True, real_asyncio=True):
                    r = await procesar_pregunta(db, pregunta, conv_id, asig, est)
                if r["respuesta"].startswith(RESPUESTA_LLM_NO_DISPONIBLE):
                    raise RuntimeError("el LLM no respondió (respuesta de respaldo)")
                conv_id = r["conversacion_id"]
        for b in sesion["bloques"]:
            asig = b["asignatura"]
            libro = libros[(est.grado_id, asig)]
            t += timedelta(seconds=rng.randrange(60, 240))
            with freeze_time(t, tick=True, real_asyncio=True):
                if b["tipo"] == "ruta":
                    leccion, nivel = await leccion_actual(db, libro, est.id)
                    prog = (await db.execute(select(ProgresoLeccion).where(
                        ProgresoLeccion.estudiante_id == est.id, ProgresoLeccion.leccion_id == leccion.id))).scalar_one_or_none()
                    if prog is None or prog.estado == EstadoLeccion.disponible:
                        if leccion.orden == 1 or prog is not None:
                            await iniciar_leccion(est.id, leccion.id, db)
                else:
                    leccion, nivel = libro["lecciones"][b["orden"]], "p"
                acts = await actividades_de_ronda(db, pool, leccion, nivel, asig, est, presupuesto,
                                                  hasta=b["offset"] + b["tam"])
            obtenidos = []
            for act in acts[b["offset"]:b["offset"] + b["tam"]]:
                objetivo = puntajes[k]
                if act.tipo == TipoActividad.ordenar:
                    objetivo = max(0, min(100, objetivo - desvio))
                respuesta, _ = respuesta_para(act, objetivo)
                t += timedelta(seconds=rng.randrange(20, 90))
                with freeze_time(t, tick=True, real_asyncio=True):
                    res = await responder_actividad(db, act.id, respuesta, est.id)
                desvio += res["puntaje"] - puntajes[k]
                obtenidos.append(res["puntaje"])
                k += 1
            if b["tipo"] == "ruta" and b["tam"] == ACTIVIDADES_POR_RONDA:
                with freeze_time(t + timedelta(seconds=5), tick=True, real_asyncio=True):
                    await completar_nivel(est.id, leccion.id, nivel, sum(p >= APROBADA for p in obtenidos),
                                          int(obtenidos[-1]), db, total_actividades=b["tam"])


# ---------------------------------------------------------------- main

def elegir_lecciones(filas: list[dict], libros: dict) -> dict[int, list[tuple[int, int]]]:
    """Lecciones de práctica de cada fila: 8–12, mitad por asignatura, tomando primero las menos
    usadas del grado para que el mapa de calor cubra las 10 de cada libro."""
    elegidas = {}
    for g in sorted({r["grado_id"] for r in filas}):
        rng = random.Random(SEMILLA + g)
        uso = Counter()
        candidatas = {a: [(a, o) for o in lecciones_de_practica(len(libros[(g, a)]["lecciones"]))]
                      for a in (CIENCIAS, MATEMATICAS) if (g, a) in libros}
        for r in sorted((r for r in filas if r["grado_id"] == g), key=lambda r: r["fila"]):
            n = rng.randint(*LECCIONES_POR_ESTUDIANTE)
            mitades = {CIENCIAS: n - n // 2, MATEMATICAS: n // 2} if rng.random() < 0.5 else \
                      {CIENCIAS: n // 2, MATEMATICAS: n - n // 2}
            sel = []
            for a, c in candidatas.items():
                orden = sorted(c, key=lambda x: (uso[x], rng.random()))[:mitades[a]]
                uso.update(orden)
                sel += orden
            rng.shuffle(sel)
            elegidas[r["fila"]] = sel
    return elegidas


def recorrer(r: dict, sesiones: list[dict], puntajes: list[int], libros: dict):
    """Simula la corrida: devuelve, por bloque en orden, (asignatura, orden, nivel) — nivel "p" en
    práctica — y las lecciones del chat ((grado, asignatura, orden))."""
    estado = {asig: {"orden": 1, "nivel": 1, "total": len(libros[(r["grado_id"], asig)]["lecciones"])}
              for asig in (CIENCIAS, MATEMATICAS) if (r["grado_id"], asig) in libros}
    pasos, lecciones_chat, k = [], set(), 0
    for s in sesiones or []:
        if s["consultas"]:
            asig, orden = s["chat"]
            if asig in estado:
                lecciones_chat.add((r["grado_id"], asig, orden or estado[asig]["orden"]))
        for b in s["bloques"]:
            st = estado.get(b["asignatura"])
            if st is None:
                pasos.append(None)
                continue
            ps = puntajes[k:k + b["tam"]]
            if b["tipo"] == "ruta":
                orden, nivel = (st["orden"], st["nivel"]) if b["tam"] < ACTIVIDADES_POR_RONDA else simular_progreso(st, ps)
            else:
                orden, nivel = b["orden"], "p"
            pasos.append((b["asignatura"], orden, nivel))
            k += b["tam"]
    return pasos, lecciones_chat


def slots_reales(r: dict, en_orden: list[dict], pasos: list, libros: dict, tipos: dict) -> dict[int, list[int]]:
    """Como slots_ordenar, pero con las actividades ya generadas en el banco: crear_actividad
    regenera como opción múltiple las de ordenar que no valida, y el nº de elementos varía.
    `tipos`: clave del banco -> por actividad, los puntajes posibles si es de ordenar o None."""
    slots, k = {}, 0
    for b, paso in zip(en_orden, pasos):
        banco = []
        if paso is not None:
            asig, orden, nivel = paso
            banco = tipos.get(f"{libros[(r['grado_id'], asig)]['lecciones'][orden].id}:{nivel}", [])
        for j in range(b["tam"]):
            i = b["offset"] + j
            if i < len(banco):
                if banco[i] is not None:
                    slots[k + j] = banco[i]
            elif i in SLOTS_ORDENAR:
                slots[k + j] = valores_ordenar(5)
        k += b["tam"]
    return slots


def mover_offsets(en_orden: list[dict], rng: random.Random) -> None:
    """Nueva posición inicial en el banco para los bloques de práctica de cada lección; los bloques
    partidos de una misma lección siguen consecutivos (nunca repiten actividad)."""
    por_leccion = defaultdict(list)
    for b in en_orden:
        if b["tipo"] == "practica":
            por_leccion[(b["asignatura"], b["orden"])].append(b)
    for bs in por_leccion.values():
        pos = rng.randrange(ACTIVIDADES_POR_RONDA - sum(b["tam"] for b in bs) + 1)
        for b in bs:
            b["offset"], pos = pos, pos + b["tam"]


def construir_planes(filas: list[dict], libros: dict, tipos: dict | None = None) -> dict[int, dict]:
    """`tipos`: clave del banco ("leccion_id:nivel") -> tipos reales de sus actividades ya generadas."""
    planes = {}
    elegidas = elegir_lecciones(filas, libros)
    for r in filas:
        rng = random.Random(SEMILLA * 1000 + r["fila"])
        bloques = plan_bloques(r["actividades"], elegidas[r["fila"]], rng)
        sesiones = plan_sesiones(r["sesiones"], r["consultas"], bloques, elegidas[r["fila"]], rng)
        en_orden = [b for s in sesiones or [] for b in s["bloques"]]
        for intento in range(20):
            if intento:  # sin plan: otras posiciones en los bancos de práctica (mismos días y lecciones)
                mover_offsets(en_orden, rng)
            slots = slots_ordenar(en_orden)
            for _ in range(5):  # los bancos de la ruta dependen del avance, que depende de los puntajes
                puntajes, ok, creciente = planificar_puntajes(r["actividades"], r["tasa_acierto"], r["dominio_inicio"],
                                                              r["dominio_final"], rng, slots=slots)
                pasos, lecciones_chat = recorrer(r, sesiones, puntajes, libros)
                nuevos = slots_reales(r, en_orden, pasos, libros, tipos or {})
                if nuevos == slots:
                    break
                slots = nuevos
            else:
                ok = False
            if ok:
                break
        bancos, celdas, k = Counter(), defaultdict(list), 0
        for b, paso in zip(en_orden, pasos):
            if paso is not None:
                asig, orden, nivel = paso
                clave = (r["grado_id"], asig, orden, nivel)
                bancos[clave] = max(bancos[clave], b["offset"] + b["tam"])
                celdas[(asig, orden)] += puntajes[k:k + b["tam"]]
            k += b["tam"]
        w = ventana(len(puntajes))
        planes[r["fila"]] = {
            "puntajes": puntajes, "sesiones": sesiones, "ok": ok and sesiones is not None, "creciente": creciente,
            "tasa_plan": sum(puntajes) / len(puntajes),
            "inicio_plan": nivel_csv(sum(puntajes[:w]) / w), "final_plan": nivel_csv(sum(puntajes[-w:]) / w),
            "bancos": bancos, "lecciones_chat": lecciones_chat,
            "celdas": {c: nivel_por_puntaje(sum(v) / len(v)) for c, v in celdas.items()},
            "act_ruta": sum(b["tam"] for b in en_orden if b["tipo"] == "ruta"),
            "lecciones_practica": len({(b["asignatura"], b["orden"]) for b in en_orden if b["tipo"] == "practica"}),
            "faltan_libros": [a for a in (CIENCIAS, MATEMATICAS) if (r["grado_id"], a) not in libros],
        }
    return planes


def escribir_mapeo(ruta: Path, filas, asignado, planes, nombres_grado) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fila_csv", "estudiante_id", "username", "nombre", "apellido", "grado_csv", "grado_asignado",
                    "cuenta_demo", "curva", "plan_compatible"])
        for r in sorted(filas, key=lambda r: r["fila"]):
            u, p = asignado[r["fila"]], planes[r["fila"]]
            w.writerow([r["fila"], u.id, u.username, u.nombre, u.apellido, r["grado"], nombres_grado[r["grado_id"]],
                        "sí" if r["fila"] in CUENTAS_DEMO else "", "creciente" if p["creciente"] else "no creciente (opción A)",
                        "sí" if p["ok"] else "NO"])


def imprimir_plan(filas, asignado, planes, por_grado, nombres_grado, presupuesto) -> None:
    print("\n== Compatibilidad de las 72 filas")
    print(f"{'fila':>4} {'grado':13} {'usuario':13} {'ses':>3} {'cons':>4} {'act':>3} {'tasa':>6}->{'plan':<6} "
          f"{'inicio':18}{'final':18} curva       ok")
    for r in sorted(filas, key=lambda r: r["fila"]):
        p = planes[r["fila"]]
        ini = r["dominio_inicio"] + ("" if p["inicio_plan"] == r["dominio_inicio"] else f"≠{p['inicio_plan']}")
        fin = r["dominio_final"] + ("" if p["final_plan"] == r["dominio_final"] else f"≠{p['final_plan']}")
        print(f"{r['fila']:>4} {nombres_grado[r['grado_id']]:13} {asignado[r['fila']].username:13} {r['sesiones']:>3} "
              f"{r['consultas']:>4} {r['actividades']:>3} {r['tasa_acierto']:>6.1f}->{p['tasa_plan']:<6.1f} {ini:18}{fin:18}"
              f"{'creciente  ' if p['creciente'] else 'opción A   '} {'OK' if p['ok'] else 'FALLA'}"
              f"{' (sin libro: ' + str(p['faltan_libros']) + ')' if p['faltan_libros'] else ''}")
    print("\n== Plan por grado")
    print(f"{'grado':13} {'estud.':>6} {'con datos':>9} {'consultas':>9} {'activ.':>6} {'ruta %':>6} "
          f"{'bancos':>6} {'gen.':>5} {'lecc. chat':>10} {'USD est.':>8}")
    total = Counter()
    entrada, salida = presupuesto.precio(presupuesto.modelo)
    costo = {k: (TOKENS[k][0] * entrada + TOKENS[k][1] * salida) / 1e6 for k in TOKENS}
    for g in sorted(por_grado):
        fs = [r for r in filas if r["grado_id"] == g]
        cons = sum(r["consultas"] for r in fs)
        act = sum(r["actividades"] for r in fs)
        ruta = sum(planes[r["fila"]]["act_ruta"] for r in fs)
        bancos = Counter()
        for r in fs:
            for c, n in planes[r["fila"]]["bancos"].items():
                bancos[c] = max(bancos[c], n)
        generadas = sum(bancos.values())
        lchat = set().union(*[planes[r["fila"]]["lecciones_chat"] for r in fs]) if fs else set()
        usd = cons * costo["chat"] + generadas * LLAMADAS_POR_ACTIVIDAD * costo["actividad"] + len(lchat) * costo["preguntas"]
        total.update({"est": len(por_grado[g]), "datos": len(fs), "cons": cons, "act": act, "ruta": ruta,
                      "bancos": len(bancos), "gen": generadas, "lchat": len(lchat), "usd": usd})
        print(f"{nombres_grado[g]:13} {len(por_grado[g]):>6} {len(fs):>9} {cons:>9} {act:>6} {100 * ruta / act:>5.0f}% "
              f"{len(bancos):>6} {generadas:>5} {len(lchat):>10} {usd:>8.2f}")
    print(f"{'TOTAL':13} {total['est']:>6} {total['datos']:>9} {total['cons']:>9} {total['act']:>6} "
          f"{100 * total['ruta'] / total['act']:>5.0f}% {total['bancos']:>6} {total['gen']:>5} {total['lchat']:>10} {total['usd']:>8.2f}")
    print(f"\nActividades: {total['ruta']} en la ruta ({100 * total['ruta'] / total['act']:.0f} %), "
          f"{total['act'] - total['ruta']} en práctica por lección ({100 - 100 * total['ruta'] / total['act']:.0f} %)")
    n_lecc = Counter(planes[r["fila"]]["lecciones_practica"] for r in filas)
    print("Lecciones de práctica por estudiante:", dict(sorted(n_lecc.items())))

    print("\n== Mapa de calor previsto (lecciones con celdas · celdas domina/en_proceso/refuerzo)")
    for g in sorted(por_grado):
        partes = []
        for a, nombre in ((CIENCIAS, "Ciencias"), (MATEMATICAS, "Matemáticas")):
            celdas = [n for r in filas if r["grado_id"] == g for (asig, _), n in planes[r["fila"]]["celdas"].items() if asig == a]
            lecc = {o for r in filas if r["grado_id"] == g for (asig, o) in planes[r["fila"]]["celdas"] if asig == a}
            c = Counter(celdas)
            partes.append(f"{nombre} {len(lecc):>2} lecc · {c['domina']:>2}/{c['en_proceso']:>2}/{c['refuerzo']:>2}")
        print(f"{nombres_grado[g]:13} " + "   ".join(partes))
    llamadas_total = total["cons"] + total["gen"] * LLAMADAS_POR_ACTIVIDAD + total["lchat"]
    print(f"\nLlamadas LLM estimadas: ~{llamadas_total:.0f} (modelo {presupuesto.modelo}, ${entrada}/M entrada, ${salida}/M salida)")
    print(f"Tiempo estimado: ~{(total['cons'] * 2 + total['gen'] * 2.5 + total['act'] * 0.2) / 60:.0f} min")


async def main_async(args) -> None:
    async with AsyncSessionLocal() as db:
        por_grado = await estudiantes_reales(db)
        if args.borrar:
            ids = [u.id for us in por_grado.values() for u in us]
            for i in ids:
                await borrar_estudiante(db, i)
            n = (await db.execute(delete(Actividad).where(_en_ventana(Actividad.fecha_creacion)))).rowcount
            await db.commit()
            POOL_PATH.unlink(missing_ok=True)
            print(f"Borrados los datos de uso de {len(ids)} estudiantes reales y {n} actividades del pool del piloto.")
            return
        nombres_grado = dict((await db.execute(select(Grado.id, Grado.nombre))).all())
        filas = leer_csv(args.csv)
        asignado = mapear(filas, por_grado)
        libros = await libros_y_lecciones(db)
        pool = _cargar_pool()
        planes = construir_planes(filas, libros, await tipos_del_pool(db, pool))
        escribir_mapeo(args.mapeo, filas, asignado, planes, nombres_grado)
        presupuesto = Presupuesto(args.max_usd)
        from app.config import settings
        presupuesto.modelo = settings.LLM_MODEL
        if args.dry_run:
            imprimir_plan(filas, asignado, planes, por_grado, nombres_grado, presupuesto)
            print(f"\nMapeo escrito en {args.mapeo}. (dry-run: no se llamó al LLM ni se escribió en la BD)")
            return
        malas = [r["fila"] for r in filas if not planes[r["fila"]]["ok"] or planes[r["fila"]]["faltan_libros"]]
        if malas:
            sys.exit(f"filas sin plan compatible o sin libros: {malas}; revisar con --dry-run")
        from app.llm.client import llm_client
        presupuesto.instrumentar(llm_client._client)
        objetivo = [r for r in sorted(filas, key=lambda r: r["fila"]) if not args.grado or r["grado_id"] in args.grado]
        try:
            for i, r in enumerate(objetivo, 1):
                est = asignado[r["fila"]]
                hecho = await contar_piloto(db, est.id)
                completo = (hecho["actividades"], hecho["consultas"]) == (r["actividades"], r["consultas"])
                if completo and not (args.rehacer_actividades and not cuadra(hecho, r)):
                    print(f"[{i}/{len(objetivo)}] fila {r['fila']} ({est.username}) ya sembrada, se salta")
                    continue
                # Con --rehacer-actividades, una fila completa que no cuadra conserva su chat.
                solo_actividades = completo
                borrar = borrar_actividades_estudiante if solo_actividades else borrar_estudiante
                await borrar(db, est.id)  # a medias o con datos previos (p. ej. progreso de pruebas)
                try:
                    await sembrar_estudiante(db, r, est, planes[r["fila"]], libros, pool, presupuesto,
                                             con_chat=not solo_actividades)
                except BaseException:
                    await db.rollback()
                    await borrar(db, est.id)
                    raise
                h = await contar_piloto(db, est.id)
                print(f"[{i}/{len(objetivo)}] fila {r['fila']} ({est.username}): {h['sesiones']} ses, {h['consultas']} cons, "
                      f"{h['actividades']} act, tasa {h['tasa']:.1f} (CSV {r['tasa_acierto']}) | ${presupuesto.total_usd:.3f}",
                      flush=True)
        except PresupuestoAgotado as e:
            print(f"\nDetenido por presupuesto: {e}. El último estudiante se deshizo; volver a correr para continuar.")
        finally:
            presupuesto.imprimir_resumen()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, help="datos_simulados_cap5.csv")
    ap.add_argument("--mapeo", type=Path, help="dónde escribir el mapeo fila -> estudiante")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--grado", type=int, action="append", help="solo este grado_id (repetible)")
    ap.add_argument("--rehacer-actividades", action="store_true",
                    help="rehace solo las actividades de las filas completas que no cuadran (conserva el chat)")
    ap.add_argument("--borrar", action="store_true", help="borra los datos de uso de los estudiantes reales y el pool")
    agregar_argumento_max_usd(ap, defecto=3.0)
    args = ap.parse_args()
    if not args.borrar and (not args.csv or not args.mapeo):
        ap.error("--csv y --mapeo son obligatorios (salvo con --borrar)")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
