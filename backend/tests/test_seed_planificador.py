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


def test_sesiones_parten_rondas_si_faltan_unidades():
    # Fila 3: 5 sesiones, 2 consultas, 9 actividades (2 rondas) -> se parte una ronda.
    plan = sp.plan_sesiones(5, 2, 9, random.Random(1))
    assert len(plan) == 5 and all(p["rondas"] or p["consultas"] for p in plan)
    assert sum(sum(p["rondas"]) for p in plan) == 9 and sum(p["consultas"] for p in plan) == 2
    assert len({p["fecha"].date() for p in plan}) == 5


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
