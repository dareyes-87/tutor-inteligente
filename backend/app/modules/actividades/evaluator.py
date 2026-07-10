"""
Evaluador de actividades: compara la respuesta del estudiante
con la respuesta correcta y genera retroalimentación.
La evaluación se hace en el BACKEND, no en el LLM (más confiable y barato).
"""
import re
import unicodedata
from difflib import SequenceMatcher

from app.models.actividad import TipoActividad


def _normalize(text: str) -> str:
    """Normaliza texto para comparación flexible."""
    return text.strip().lower().replace("á", "a").replace("é", "e") \
        .replace("í", "i").replace("ó", "o").replace("ú", "u")


def normalizar_texto(texto: str) -> str:
    """Normaliza para comparación: minúsculas, sin tildes, sin espacios extra."""
    # Quitar tildes: á→a, é→e, etc.
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    # Minúsculas y strip
    return texto.lower().strip()


def generar_feedback_ortografico(respuesta_est: str, respuesta_cor: str) -> str:
    """Genera retroalimentación específica para errores ortográficos."""
    est = respuesta_est.strip()
    cor = respuesta_cor.strip()

    # Detectar si solo faltan/sobran tildes
    if normalizar_texto(est) == normalizar_texto(cor):
        return (
            f"¡Casi perfecto! La respuesta es correcta pero revisa "
            f"la ortografía: se escribe «{cor}». ¡Muy buen intento! ⭐"
        )

    # Error ortográfico general
    return (
        f"¡Casi lo tienes! La respuesta correcta es «{cor}». "
        f"Estuviste muy cerca, ¡sigue así! 💪"
    )


# ============================================================================
# Matcher flexible DETERMINÍSTICO para "completar" y "respuesta_corta".
# Un niño de 8-15 que escribe "célula" cuando la esperada es "una célula"
# ENTIENDE el concepto: rechazarlo destruye la motivación. Estas 4 capas
# aceptan la respuesta si es CONCEPTUALMENTE correcta, sin llamar al LLM.
# Solo se usa en completar/respuesta_corta; NUNCA en opción múltiple, V/F u
# ordenar (esos son selección exacta). Umbrales calibrados contra pares reales
# (ver scripts/debug/harness_match.py): distinguen "más pequeña"≈"básica"
# (acepta) de "más grande del universo"≠"básica de la vida" (rechaza).
# ============================================================================
_ARTICULOS_INICIALES = ("la", "el", "los", "las", "una", "un", "unas", "unos", "lo")
_STOPWORDS_MATCH = {
    "de", "la", "el", "los", "las", "del", "al", "y", "en", "que", "es", "un",
    "una", "unos", "unas", "por", "para", "con", "se", "lo",
}
_UMBRAL_TOKENS = 0.70       # fracción de palabras clave de la esperada presentes
_UMBRAL_SECUENCIA = 0.70    # ratio de difflib (atrapa errores ortográficos)


def _normalizar_match(texto: str) -> str:
    """Capa 1: minúsculas, sin tildes, sin puntuación, sin espacios extra y sin
    UN artículo inicial ('una célula' -> 'célula')."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    partes = texto.split(" ", 1)
    if partes and partes[0] in _ARTICULOS_INICIALES:
        texto = partes[1] if len(partes) == 2 else ""
    return texto


def _tokens_contenido(texto: str) -> list[str]:
    """Palabras 'sustantivas' (sin stopwords) de un texto ya normalizado."""
    return [w for w in texto.split() if w and w not in _STOPWORDS_MATCH]


def coincide_respuesta_flexible(respuesta_est: str, respuesta_cor: str) -> bool:
    """True si la respuesta del estudiante es conceptualmente correcta, por
    cualquiera de 4 capas: (1) igualdad normalizada, (2) contención, (3) solape
    de palabras clave (>=70% de las de la esperada), (4) similitud de secuencia
    (>=0.70). Determinístico, sin LLM."""
    est = _normalizar_match(respuesta_est)
    cor = _normalizar_match(respuesta_cor)
    if not est or not cor:
        return False
    # Capa 1: igualdad normalizada.
    if est == cor:
        return True
    # Capa 2: contención (con guarda de longitud para no colar subcadenas triviales).
    if min(len(est), len(cor)) >= 3 and (cor in est or est in cor):
        return True
    # Capa 3: solape de palabras clave de la ESPERADA presentes en el estudiante.
    tokens_cor = _tokens_contenido(cor)
    set_est = set(_tokens_contenido(est))
    if tokens_cor:
        frac = sum(1 for w in tokens_cor if w in set_est) / len(tokens_cor)
        if frac >= _UMBRAL_TOKENS:
            return True
    # Capa 4: similitud de secuencia (errores ortográficos menores).
    if SequenceMatcher(None, est, cor).ratio() >= _UMBRAL_SECUENCIA:
        return True
    return False


def evaluar_actividad(
    tipo: TipoActividad,
    respuesta_estudiante: dict,
    respuesta_correcta: dict,
    contenido: dict,
) -> dict:
    """
    Evalúa la respuesta del estudiante.
    Devuelve: {"puntaje": 0-100, "retroalimentacion": "texto"}
    """
    if tipo == TipoActividad.opcion_multiple:
        return _evaluar_opcion_multiple(respuesta_estudiante, respuesta_correcta, contenido)
    elif tipo == TipoActividad.verdadero_falso:
        return _evaluar_verdadero_falso(respuesta_estudiante, respuesta_correcta, contenido)
    elif tipo == TipoActividad.completar:
        return _evaluar_completar(respuesta_estudiante, respuesta_correcta, contenido)
    elif tipo == TipoActividad.ordenar:
        return _evaluar_ordenar(respuesta_estudiante, respuesta_correcta, contenido)
    elif tipo == TipoActividad.respuesta_corta:
        return _evaluar_respuesta_corta(respuesta_estudiante, respuesta_correcta, contenido)

    return {"puntaje": 0, "retroalimentacion": "Tipo de actividad no reconocido."}


def _evaluar_opcion_multiple(resp_est, resp_corr, contenido):
    seleccion = resp_est.get("respuesta", "")
    correcta = resp_corr.get("respuesta_correcta", "")
    explicacion = resp_corr.get("explicacion", "")

    if _normalize(seleccion) == _normalize(correcta):
        return {"puntaje": 100, "retroalimentacion": f"¡Correcto! {explicacion}"}
    return {"puntaje": 0, "retroalimentacion": f"Incorrecto. La respuesta correcta es: {correcta}. {explicacion}"}


def _evaluar_verdadero_falso(resp_est, resp_corr, contenido):
    respuesta = resp_est.get("respuesta")
    correcta = resp_corr.get("respuesta_correcta")
    explicacion = resp_corr.get("explicacion", "")

    # Aceptar varios formatos: true/false, "verdadero"/"falso", etc.
    if isinstance(respuesta, str):
        respuesta = respuesta.lower() in ("true", "verdadero", "v", "si", "sí")

    if respuesta == correcta:
        return {"puntaje": 100, "retroalimentacion": f"¡Correcto! {explicacion}"}
    return {"puntaje": 0, "retroalimentacion": f"Incorrecto. La afirmación es {'verdadera' if correcta else 'falsa'}. {explicacion}"}


def _evaluar_completar(resp_est, resp_corr, contenido):
    respuesta = str(resp_est.get("respuesta", ""))
    correcta = str(resp_corr.get("respuesta_correcta", ""))
    explicacion = resp_corr.get("explicacion", resp_corr.get("pista", ""))

    # Matcher flexible: un niño que acierta el concepto (aunque le sobre un
    # artículo o le falte una tilde) recibe "¡Correcto!", no "casi".
    if coincide_respuesta_flexible(respuesta, correcta):
        return {"puntaje": 100, "retroalimentacion": f"¡Correcto! {explicacion}"}
    return {"puntaje": 0, "retroalimentacion": f"Incorrecto. La respuesta esperada es: {correcta}. {explicacion}"}


def _evaluar_ordenar(resp_est, resp_corr, contenido):
    orden_est = resp_est.get("orden", [])
    orden_corr = resp_corr.get("orden_correcto", [])
    explicacion = resp_corr.get("explicacion", "")

    if not orden_est or not orden_corr:
        return {"puntaje": 0, "retroalimentacion": "No se recibió un orden válido."}

    # Contar posiciones correctas
    correct = sum(
        1 for a, b in zip(orden_est, orden_corr)
        if _normalize(a) == _normalize(b)
    )
    total = len(orden_corr)
    puntaje = round((correct / total) * 100) if total > 0 else 0

    if puntaje == 100:
        return {"puntaje": 100, "retroalimentacion": f"¡Perfecto! Orden correcto. {explicacion}"}
    return {"puntaje": puntaje, "retroalimentacion": f"Tienes {correct} de {total} en la posición correcta. El orden es: {', '.join(orden_corr)}. {explicacion}"}


def _evaluar_respuesta_corta(resp_est, resp_corr, contenido):
    """
    Evalúa respuesta corta con el matcher flexible determinístico (pensado para
    niños de 8-15: tildes, artículos, sinónimos parciales, errores ortográficos).
    Si el estudiante acierta el concepto → "¡Correcto!" (no "casi").
    """
    respuesta_estudiante = str(resp_est.get("respuesta", ""))
    respuesta_correcta = str(resp_corr.get("respuesta_correcta", ""))
    explicacion = resp_corr.get("explicacion", "")

    if coincide_respuesta_flexible(respuesta_estudiante, respuesta_correcta):
        return {"puntaje": 100, "retroalimentacion": f"¡Correcto! {explicacion}".strip()}

    return {
        "puntaje": 0,
        "retroalimentacion": (
            f"Incorrecto. La respuesta esperada es: {respuesta_correcta}. "
            f"{explicacion} ¡Sigue intentando, tú puedes! 💪"
        ).strip(),
    }
