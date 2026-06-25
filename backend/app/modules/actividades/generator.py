"""
Generador de actividades: usa el LLM para crear ejercicios
basados en el contenido de los libros (fragmentos RAG).
"""
import logging

from app.llm.client import llm_client
from app.models.actividad import TipoActividad

logger = logging.getLogger(__name__)

# Los ejemplos usan placeholders ABSTRACTOS a propósito: si traen un tema real
# (p. ej. "energía cinética" o "ciclo del agua"), el modelo 7B tiende a copiarlos
# literalmente en vez de basarse en los fragmentos del libro. Mantenerlos genéricos
# obliga al LLM a tomar el contenido del contexto.
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

    TipoActividad.completar: """Genera UNA oración para completar. La oración debe salir TEXTUALMENTE del contexto (toma una frase real de los fragmentos y reemplaza por ___ la palabra o término clave que el estudiante debe recordar). Usa ___ donde va la palabra faltante.
Responde SOLO con JSON válido, sin texto adicional (los valores son ejemplos de FORMATO, no de contenido):
{
    "oracion": "<una oración tomada del contexto con ___ en la palabra clave>",
    "respuesta_correcta": "<la palabra exacta que va en ___, tal como aparece en el contexto>",
    "pista": "una pista para ayudar al estudiante"
}""",

    TipoActividad.ordenar: """Genera UN ejercicio de ordenar elementos basado en el contexto. Los elementos deben ser conceptos, pasos o etapas QUE APARECEN en los fragmentos (una secuencia o proceso descrito en el contexto). No uses procesos que no estén en el contexto.
Responde SOLO con JSON válido, sin texto adicional (los valores son ejemplos de FORMATO, no de contenido):
{
    "instruccion": "<instrucción de qué ordenar, sobre el proceso del contexto>",
    "elementos_desordenados": ["<elemento del contexto>", "<elemento del contexto>", "<elemento del contexto>"],
    "orden_correcto": ["<los mismos elementos en el orden correcto según el contexto>"],
    "explicacion": "explicación del orden correcto según el contexto"
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
            "content": (
                "Eres un profesor que crea ejercicios educativos para estudiantes de "
                f"primaria/secundaria en Guatemala. Crea ejercicios claros, en español.{tema_str} "
                "Genera la actividad EXCLUSIVAMENTE con el contenido de los fragmentos del libro "
                "que se te dan. NO uses tu conocimiento propio. NO inventes información ni ejemplos "
                "que no estén en los fragmentos."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Basándote ÚNICAMENTE en el siguiente contenido del libro:\n\n{context}\n\n"
                f"{activity_prompt}\n\n"
                "Recuerda: la actividad debe tratar sobre lo que dicen los fragmentos de arriba, "
                "no sobre otros temas."
            ),
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
