"""Signos ÷ × ( ) de las fuentes MathMagic (libros de Matemática del MINEDUC).

Fixture: página 61 de "1B Matemática" (División de una expresión algebraica
entre un número entero), recortada a un PDF de una página.
"""
from pathlib import Path

import fitz

from app.modules.ingesta.pdf_processor import _extract_digital_text

PAGINA_61 = Path(__file__).parent / "fixtures" / "1B_matematica_p61.pdf"


def test_division_y_parentesis_se_extraen_como_signos():
    with fitz.open(PAGINA_61) as doc:
        texto = _extract_digital_text(doc[0])
    assert "x litros ÷ 3 amigos" in texto
    assert "omitiendo el signo “÷”" in texto
    assert "x ÷ (- 4)" in texto
    assert "x ×" in texto
    assert "'" not in texto and "#" not in texto and "^" not in texto
    assert "Juliana" in texto  # el resto del texto no se toca
