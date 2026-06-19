"""
Procesador de PDF: extracción de texto digital y OCR de páginas escaneadas.
Este es el corazón del camino crítico. Maneja ambos tipos de PDF.

Optimizado para páginas escolares complejas (editorial Piedrasanta):
texto a columnas, recuadros laterales, pies de foto, tablas, sopas de letras
y ejercicios con líneas para escribir a mano. Para que la confianza refleje la
calidad real del texto y no la basura visual, el OCR:
  - usa PSM 3 (segmentación automática, bueno para columnas),
  - filtra palabras por debajo de una confianza mínima,
  - reconstruye el texto SOLO con esas palabras (la basura no se indexa),
  - salta páginas que son mayormente imagen (pocas palabras válidas),
  - preprocesa con escala de grises + autocontraste + deskew.
"""
import io
import logging

import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

# DPI para rasterizar páginas escaneadas (300 = buen balance calidad/velocidad)
OCR_DPI = 300
# Umbral mínimo de texto por página para considerar que es "digital"
MIN_TEXT_CHARS = 50

# Config de Tesseract: OEM 1 = motor LSTM; PSM 3 = segmentación automática de
# página (detecta columnas, recuadros y bloques por su cuenta).
TESSERACT_CONFIG = "--oem 1 --psm 3"
TESSERACT_LANG = "spa"

# Confianza mínima (0-100) para que una palabra cuente. Por debajo de esto casi
# siempre es ruido: letras sueltas de sopas de letras, trazos de escritura a
# mano, o números aislados mal leídos de una tabla.
MIN_WORD_CONF = 60
# Una palabra cuenta como "válida" (texto real, no ruido) si tiene al menos
# estos caracteres alfabéticos. Descarta números sueltos y símbolos.
MIN_ALPHA_CHARS = 2
# Si una página tiene menos de estas palabras válidas, se considera "mayormente
# imagen" y se salta (no aporta texto útil al RAG y solo ensucia la confianza).
MIN_VALID_WORDS = 12

# Deskew: rango máximo de inclinación a corregir (grados) y paso de búsqueda.
MAX_DESKEW_ANGLE = 10.0
DESKEW_STEP = 0.5
# Ángulo mínimo para molestarse en rotar (evita resampleo innecesario).
MIN_DESKEW_ANGLE = 0.5


def _is_valid_word(text: str) -> bool:
    """Una palabra real de prosa: al menos MIN_ALPHA_CHARS letras."""
    alpha = sum(1 for ch in text if ch.isalpha())
    return alpha >= MIN_ALPHA_CHARS


def _estimate_skew_angle(gray_img: Image.Image) -> float:
    """
    Estima el ángulo de inclinación del texto por projection-profile.
    Idea: cuando las líneas de texto quedan horizontales, la suma de tinta por
    fila tiene picos marcados (alta varianza). Probamos varios ángulos y nos
    quedamos con el de mayor varianza. Usa numpy (dependencia transitiva).
    """
    # Trabajar sobre una versión reducida: la estimación no necesita el detalle
    # completo y así probar ~40 ángulos es rápido.
    w, h = gray_img.size
    if w > 800:
        scale = 800 / w
        small = gray_img.resize((800, int(h * scale)), Image.BILINEAR)
    else:
        small = gray_img

    best_angle = 0.0
    best_score = -1.0
    angle = -MAX_DESKEW_ANGLE
    while angle <= MAX_DESKEW_ANGLE + 1e-9:
        rotated = small.rotate(
            angle, resample=Image.BILINEAR, expand=False, fillcolor=255
        )
        arr = np.asarray(rotated, dtype=np.float32)
        # Invertir para que la tinta (oscura) sume alto.
        ink = 255.0 - arr
        profile = ink.sum(axis=1)
        score = float(profile.var())
        if score > best_score:
            best_score = score
            best_angle = angle
        angle += DESKEW_STEP

    return best_angle


def _preprocess_image(pil_img: Image.Image) -> Image.Image:
    """
    Preprocesamiento de imagen antes del OCR para mejorar la precisión.
    Escala de grises -> autocontraste -> deskew -> nitidez -> upscaling.
    """
    # 1. Escala de grises
    img = pil_img.convert("L")
    # 2. Autocontraste real (estira el histograma; ayuda con escaneos lavados)
    img = ImageOps.autocontrast(img)
    # 3. Deskew: estimar y corregir inclinación si es significativa
    angle = _estimate_skew_angle(img)
    if abs(angle) >= MIN_DESKEW_ANGLE:
        img = img.rotate(
            angle, resample=Image.BICUBIC, expand=True, fillcolor=255
        )
        logger.debug(f"Deskew aplicado: {angle:+.1f}°")
    # 4. Nitidez
    img = img.filter(ImageFilter.SHARPEN)
    # 5. Escalar si es muy pequeña (Tesseract rinde mejor con imágenes grandes)
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


def _extract_ocr_text(page: fitz.Page) -> dict:
    """
    Rasteriza una página, preprocesa y aplica OCR en un solo pase.

    Devuelve un dict con:
      - text: texto reconstruido SOLO con palabras de confianza suficiente
      - confidence: confianza promedio de las palabras válidas (0-100)
      - valid_words: nº de palabras válidas (prosa real)
      - total_words: nº total de tokens detectados (para el ratio de imagen)
    """
    # Rasterizar a imagen
    mat = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72)
    pix = page.get_pixmap(matrix=mat)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))

    # Preprocesar
    processed = _preprocess_image(pil_img)

    # OCR único con datos detallados (de aquí sale TANTO el texto como la
    # confianza, así ambos comparten exactamente el mismo filtrado).
    data = pytesseract.image_to_data(
        processed,
        lang=TESSERACT_LANG,
        config=TESSERACT_CONFIG,
        output_type=pytesseract.Output.DICT,
    )

    n = len(data["text"])
    total_words = 0
    valid_confidences: list[int] = []
    # Reagrupar palabras buenas por línea para reconstruir un texto legible.
    lines: dict[tuple, list[str]] = {}

    for i in range(n):
        raw = data["text"][i]
        word = raw.strip()
        if not word:
            continue
        total_words += 1

        conf = int(data["conf"][i])
        if conf < MIN_WORD_CONF:
            continue  # ruido: fuera del texto y de la confianza

        # Texto indexable: palabra confiable (incluye números confiables).
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)

        # Métrica de confianza: solo palabras de prosa real.
        if _is_valid_word(word):
            valid_confidences.append(conf)

    # Texto en orden de lectura (las claves de Tesseract ya vienen ordenadas).
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items())).strip()

    avg_conf = (
        sum(valid_confidences) / len(valid_confidences) if valid_confidences else 0.0
    )

    return {
        "text": text,
        "confidence": avg_conf,
        "valid_words": len(valid_confidences),
        "total_words": total_words,
    }


def process_pdf(pdf_path: str) -> list[dict]:
    """
    Procesa un PDF completo página por página.
    Para cada página decide: ¿digital, escaneada, o mayormente imagen?

    Devuelve una lista de diccionarios (una entrada por página, incluidas las
    saltadas, para que el conteo total de páginas se mantenga):
    [
        {
            "page_num": 1,
            "text": "contenido...",
            "method": "digital" | "ocr" | "imagen",
            "confidence": 100.0 | 85.3 | 0.0
        },
        ...
    ]

    Nota de contrato: el worker promedia la confianza SOLO sobre páginas con
    method == "ocr", así que las páginas "imagen" (saltadas) no la contaminan.
    """
    doc = fitz.open(pdf_path)
    results = []

    n_digital = n_ocr = n_imagen = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        numero = page_num + 1

        if _page_has_text(page):
            text = _extract_digital_text(page)
            results.append({
                "page_num": numero,
                "text": text,
                "method": "digital",
                "confidence": 100.0,
            })
            n_digital += 1
            logger.info(f"Página {numero}: digital ({len(text)} chars)")
            continue

        ocr = _extract_ocr_text(page)

        # ¿Mayormente imagen? Pocas palabras válidas -> saltar.
        if ocr["valid_words"] < MIN_VALID_WORDS:
            ratio = (
                ocr["valid_words"] / ocr["total_words"]
                if ocr["total_words"] else 0.0
            )
            results.append({
                "page_num": numero,
                "text": "",
                "method": "imagen",
                "confidence": 0.0,
            })
            n_imagen += 1
            logger.info(
                f"Página {numero}: SALTADA (mayormente imagen) — "
                f"{ocr['valid_words']} palabras válidas de {ocr['total_words']} "
                f"(ratio {ratio:.0%})"
            )
            continue

        results.append({
            "page_num": numero,
            "text": ocr["text"],
            "method": "ocr",
            "confidence": round(ocr["confidence"], 2),
        })
        n_ocr += 1
        logger.info(
            f"Página {numero}: OCR (confianza={ocr['confidence']:.1f}%, "
            f"{ocr['valid_words']} palabras válidas, {len(ocr['text'])} chars)"
        )

    doc.close()

    # Resumen del libro completo
    ocr_confs = [r["confidence"] for r in results if r["method"] == "ocr"]
    avg_ocr = sum(ocr_confs) / len(ocr_confs) if ocr_confs else 0.0
    logger.info(
        f"[Resumen OCR] {len(results)} páginas: "
        f"{n_digital} digitales, {n_ocr} OCR, {n_imagen} saltadas (imagen). "
        f"Confianza OCR promedio: {avg_ocr:.1f}%"
    )

    return results
