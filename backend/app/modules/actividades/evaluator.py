"""
Evaluador de actividades: compara la respuesta del estudiante
con la respuesta correcta y genera retroalimentación.
La evaluación se hace en el BACKEND, no en el LLM (más confiable y barato).
"""
from app.models.actividad import TipoActividad


def _normalize(text: str) -> str:
    """Normaliza texto para comparación flexible."""
    return text.strip().lower().replace("á", "a").replace("é", "e") \
        .replace("í", "i").replace("ó", "o").replace("ú", "u")


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
    respuesta = _normalize(resp_est.get("respuesta", ""))
    palabras_clave = [_normalize(p) for p in resp_corr.get("palabras_clave", [])]
    explicacion = resp_corr.get("explicacion", "")

    if not palabras_clave:
        correcta = _normalize(resp_corr.get("respuesta_correcta", ""))
        if correcta and correcta in respuesta:
            return {"puntaje": 100, "retroalimentacion": f"¡Correcto! {explicacion}"}
        return {"puntaje": 0, "retroalimentacion": f"La respuesta esperada era: {resp_corr.get('respuesta_correcta', '')}. {explicacion}"}

    # Evaluar por palabras clave encontradas
    found = sum(1 for kw in palabras_clave if kw in respuesta)
    puntaje = round((found / len(palabras_clave)) * 100)

    if puntaje >= 80:
        return {"puntaje": puntaje, "retroalimentacion": f"¡Muy bien! {explicacion}"}
    elif puntaje >= 50:
        return {"puntaje": puntaje, "retroalimentacion": f"Bien, pero incompleto. {explicacion}"}
    return {"puntaje": puntaje, "retroalimentacion": f"Necesitas repasar. {explicacion}"}
