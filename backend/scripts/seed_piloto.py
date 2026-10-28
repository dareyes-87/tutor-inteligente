"""
Seed del piloto (1–30 de septiembre de 2026) a partir de datos/datos_simulados_cap5.csv.

Reproduce, sobre las cuentas REALES de estudiantes (no crea ni modifica cuentas),
el uso que describe cada fila del CSV, llamando a las FUNCIONES DE SERVICIO reales
con la hora congelada (freezegun) en la fecha simulada de cada evento:
  - consultas   -> chat.service.procesar_pregunta (pipeline RAG + DeepSeek real),
  - actividades -> lecciones.service.iniciar_leccion / actividades.service.responder_actividad /
                   lecciones.service.completar_nivel, en rondas de 5 como la app,
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
cada ronda lleva una actividad de ordenar para ajustar la tasa.

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


def planificar_puntajes(actividades: int, tasa: float, inicio: str, final: str, rng: random.Random):
    """Secuencia de puntajes (0/100; 20-80 solo en el slot de ordenar de cada ronda)."""
    slots = set()
    for r, tam in enumerate(tamanos_rondas(actividades)):
        slots.update(r * ACTIVIDADES_POR_RONDA + j for j in SLOTS_ORDENAR if j < tam)
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
            opciones = [0, 100] + ([20, 40, 60, 80] if i in slots else [])
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
        valores = [([0, 20, 40, 60, 80, 100] if i in slots else [0, 100]) for i in range(actividades)]
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


def plan_sesiones(sesiones: int, consultas: int, actividades: int, rng: random.Random):
    """Reparte rondas y consultas en las sesiones; cada sesión recibe al menos una de las dos.
    Devuelve [{fecha, asignatura, consultas, rondas: [tamaños]}] o None si no cabe."""
    rondas = tamanos_rondas(actividades)
    # Más sesiones que rondas + consultas: se parten rondas (práctica que se deja a
    # medias y se retoma otro día), empezando por la última.
    while sesiones > len(rondas) + consultas and any(r > 1 for r in rondas):
        i = max(i for i, r in enumerate(rondas) if r > 1)
        rondas[i:i + 1] = [rondas[i] - rondas[i] // 2, rondas[i] // 2]
    if sesiones > len(rondas) + consultas:
        return None
    plan = [{"rondas": [], "consultas": 0} for _ in range(sesiones)]
    for i, tam in enumerate(rondas):
        plan[min(sesiones - 1, i * sesiones // len(rondas))]["rondas"].append(tam)
    vacias = [p for p in plan if not p["rondas"]]
    for p in vacias[:consultas]:
        p["consultas"] += 1
    for _ in range(consultas - min(consultas, len(vacias))):
        rng.choice(plan)["consultas"] += 1
    for i, (p, f) in enumerate(zip(plan, fechas_sesiones(sesiones, rng))):
        p["fecha"] = f
        p["asignatura"] = CIENCIAS if i % 2 == 0 else MATEMATICAS
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


async def actividades_de_ronda(db, pool, leccion: Leccion, nivel: int, asignatura_id: int, estudiante: Usuario,
                               presupuesto) -> list[Actividad]:
    """Las 5 actividades del pool para (lección, nivel); las genera la primera vez."""
    from app.modules.actividades.service import crear_actividad
    clave = f"{leccion.id}:{nivel}"
    ids = pool["actividades"].get(clave, [])
    actividades = [a for a in (await db.execute(select(Actividad).where(Actividad.id.in_(ids)))).scalars()]
    actividades.sort(key=lambda a: ids.index(a.id))
    while len(actividades) < ACTIVIDADES_POR_RONDA:
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


async def sembrar_estudiante(db, fila: dict, est: Usuario, plan: dict, libros: dict, pool: dict, presupuesto) -> None:
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
        asig = sesion["asignatura"]
        libro = libros[(est.grado_id, asig)]
        nombre_asig = "Ciencias Naturales" if asig == CIENCIAS else "Matemáticas"
        conv_id = None
        if sesion["consultas"]:
            leccion, _ = await leccion_actual(db, libro, est.id)
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
        for tam in sesion["rondas"]:
            leccion, nivel = await leccion_actual(db, libro, est.id)
            t += timedelta(seconds=rng.randrange(60, 240))
            with freeze_time(t, tick=True, real_asyncio=True):
                prog = (await db.execute(select(ProgresoLeccion).where(
                    ProgresoLeccion.estudiante_id == est.id, ProgresoLeccion.leccion_id == leccion.id))).scalar_one_or_none()
                if prog is None or prog.estado == EstadoLeccion.disponible:
                    if leccion.orden == 1 or prog is not None:
                        await iniciar_leccion(est.id, leccion.id, db)
                acts = await actividades_de_ronda(db, pool, leccion, nivel, asig, est, presupuesto)
            obtenidos = []
            for j, act in enumerate(acts[:tam]):
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
            if tam == ACTIVIDADES_POR_RONDA:
                with freeze_time(t + timedelta(seconds=5), tick=True, real_asyncio=True):
                    await completar_nivel(est.id, leccion.id, nivel, sum(p >= APROBADA for p in obtenidos),
                                          int(obtenidos[-1]), db, total_actividades=tam)


# ---------------------------------------------------------------- main

def construir_planes(filas: list[dict], libros: dict) -> dict[int, dict]:
    planes = {}
    for r in filas:
        rng = random.Random(SEMILLA * 1000 + r["fila"])
        puntajes, ok, creciente = planificar_puntajes(r["actividades"], r["tasa_acierto"],
                                                      r["dominio_inicio"], r["dominio_final"], rng)
        sesiones = plan_sesiones(r["sesiones"], r["consultas"], r["actividades"], rng)
        estado = {asig: {"orden": 1, "nivel": 1, "total": len(libros[(r["grado_id"], asig)]["lecciones"])}
                  for asig in (CIENCIAS, MATEMATICAS) if (r["grado_id"], asig) in libros}
        practicado, lecciones_chat, k = set(), set(), 0
        for s in sesiones or []:
            st = estado.get(s["asignatura"])
            if st is None:
                continue
            if s["consultas"]:
                lecciones_chat.add((r["grado_id"], s["asignatura"], st["orden"]))
            for tam in s["rondas"]:
                orden, nivel = simular_progreso(st, puntajes[k:k + tam])
                practicado.add((r["grado_id"], s["asignatura"], orden, nivel))
                k += tam
        w = ventana(len(puntajes))
        planes[r["fila"]] = {
            "puntajes": puntajes, "sesiones": sesiones, "ok": ok and sesiones is not None, "creciente": creciente,
            "tasa_plan": sum(puntajes) / len(puntajes),
            "inicio_plan": nivel_csv(sum(puntajes[:w]) / w), "final_plan": nivel_csv(sum(puntajes[-w:]) / w),
            "practicado": practicado, "lecciones_chat": lecciones_chat,
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
    print(f"{'grado':13} {'estud.':>6} {'con datos':>9} {'consultas':>9} {'activ.':>6} {'(lecc,nivel)':>12} {'lecc. chat':>10} {'USD est.':>8}")
    total = Counter()
    entrada, salida = presupuesto.precio(presupuesto.modelo)
    for g in sorted(por_grado):
        fs = [r for r in filas if r["grado_id"] == g]
        cons = sum(r["consultas"] for r in fs)
        act = sum(r["actividades"] for r in fs)
        pares = set().union(*[planes[r["fila"]]["practicado"] for r in fs]) if fs else set()
        lchat = set().union(*[planes[r["fila"]]["lecciones_chat"] for r in fs]) if fs else set()
        llamadas = {"chat": cons, "actividad": len(pares) * ACTIVIDADES_POR_RONDA * LLAMADAS_POR_ACTIVIDAD, "preguntas": len(lchat)}
        usd = sum(n * (TOKENS[k][0] * entrada + TOKENS[k][1] * salida) / 1e6 for k, n in llamadas.items())
        total.update({"est": len(por_grado[g]), "datos": len(fs), "cons": cons, "act": act, "pares": len(pares),
                      "lchat": len(lchat), "usd": usd})
        print(f"{nombres_grado[g]:13} {len(por_grado[g]):>6} {len(fs):>9} {cons:>9} {act:>6} {len(pares):>12} {len(lchat):>10} {usd:>8.2f}")
    print(f"{'TOTAL':13} {total['est']:>6} {total['datos']:>9} {total['cons']:>9} {total['act']:>6} {total['pares']:>12} "
          f"{total['lchat']:>10} {total['usd']:>8.2f}")
    llamadas_total = total["cons"] + total["pares"] * ACTIVIDADES_POR_RONDA * LLAMADAS_POR_ACTIVIDAD + total["lchat"]
    print(f"\nLlamadas LLM estimadas: ~{llamadas_total:.0f} (modelo {presupuesto.modelo}, ${entrada}/M entrada, ${salida}/M salida)")
    print(f"Tiempo estimado: ~{(total['cons'] * 2 + total['pares'] * ACTIVIDADES_POR_RONDA * 2.5 + total['act'] * 0.2) / 60:.0f} min")


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
        planes = construir_planes(filas, libros)
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
        pool = _cargar_pool()
        objetivo = [r for r in sorted(filas, key=lambda r: r["fila"]) if not args.grado or r["grado_id"] in args.grado]
        try:
            for i, r in enumerate(objetivo, 1):
                est = asignado[r["fila"]]
                hecho = await contar_piloto(db, est.id)
                if (hecho["actividades"], hecho["consultas"]) == (r["actividades"], r["consultas"]):
                    print(f"[{i}/{len(objetivo)}] fila {r['fila']} ({est.username}) ya sembrada, se salta")
                    continue
                await borrar_estudiante(db, est.id)  # a medias o con datos previos (p. ej. progreso de pruebas)
                try:
                    await sembrar_estudiante(db, r, est, planes[r["fila"]], libros, pool, presupuesto)
                except BaseException:
                    await db.rollback()
                    await borrar_estudiante(db, est.id)
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
    ap.add_argument("--borrar", action="store_true", help="borra los datos de uso de los estudiantes reales y el pool")
    agregar_argumento_max_usd(ap, defecto=3.0)
    args = ap.parse_args()
    if not args.borrar and (not args.csv or not args.mapeo):
        ap.error("--csv y --mapeo son obligatorios (salvo con --borrar)")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
