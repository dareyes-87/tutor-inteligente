"""
Pruebas UNITARIAS del evaluador de actividades (sin servidor ni LLM).
"""
from app.models.actividad import TipoActividad
from app.modules.actividades.evaluator import evaluar_actividad

# Forma real en que crear_actividad guarda una actividad "completar".
CONTENIDO = {"oracion": "El sistema ___ lleva la sangre a todo el cuerpo", "pista": "Empieza con 'circ'"}
RESPUESTA = {"respuesta_correcta": "circulatorio"}


def test_completar_correcto_incluye_la_pista():
    r = evaluar_actividad(TipoActividad.completar, {"respuesta": "Circulatorio"}, RESPUESTA, CONTENIDO)
    assert r["puntaje"] == 100
    assert r["retroalimentacion"] == "¡Correcto! Empieza con 'circ'"


def test_completar_incorrecto_incluye_respuesta_y_pista():
    r = evaluar_actividad(TipoActividad.completar, {"respuesta": "nervioso"}, RESPUESTA, CONTENIDO)
    assert r["puntaje"] == 0
    assert "circulatorio" in r["retroalimentacion"]
    assert "Empieza con 'circ'" in r["retroalimentacion"]


def test_completar_sin_pista_no_falla():
    r = evaluar_actividad(TipoActividad.completar, {"respuesta": "circulatorio"}, RESPUESTA, {"oracion": "x"})
    assert r["puntaje"] == 100
