"""
Procesador de PDF: extracción de texto digital y OCR de páginas escaneadas.
Este es el corazón del camino crítico. Maneja ambos tipos de PDF.
"""
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageFilter
import io
import logging

logger = logging.getLogger(__name__)

# DPI para rasterizar páginas escaneadas (300 = buen balance calidad/velocidad)
OCR_DPI = 300
# Umbral mínimo de texto por página para considerar que es "digital"
MIN_TEXT_CHARS = 50


def _preprocess_image(pil_img: Image.Image) -> Image.Image:
    """
    Preprocesamiento de imagen antes del OCR para mejorar la precisión.
    Esto es lo que te lleva al ≥95% CER en escaneados.
    """
    # 1. Escala de grises
    img = pil_img.convert("L")
    # 2. Aumentar contraste (binarización con umbral de Otsu lo hace Tesseract,
    #    pero ayudamos con un filtro de nitidez)
    img = img.filter(ImageFilter.SHARPEN)
    # 3. Escalar si es muy pequeña (Tesseract rinde mejor con imágenes grandes)
    w, h = img.size
    if w < 1500:
        scale = 1500 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _page_has_text(page: fitz.Page) -> bool:
    """Detecta si una página tiene texto digital extraíble."""
    text = page.get_text("text", sort=True).strip()
    return len(text) >= MIN_TEXT_CHARS


def _extract_digital_text(page: fitz.Page) -> str:
    """Extrae texto de una página con capa de texto digital."""
    return page.get_text("text", sort=True).strip()


def _extract_ocr_text(page: fitz.Page) -> tuple[str, float]:
    """
    Rasteriza una página, preprocesa y aplica OCR.
    Devuelve (texto, confianza_promedio).
    """
    # Rasterizar a imagen
    mat = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    pil_img = Image.open(io.BytesIO(img_bytes))

    # Preprocesar
    processed = _preprocess_image(pil_img)

    # OCR con Tesseract en español, pidiendo datos detallados para confianza
    data = pytesseract.image_to_data(
        processed, lang="spa", output_type=pytesseract.Output.DICT
    )

    # Calcular confianza promedio (solo de palabras reales, no espacios)
    confidences = [
        int(c) for c, text in zip(data["conf"], data["text"])
        if int(c) > 0 and text.strip()
    ]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # Extraer texto limpio
    text = pytesseract.image_to_string(processed, lang="spa").strip()

    return text, avg_confidence


def process_pdf(pdf_path: str) -> list[dict]:
    """
    Procesa un PDF completo página por página.
    Para cada página decide: ¿digital o escaneada? y extrae el texto.

    Devuelve una lista de diccionarios:
    [
        {
            "page_num": 1,
            "text": "contenido...",
            "method": "digital" | "ocr",
            "confidence": 100.0 | 85.3  (100 para digital)
        },
        ...
    ]
    """
    doc = fitz.open(pdf_path)
    results = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        if _page_has_text(page):
            text = _extract_digital_text(page)
            results.append({
                "page_num": page_num + 1,
                "text": text,
                "method": "digital",
                "confidence": 100.0,
            })
            logger.info(f"Página {page_num + 1}: digital ({len(text)} chars)")
        else:
            text, confidence = _extract_ocr_text(page)
            results.append({
                "page_num": page_num + 1,
                "text": text,
                "method": "ocr",
                "confidence": round(confidence, 2),
            })
            logger.info(
                f"Página {page_num + 1}: OCR (confianza={confidence:.1f}%, {len(text)} chars)"
            )

    doc.close()
    return results
