"""
Procesador de PDF: extracción de texto digital y OCR de páginas escaneadas.
Optimizado para libros escolares con diseño complejo (tablas, columnas, imágenes).
"""
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
import io
import logging

logger = logging.getLogger(__name__)

OCR_DPI = 300
MIN_TEXT_CHARS = 50
# Confianza mínima por palabra para considerarla válida (filtra basura de imágenes)
MIN_WORD_CONFIDENCE = 30
# Si una página tiene menos de este % de palabras válidas, se marca como "imagen"
MIN_VALID_WORDS_RATIO = 0.3


def _preprocess_image(pil_img: Image.Image) -> Image.Image:
    """
    Preprocesamiento de imagen para libros con diseño complejo.
    """
    # 1. Escala de grises
    img = pil_img.convert("L")
    # 2. Aumentar contraste
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    # 3. Nitidez
    img = img.filter(ImageFilter.SHARPEN)
    # 4. Escalar si es muy pequeña
    w, h = img.size
    if w < 2000:
        scale = 2000 / w
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
    Usa PSM 3 (segmentación automática) que maneja columnas y tablas.
    Filtra palabras basura para un cálculo de confianza más realista.
    """
    # Rasterizar a imagen
    mat = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    pil_img = Image.open(io.BytesIO(img_bytes))

    # Preprocesar
    processed = _preprocess_image(pil_img)

    # OCR con Tesseract: PSM 3 = segmentación automática completa
    # Mejor para páginas con columnas, tablas y diseño mixto
    custom_config = r"--psm 3 --oem 3"

    data = pytesseract.image_to_data(
        processed, lang="spa", config=custom_config,
        output_type=pytesseract.Output.DICT,
    )

    # Filtrar: solo palabras reales con confianza razonable
    valid_words = []
    all_confidences = []

    for conf_str, word in zip(data["conf"], data["text"]):
        conf = int(conf_str)
        word_clean = word.strip()

        if conf < 0 or not word_clean:
            continue  # Tesseract pone -1 en separadores

        all_confidences.append(conf)

        if conf >= MIN_WORD_CONFIDENCE and len(word_clean) >= 1:
            valid_words.append(word_clean)

    # Calcular ratio de palabras válidas vs total
    total_words = len(all_confidences)
    valid_count = len(valid_words)

    if total_words == 0:
        return "", 0.0

    valid_ratio = valid_count / total_words

    # Si muy pocas palabras son válidas, esta página es probablemente una imagen
    if valid_ratio < MIN_VALID_WORDS_RATIO:
        logger.debug(f"Página descartada: solo {valid_ratio:.0%} palabras válidas")
        return "", 0.0

    # Confianza = promedio SOLO de las palabras válidas (no de la basura)
    valid_confidences = [
        c for c in all_confidences if c >= MIN_WORD_CONFIDENCE
    ]
    avg_confidence = (
        sum(valid_confidences) / len(valid_confidences) if valid_confidences else 0.0
    )

    # Extraer texto completo con el mismo config
    text = pytesseract.image_to_string(
        processed, lang="spa", config=custom_config
    ).strip()

    return text, avg_confidence


def process_pdf(pdf_path: str) -> list[dict]:
    """
    Procesa un PDF completo página por página.
    Para cada página decide: digital o escaneada, y extrae el texto.
    Páginas que son puras imágenes se saltan (confianza 0, texto vacío).
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

            if not text or confidence == 0:
                logger.info(f"Página {page_num + 1}: imagen/sin texto útil (saltada)")
                continue  # No indexar páginas sin texto útil

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
