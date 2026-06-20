"""
Evaluador de actividades: compara la respuesta del estudiante
con la respuesta correcta y genera retroalimentación.
La evaluación se hace en el BACKEND, no en el LLM (más confiable y barato).
"""
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
    respuesta = _normalize(resp_est.get("respuesta", ""))
    correcta = _normalize(resp_corr.get("respuesta_correcta", ""))
    explicacion = resp_corr.get("explicacion", resp_corr.get("pista", ""))

    if respuesta == correcta:
        return {"puntaje": 100, "retroalimentacion": f"¡Correcto! {explicacion}"}
    # Coincidencia parcial
    if correcta in respuesta or respuesta in correcta:
        return {"puntaje": 50, "retroalimentacion": f"Casi. La respuesta exacta es: {resp_corr.get('respuesta_correcta', '')}. {explicacion}"}
    return {"puntaje": 0, "retroalimentacion": f"Incorrecto. La respuesta es: {resp_corr.get('respuesta_correcta', '')}. {explicacion}"}


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
    Evalúa respuesta corta con tolerancia ortográfica (pensado para niños de
    8-12 años: errores de tildes, letras confundidas, escritura fonética).
    """
    respuesta_estudiante = str(resp_est.get("respuesta", ""))
    respuesta_correcta = str(resp_corr.get("respuesta_correcta", ""))

    # Normalizar ambas (minúsculas, sin tildes, sin espacios extra)
    est_norm = normalizar_texto(respuesta_estudiante)
    cor_norm = normalizar_texto(respuesta_correcta)

    # Caso 1: Match exacto (normalizado) → 100 puntos
    if est_norm and est_norm == cor_norm:
        return {"puntaje": 100, "retroalimentacion": "¡Excelente! ¡Respuesta correcta! 🌟"}

    # Caso 2: Similitud alta (>= 0.80) → casi correcto, 70 puntos
    similitud = SequenceMatcher(None, est_norm, cor_norm).ratio()
    if similitud >= 0.80:
        feedback = generar_feedback_ortografico(respuesta_estudiante, respuesta_correcta)
        return {"puntaje": 70, "retroalimentacion": feedback}

    # Caso 3: La respuesta correcta está CONTENIDA en la del estudiante o
    # viceversa (ej: "el microscopio" vs "microscopio"). La guarda
    # `est_norm and cor_norm` evita que una respuesta vacía cuele un 85,
    # porque "" siempre está contenido en cualquier cadena.
    if est_norm and cor_norm and (cor_norm in est_norm or est_norm in cor_norm):
        return {
            "puntaje": 85,
            "retroalimentacion": f"¡Muy bien! La respuesta es: {respuesta_correcta}. ¡Casi perfecto! ⭐",
        }

    # Caso 4: Incorrecto → 0 puntos
    return {
        "puntaje": 0,
        "retroalimentacion": f"No es correcto. La respuesta es: {respuesta_correcta}. ¡Sigue intentando, tú puedes! 💪",
    }
