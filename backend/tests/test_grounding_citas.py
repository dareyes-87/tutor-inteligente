"""
Pruebas UNITARIAS de la Capa 3 del grounding: validación de que las páginas
citadas por el LLM existan entre los fragmentos recuperados.

A diferencia de test_endpoints.py, estas NO requieren el servidor levantado ni
el LLM: prueban funciones puras de app.modules.chat.service.

    cd backend && pytest tests/test_grounding_citas.py
"""
from app.modules.chat.service import _citas_validas, _paginas_citadas, _quitar_citas_invalidas


def test_cita_valida_pagina_existente():
    """La respuesta cita una página que SÍ está en los fragmentos → True."""
    fragments = [{"page_num": 12}, {"page_num": 13}]
    respuesta = "Los seres vivos nacen y crecen (página 12)."
    assert _citas_validas(respuesta, fragments) is True


def test_cita_invalida_pagina_inexistente():
    """La respuesta cita una página que NO está en los fragmentos → False."""
    fragments = [{"page_num": 12}, {"page_num": 13}]
    respuesta = "La fotosíntesis ocurre en las hojas (página 99)."
    assert _citas_validas(respuesta, fragments) is False


def test_sin_citas_es_valida():
    """Respuesta sin ninguna cita de página → True (no se penaliza)."""
    fragments = [{"page_num": 12}]
    respuesta = "Los seres vivos respiran y se reproducen."
    assert _citas_validas(respuesta, fragments) is True


def test_una_valida_y_una_invalida_es_false():
    """Si al menos una cita es inválida, la respuesta completa es inválida."""
    fragments = [{"page_num": 12}]
    respuesta = "Ver (página 12) y también (página 40)."
    assert _citas_validas(respuesta, fragments) is False


def test_extraccion_paginas_con_y_sin_acento():
    """_paginas_citadas capta 'página' y 'pagina', sin distinguir mayúsculas."""
    assert _paginas_citadas("(página 5) y (Pagina 8)") == [5, 8]


def test_extraccion_plurales_y_rangos():
    assert _paginas_citadas("páginas 12 y 13, pág. 7 y **págs. 4-6**") == [12, 13, 7, 4, 5, 6]


def test_quitar_citas_invalidas_conserva_las_validas():
    """Solo se quitan las citas a páginas no recuperadas; el resto del texto queda igual."""
    disponibles = {23, 25}
    casos = {
        "Pertenecen al **Reino Fungi** (página 82). Los divisores (página 23).":
            "Pertenecen al **Reino Fungi**. Los divisores (página 23).",
        "Puedes revisar la página 45 de tu libro.": "Puedes revisar tu libro.",
        "Siguiendo lo que dice tu libro en la página 32: suma.": "Siguiendo lo que dice tu libro: suma.",
        "Se explica en la **página 40** y en la página 25.": "Se explica en tu libro y en la página 25.",
        "Mira páginas 7 y 8 del texto.": "Mira tu libro del texto.",
        "El m.c.m. aparece en tus páginas 36 y 37.": "El m.c.m. aparece en tu libro.",
    }
    for antes, despues in casos.items():
        assert _quitar_citas_invalidas(antes, disponibles) == despues
        assert _citas_validas(_quitar_citas_invalidas(antes, disponibles), [{"page_num": p} for p in disponibles])
