"""Pruebas unitarias del formato de referencias a páginas (rag/paginas.py)."""
from app.modules.rag.paginas import formatear_rango_paginas, referencia_repaso


def test_rangos_consecutivos_y_sueltos():
    assert formatear_rango_paginas([37, 36, 93, 36]) == "36-37, 93"


def test_repaso_una_pagina():
    assert referencia_repaso("Ciencias Naturales", [51, 51]) == "\n\n📖 Repasa tu libro de Ciencias Naturales, página 51."


def test_repaso_varias_paginas():
    assert referencia_repaso("Matemáticas", [50, 51, 55]) == "\n\n📖 Repasa tu libro de Matemáticas, páginas 50-51, 55."


def test_repaso_sin_paginas_es_vacio():
    assert referencia_repaso("Matemáticas", []) == ""
    assert referencia_repaso("Matemáticas", [None]) == ""
