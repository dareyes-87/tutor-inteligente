"""Planificador del seed del piloto (scripts/seed_piloto.py): lógica pura, sin BD ni LLM."""
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import seed_piloto as sp  # noqa: E402
from app.models.actividad import TipoActividad  # noqa: E402


def _cumple(puntajes, tasa, inicio, final):
    w = sp.ventana(len(puntajes))
    return (sp.nivel_csv(sum(puntajes[:w]) / w) == inicio and sp.nivel_csv(sum(puntajes[-w:]) / w) == final
            and abs(sum(puntajes) / len(puntajes) - tasa) <= 2)


def test_plan_creciente_cumple_tasa_y_dominio():
    puntajes, ok, creciente = sp.planificar_puntajes(18, 76.9, "Necesita refuerzo", "En proceso", random.Random(1))
    assert ok and creciente and _cumple(puntajes, 76.9, "Necesita refuerzo", "En proceso")


def test_fila_incompatible_con_tendencia_creciente_usa_opcion_a():
    # Fila 32 del CSV: 15 actividades, 69.2 % y refuerzo -> refuerzo.
    puntajes, ok, creciente = sp.planificar_puntajes(15, 69.2, "Necesita refuerzo", "Necesita refuerzo", random.Random(1))
    assert ok and not creciente and _cumple(puntajes, 69.2, "Necesita refuerzo", "Necesita refuerzo")


def test_bloques_una_ronda_de_ruta_y_practica_en_lecciones_distintas():
    elegidas = [(sp.CIENCIAS, o) for o in range(2, 7)] + [(sp.MATEMATICAS, o) for o in range(2, 7)]
    bloques = sp.plan_bloques(18, "Bajo", elegidas, random.Random(1))
    ruta = [b for b in bloques if b["tipo"] == "ruta"]
    practica = [b for b in bloques if b["tipo"] == "practica"]
    assert [b["tam"] for b in ruta] == [5]
    assert bloques.index(ruta[0]) >= len(bloques) // 2  # en la segunda mitad, con la curva ya alta
    # 13 de práctica en 4 lecciones (al menos 3 por lección: celdas que no son solo 0/100)
    assert sum(b["tam"] for b in practica) == 13 and len({(b["asignatura"], b["orden"]) for b in practica}) == 4
    assert all(b["tam"] >= sp.MIN_ACT_POR_LECCION for b in practica)
    assert all(b["offset"] + b["tam"] <= 5 for b in practica)


def test_sesiones_parten_bloques_si_faltan_unidades():
    # Fila 3: 5 sesiones, 2 consultas, 9 actividades -> 1 ronda de ruta + 4 de práctica en 1 lección (se parte entre días).
    rng = random.Random(1)
    elegidas = [(sp.CIENCIAS, 2), (sp.MATEMATICAS, 3), (sp.CIENCIAS, 4), (sp.MATEMATICAS, 5)]
    plan = sp.plan_sesiones(5, 2, sp.plan_bloques(9, "Bajo", elegidas, rng), elegidas, rng)
    assert len(plan) == 5 and all(p["bloques"] or p["consultas"] for p in plan)
    assert sum(b["tam"] for p in plan for b in p["bloques"]) == 9 and sum(p["consultas"] for p in plan) == 2
    assert len({p["fecha"].date() for p in plan}) == 5


def test_slots_ordenar_siguen_la_posicion_en_el_banco():
    bloques = [{"tipo": "ruta", "tam": 5, "offset": 0}, {"tipo": "practica", "tam": 2, "offset": 2}]
    assert set(sp.slots_ordenar(bloques)) == {1, 3, 6}


def test_valores_ordenar_excluyen_n_menos_1():
    assert sp.valores_ordenar(4) == [0, 25, 50, 100]
    assert sp.valores_ordenar(5) == [0, 20, 40, 60, 100]


def test_ordenar_da_el_parcial_mas_cercano():
    act = SimpleNamespace(tipo=TipoActividad.ordenar, contenido={},
                          respuesta_correcta={"orden_correcto": ["a", "b", "c", "d", "e"]})
    respuesta, esperado = sp.respuesta_para(act, 60)
    assert esperado == 60
    assert sum(x == y for x, y in zip(respuesta["orden"], "abcde")) == 3


def test_progreso_sube_de_nivel_con_4_de_5():
    estado = {"orden": 1, "nivel": 1, "total": 3}
    sp.simular_progreso(estado, [100, 100, 100, 80, 0])
    assert (estado["orden"], estado["nivel"]) == (1, 2)
    sp.simular_progreso(estado, [100, 0, 100, 0, 100])
    assert (estado["orden"], estado["nivel"]) == (1, 2)


def test_fechas_sobre_chat_cuadra_sesiones_y_conserva_orden():
    from datetime import date
    rng = random.Random(1)
    elegidas = [(sp.CIENCIAS, 2), (sp.MATEMATICAS, 3), (sp.CIENCIAS, 4)]
    plan = {"sesiones": sp.plan_sesiones(9, 12, sp.plan_bloques(14, "Bajo", elegidas, rng), elegidas, rng)}
    chat = {date(2026, 9, d) for d in (2, 3, 8, 15, 22, 29)}
    nuevo = sp.fechas_sobre_chat(plan, 9, chat, random.Random(2))
    fechas = [x["fecha"] for x in nuevo["sesiones"]]
    assert fechas == sorted(fechas)
    assert len({f.date() for f in fechas} | chat) == 9
    assert sum(b["tam"] for x in nuevo["sesiones"] for b in x["bloques"]) == 14


def test_rondas_de_ruta_segun_nivel_de_uso():
    # 20 actividades: alto ≈ 95 % (4 rondas), medio ≈ 70 % (3), bajo ≈ 40 % (2); nunca más de act // 5.
    assert [sp.rondas_de_ruta(20, u) for u in ("Alto", "Medio", "Bajo")] == [4, 3, 2]
    assert sp.rondas_de_ruta(9, "Alto") == 1 and sp.rondas_de_ruta(6, "Bajo") == 0


def test_reintento_de_nivel_usa_banco_nuevo():
    # Ronda 1 falla (3 de 5) y ronda 2 aprueba en el mismo nivel: la 2ª usa otro banco.
    r = {"grado_id": 1}
    libros = {(1, sp.CIENCIAS): {"lecciones": {o: SimpleNamespace(id=100 + o) for o in range(1, 6)}}}
    ronda = {"tipo": "ruta", "asignatura": sp.CIENCIAS, "orden": None, "tam": 5, "offset": 0}
    sesiones = [{"consultas": 0, "bloques": [dict(ronda), dict(ronda)]}]
    pasos, _, estado = sp.recorrer(r, sesiones, [100, 100, 100, 0, 0] + [100] * 5, libros)
    assert pasos == [(sp.CIENCIAS, 1, 1, 0), (sp.CIENCIAS, 1, 1, 1)]
    assert sp.clave_banco(101, 1, 0) != sp.clave_banco(101, 1, 1)
    assert sp.avance(estado)["niveles"] == 1


def test_limpiar_pruebas_reconoce_rondas_de_ruta():
    # Banco del seed: actividad -> (lección:nivel[:intento], posición). Práctica ("p") no es ruta;
    # una ronda nueva empieza en la 1ª actividad del banco aunque el banco se repita.
    import limpiar_pruebas as lp
    banco = {i: ("101:1", i) for i in range(5)} | {10 + i: ("101:p", i) for i in range(3)}
    from datetime import datetime, timezone
    d1, d2 = datetime(2026, 9, 10, 18, tzinfo=timezone.utc), datetime(2026, 9, 12, 18, tzinfo=timezone.utc)
    res = [SimpleNamespace(actividad_id=a, fecha=d1) for a in [10, 11, 0, 1, 2, 3, 4, 12, 0, 1, 2]]
    res += [SimpleNamespace(actividad_id=a, fecha=d2) for a in [3, 4]]  # bloque partido entre días
    rondas = lp.rondas_de_ruta(res, banco)
    assert [[r.actividad_id for r in x] for x in rondas] == [[0, 1, 2, 3, 4], [0, 1, 2], [3, 4]]


def test_cuentas_demo_una_por_grado_del_piloto():
    from sqlalchemy import create_engine, text

    from app.config import settings
    from cuentas_demo import CUENTAS_DEMO, USUARIOS_DEMO
    assert len(CUENTAS_DEMO) == len(USUARIOS_DEMO) == len(sp.GRADO_CSV) == 6
    with create_engine(settings.database_url_sync).connect() as c:
        reales = dict(c.execute(text(
            "select u.username, g.nombre from usuario u join grado g on g.id = u.grado_id"
            " where u.rol = 'estudiante' and u.activo and u.username = any(:u)"), {"u": list(USUARIOS_DEMO)}).all())
    assert {g: u for u, g in reales.items()} == CUENTAS_DEMO
