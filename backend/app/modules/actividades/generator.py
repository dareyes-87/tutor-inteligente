"""
Generador de actividades: usa el LLM para crear ejercicios
basados en el contenido de los libros (fragmentos RAG).
"""
import logging

from app.llm.client import llm_client
from app.models.actividad import TipoActividad

logger = logging.getLogger(__name__)

ACTIVITY_PROMPTS = {
    TipoActividad.opcion_multiple: """Genera UNA pregunta de opción múltiple basada en el contexto.
Responde SOLO con JSON válido, sin texto adicional:
{
    "pregunta": "la pregunta",
    "opciones": ["opción A", "opción B", "opción C", "opción D"],
    "respuesta_correcta": "la opción correcta (texto exacto de una de las opciones)",
    "explicacion": "por qué esa es la respuesta correcta"
}""",

    TipoActividad.verdadero_falso: """Genera UNA afirmación de verdadero o falso basada en el contexto.
Responde SOLO con JSON válido, sin texto adicional:
{
    "afirmacion": "la afirmación a evaluar",
    "respuesta_correcta": true o false,
    "explicacion": "por qué es verdadero o falso"
}""",

    TipoActividad.completar: """Genera UNA oración para completar basada en el contexto. Usa ___ donde va la palabra faltante.
Responde SOLO con JSON válido, sin texto adicional:
{
    "oracion": "La energía ___ es la energía del movimiento.",
    "respuesta_correcta": "cinética",
    "pista": "una pista para ayudar al estudiante"
}""",

    TipoActividad.ordenar: """Genera UN ejercicio de ordenar elementos basado en el contexto (pasos de un proceso, secuencia cronológica, etc).
Responde SOLO con JSON válido, sin texto adicional:
{
    "instruccion": "Ordena los siguientes pasos del ciclo del agua:",
    "elementos_desordenados": ["Precipitación", "Evaporación", "Condensación", "Escorrentía"],
    "orden_correcto": ["Evaporación", "Condensación", "Precipitación", "Escorrentía"],
    "explicacion": "explicación del orden correcto"
}""",

    TipoActividad.respuesta_corta: """Genera UNA pregunta de respuesta corta basada en el contexto.
Responde SOLO con JSON válido, sin texto adicional:
{
    "pregunta": "la pregunta",
    "respuesta_correcta": "la respuesta esperada (breve)",
    "palabras_clave": ["palabra1", "palabra2", "palabra3"],
    "explicacion": "respuesta completa para retroalimentación"
}""",
}


def generar_actividad(tipo: TipoActividad, context: str, tema: str | None = None) -> dict | None:
    """
    Genera una actividad usando el LLM.
    Devuelve el dict con el contenido y la respuesta correcta, o None si falla.
    """
    activity_prompt = ACTIVITY_PROMPTS[tipo]

    tema_str = f" sobre el tema: {tema}" if tema else ""
    messages = [
        {
            "role": "system",
            "content": f"Eres un profesor que crea ejercicios educativos para estudiantes de primaria/secundaria en Guatemala. Crea ejercicios claros, en español.{tema_str}",
        },
        {
            "role": "user",
            "content": f"Basándote en el siguiente contenido del libro:\n\n{context}\n\n{activity_prompt}",
        },
    ]

    result = llm_client.generate_json(messages)

    if result is None:
        # Reintentar una vez con prompt más estricto
        messages[-1]["content"] += "\n\nIMPORTANTE: Responde SOLO con el JSON, sin markdown, sin explicaciones adicionales."
        result = llm_client.generate_json(messages)

    if result:
        logger.info(f"Actividad {tipo.value} generada exitosamente")
    else:
        logger.warning(f"Fallo al generar actividad {tipo.value}")

    return result
