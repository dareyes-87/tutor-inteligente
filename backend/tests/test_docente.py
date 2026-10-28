"""
Panel docente (Fase 2), integración contra el servidor real (localhost:8000).
BD local: libros 3 (Ciencias 4to) y 4 (Matemáticas 4to), ambos escaneados (OCR).
"""
import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_libros_incluyen_metodo_y_confianza_ocr(token_docente):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/docente/libros", headers={"Authorization": f"Bearer {token_docente}"})
    assert resp.status_code == 200
    libros = resp.json()
    assert libros
    for libro in libros:
        assert libro["metodo"] in ("digital", "ocr", "mixto", None)
        assert "confianza_ocr_promedio" in libro
    escaneados = [l for l in libros if l["metodo"] == "ocr"]
    assert escaneados and all(0 < l["confianza_ocr_promedio"] <= 100 for l in escaneados)
