"""
Generador de actividades: usa el LLM para crear ejercicios
basados en el contenido de los libros (fragmentos RAG).
"""
import logging
import random
import re

from app.llm.client import llm_client
from app.models.actividad import TipoActividad

logger = logging.getLogger(__name__)

# Símbolos matemáticos especiales: ningún teclado estándar de Android/iOS los
# tiene, así que NUNCA pueden ser la respuesta esperada de "completar" o
# "respuesta_corta" (el estudiante no podría escribirlos). Esas preguntas deben
# generarse como "opcion_multiple" (ver _actividad_invalida / generar_actividad).
SIMBOLOS_ESPECIALES = set("∈∉⊂⊄⊆⊇∪∩≤≥≠")


def _contiene_simbolo_especial(texto: str | None) -> bool:
    return any(c in SIMBOLOS_ESPECIALES for c in (texto or ""))


def _palabras_junto_al_hueco(oracion: str) -> set[str]:
    """Palabras (en minúsculas) inmediatamente antes y después de cada "___"."""
    tokens = re.findall(r"___|\w+", oracion or "")
    palabras = set()
    for i, tok in enumerate(tokens):
        if tok != "___":
            continue
        if i > 0:
            palabras.add(tokens[i - 1].lower())
        if i + 1 < len(tokens):
            palabras.add(tokens[i + 1].lower())
    return palabras


def _hueco_es_redundante(oracion: str | None, respuesta_correcta: str) -> bool:
    """True si la respuesta esperada ya está escrita junto al hueco (___), lo
    que vuelve la oración redundante/sin sentido pedagógico (Bug A: "decimos
    que pertenece (___) al conjunto" con respuesta "pertenece").
    """
    if not oracion or not respuesta_correcta:
        return False
    resp = respuesta_correcta.strip().lower()
    if not resp:
        return False
    for palabra in _palabras_junto_al_hueco(oracion):
        if resp == palabra or resp.rstrip("s") == palabra.rstrip("s"):
            return True
    return False


_PATRON_INCISO = re.compile(r"^\s*[A-Da-d]\s*[\.\):]\s*")


def _quitar_inciso(texto: str) -> str:
    """Quita un inciso ("A.", "b)", "C:") que el LLM haya antepuesto a una
    opción de opción múltiple, a pesar de que el prompt se lo pide
    explícitamente. Decisión de producto: el estudiante solo toca la opción,
    no necesita letras de inciso (y menos si el LLM las genera desordenadas:
    A, D, B, C confunde más que ayuda)."""
    return _PATRON_INCISO.sub("", texto or "", count=1).strip()


def _actividad_invalida(tipo: TipoActividad, result: dict) -> str | None:
    """Guardrail determinístico post-generación: devuelve la razón por la que
    la actividad NO sirve, o None si está bien.

    Solo aplica a "completar" y "respuesta_corta" (los únicos tipos donde el
    estudiante escribe la respuesta en un campo libre):
      - Bug B: la pregunta "gira en torno a" un símbolo matemático especial
        (∈, ∉, ⊂, ⊄, ⊆, ⊇, ∪, ∩, ≤, ≥, ≠) que no se puede teclear — ya sea
        porque la respuesta_correcta ES el símbolo, o porque el símbolo
        aparece en el texto visible (oración/pregunta). Esto último cubre un
        caso real: el LLM esquiva "no uses el símbolo como respuesta"
        escribiendo el símbolo en la oración y dejando un hueco/respuesta
        inventada sin sentido en otro lado (ej. oración "...pertenece (∈) al
        conjunto... ___ se simboliza con el símbolo e" con respuesta "e").
      - Bug A (solo "completar"): el hueco queda pegado a una palabra igual a
        la respuesta esperada (hueco redundante).
    """
    if tipo not in (TipoActividad.completar, TipoActividad.respuesta_corta):
        return None
    respuesta = result.get("respuesta_correcta")
    respuesta_str = str(respuesta) if respuesta is not None else None
    texto_visible = result.get("oracion") if tipo == TipoActividad.completar else result.get("pregunta")
    if _contiene_simbolo_especial(respuesta_str) or _contiene_simbolo_especial(texto_visible):
        return "la pregunta gira en torno a un símbolo matemático especial (no se puede teclear)"
    if tipo == TipoActividad.completar and _hueco_es_redundante(
        result.get("oracion"), respuesta_str or ""
    ):
        return "el hueco queda junto a una palabra igual a la respuesta (hueco redundante)"
    return None


# Los ejemplos usan placeholders ABSTRACTOS a propósito: si traen un tema real
# (p. ej. "energía cinética" o "ciclo del agua"), el modelo 7B tiende a copiarlos
# literalmente en vez de basarse en los fragmentos del libro. Mantenerlos genéricos
# obliga al LLM a tomar el contenido del contexto.
ACTIVITY_PROMPTS = {
    TipoActividad.opcion_multiple: """Genera UNA pregunta de opción múltiple basada en el contexto.
NO antepongas letras ni números de inciso ("A.", "B)", "1.", etc.) a las opciones: escribe SOLO el texto de la opción, el estudiante las toca directamente sin necesitar una letra.
REGLAS CRÍTICAS para los distractores (las opciones incorrectas):
- Cada distractor debe ser CLARAMENTE INCORRECTO según el libro, no ambiguo ni parcialmente correcto.
- NUNCA generes un distractor que podría ser interpretado como correcto por un estudiante que entiende el tema (por ejemplo, la negación exacta de una afirmación verdadera casi siempre también es defendible como cierta o falsa según el caso: evita ese patrón).
- Los distractores deben ser plausibles (no absurdos) pero inequívocamente incorrectos.
- ANTES de responder, verifica que SOLO UNA opción sea defendible como correcta.
- Evita preguntas tipo "¿Cuál de las siguientes afirmaciones es correcta?" con varias opciones que podrían defenderse como ciertas. Prefiere preguntas específicas y concretas (ej. "¿Qué significa que A esté contenido en B?") en vez de pedir juzgar afirmaciones abstractas.
Responde SOLO con JSON válido, sin texto adicional:
{
    "pregunta": "la pregunta",
    "opciones": ["opción 1 (sin letra de inciso)", "opción 2 (sin letra de inciso)", "opción 3 (sin letra de inciso)", "opción 4 (sin letra de inciso)"],
    "respuesta_correcta": "la opción correcta (texto exacto de una de las opciones, sin letra de inciso)",
    "explicacion": "por qué esa es la respuesta correcta"
}""",

    TipoActividad.verdadero_falso: """Genera UNA afirmación de verdadero o falso basada en el contexto.
Responde SOLO con JSON válido, sin texto adicional:
{
    "afirmacion": "la afirmación a evaluar",
    "respuesta_correcta": true o false,
    "explicacion": "por qué es verdadero o falso"
}""",

    TipoActividad.completar: """Genera UNA oración para completar. La oración debe salir TEXTUALMENTE del libro (toma una frase real del contenido y reemplaza por ___ la palabra o término clave que el estudiante debe recordar). Usa ___ donde va la palabra faltante.
El espacio en blanco (___) DEBE reemplazar un TÉRMINO CLAVE del tema (nombre de estructura, órgano, proceso, concepto científico). NUNCA pongas el blank en verbos comunes (significa, tiene, es, son), artículos, preposiciones o conectores.
Ejemplo CORRECTO: "La ___ es la unidad básica de los seres vivos" (respuesta: célula).
Ejemplo INCORRECTO: "La célula ___ la unidad básica" (respuesta: es).
El hueco (___) NUNCA debe quedar junto a una palabra igual a la respuesta esperada (eso lo vuelve redundante). Ejemplo INCORRECTO: "decimos que pertenece (___) al conjunto" con respuesta "pertenece" (la palabra ya está escrita justo antes del hueco).
Si el término clave de este concepto es un símbolo matemático especial (∈, ∉, ⊂, ⊄, ⊆, ⊇, ∪, ∩, ≤, ≥, ≠), NO lo uses como respuesta del hueco: ningún teclado permite escribir esos símbolos. Elige en su lugar otro término clave que se escriba con palabras.
Responde SOLO con JSON válido, sin texto adicional (los valores son ejemplos de FORMATO, no de contenido):
{
    "oracion": "<una oración tomada del contexto con ___ en el TÉRMINO CLAVE>",
    "respuesta_correcta": "<el término clave exacto que va en ___, tal como aparece en el contexto>",
    "pista": "una pista para ayudar al estudiante"
}""",

    TipoActividad.ordenar: """Genera UN ejercicio de ordenar elementos basado en el libro. Los elementos deben ser conceptos, pasos o etapas QUE APARECEN en el libro (una secuencia o proceso descrito en el libro). No uses procesos que no estén en el libro.
Responde SOLO con JSON válido, sin texto adicional (los valores son ejemplos de FORMATO, no de contenido):
{
    "instruccion": "<instrucción de qué ordenar, sobre el proceso del contexto>",
    "elementos_desordenados": ["<elemento del contexto>", "<elemento del contexto>", "<elemento del contexto>"],
    "orden_correcto": ["<los mismos elementos en el orden correcto según el contexto>"],
    "explicacion": "explicación del orden correcto según el contexto"
}""",

    TipoActividad.respuesta_corta: """Genera UNA pregunta de respuesta corta basada en el contexto.
La pregunta DEBE pedir UN SOLO TÉRMINO o CONCEPTO específico. Formúlala como: "¿Cómo se llama el hueso que protege al cerebro?" (respuesta: cráneo). NUNCA preguntes dos cosas en una ("¿qué parte Y cuál es su función?"). La respuesta esperada debe ser de 1 a 3 palabras como máximo.
NUNCA hagas una pregunta cuya respuesta sea un símbolo matemático especial (∈, ∉, ⊂, ⊄, ⊆, ⊇, ∪, ∩, ≤, ≥, ≠): el estudiante escribe la respuesta en un campo de texto libre y ningún teclado tiene esos símbolos, así que sería imposible de responder. Si el concepto involucra uno de esos símbolos, pregunta por otra cosa (una definición, un ejemplo, el nombre del concepto en palabras).
Responde SOLO con JSON válido, sin texto adicional:
{
    "pregunta": "la pregunta (pide un solo término)",
    "respuesta_correcta": "la respuesta esperada (1-3 palabras)",
    "palabras_clave": ["palabra1", "palabra2", "palabra3"],
    "explicacion": "respuesta completa para retroalimentación"
}""",
}


def _llamar_llm(tipo: TipoActividad, context: str, tema: str | None = None) -> dict | None:
    """Una llamada al LLM para un tipo de actividad dado. Devuelve el JSON crudo
    (sin separar contenido/respuesta_correcta) o None si falla."""
    activity_prompt = ACTIVITY_PROMPTS[tipo]

    tema_str = f" sobre el tema: {tema}" if tema else ""
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un profesor que crea ejercicios educativos para estudiantes de "
                f"primaria/secundaria en Guatemala. Crea ejercicios claros, en español.{tema_str} "
                "Genera la actividad EXCLUSIVAMENTE con el contenido del libro "
                "que se te da. NO uses tu conocimiento propio. NO inventes información ni ejemplos "
                "que no estén en el libro. "
                "IGNORA cualquier ejercicio, actividad resuelta, ejemplo resuelto o sección tipo "
                "'Mesa lista', 'Ahora es tu turno', 'Ejercicio', 'Practica' que aparezca en el "
                "libro: esas son actividades del libro, no la teoría del tema. Genera tu "
                "actividad basándote ÚNICAMENTE en las definiciones, conceptos, teoría y "
                "explicaciones del libro. "
                "SIEMPRE genera todo el contenido en ESPAÑOL. Nunca uses términos en inglés. "
                "Los términos científicos deben estar en español (ejemplo: profase, no prophase; "
                "célula, no cell). "
                "NUNCA uses las palabras 'fragmento', 'contexto', 'chunk' ni ningún término "
                "técnico de procesamiento de datos en tu respuesta: refiérete siempre al "
                "material como 'el libro' o 'tu libro de texto'."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Basándote ÚNICAMENTE en el siguiente contenido del libro:\n\n{context}\n\n"
                f"{activity_prompt}\n\n"
                "Recuerda: la actividad debe tratar sobre lo que dice el libro arriba, "
                "no sobre otros temas. Si alguna parte es un ejercicio del libro (por ejemplo "
                "'Mesa lista', 'Ahora es tu turno' u otro ejercicio ya resuelto o propuesto), "
                "IGNÓRALA como fuente y basa la actividad solo en la teoría/definiciones del "
                "resto del libro. "
                + (
                    f"Si el contexto es insuficiente para generar una actividad de calidad, "
                    f"genera una pregunta conceptual básica sobre el tema: {tema}."
                    if tema else ""
                )
            ),
        },
    ]

    result = llm_client.generate_json(messages)

    if result is None:
        # Reintentar una vez con prompt más estricto
        messages[-1]["content"] += "\n\nIMPORTANTE: Responde SOLO con el JSON, sin markdown, sin explicaciones adicionales."
        result = llm_client.generate_json(messages)

    if result and tipo == TipoActividad.opcion_multiple:
        # Guardrail determinístico: el prompt ya pide no anteponer incisos,
        # pero el LLM a veces los pone igual (y a veces desordenados,
        # p. ej. A, D, B, C). Se limpian aquí sin importar qué responda.
        if isinstance(result.get("opciones"), list):
            result["opciones"] = [
                _quitar_inciso(o) if isinstance(o, str) else o
                for o in result["opciones"]
            ]
        if isinstance(result.get("respuesta_correcta"), str):
            result["respuesta_correcta"] = _quitar_inciso(result["respuesta_correcta"])

        # Mezclar las opciones: el LLM tiende a poner la correcta de primera.
        # respuesta_correcta guarda el TEXTO (no el índice), y el evaluador
        # compara por texto, así que el shuffle no rompe la evaluación.
        if isinstance(result.get("opciones"), list):
            random.shuffle(result["opciones"])

    return result


def generar_actividad(
    tipo: TipoActividad, context: str, tema: str | None = None
) -> tuple[TipoActividad, dict | None]:
    """
    Genera una actividad usando el LLM.

    Guardrail post-generación (capa determinística): si `tipo` es "completar"
    o "respuesta_corta" y la actividad resulta inválida (respuesta = símbolo
    matemático especial que no se puede teclear, o hueco redundante — ver
    `_actividad_invalida`), se REGENERA forzando "opcion_multiple" en vez de
    devolver la actividad rota. El prompt YA le pide al LLM evitar estos casos,
    pero un caso similar (ejercicios del libro tratados como teoría) demostró
    que "solo prompt" no basta: se necesita esta capa para garantizar el
    comportamiento sin importar qué responda el LLM.

    Devuelve `(tipo_efectivo, dict | None)`: `tipo_efectivo` puede diferir del
    `tipo` pedido si se forzó la regeneración; el dict es None si falló.
    """
    result = _llamar_llm(tipo, context, tema)

    if result:
        razon = _actividad_invalida(tipo, result)
        if razon:
            logger.warning(
                f"Actividad {tipo.value} inválida ({razon}); regenerando como opcion_multiple"
            )
            result_omc = _llamar_llm(TipoActividad.opcion_multiple, context, tema)
            if result_omc:
                tipo = TipoActividad.opcion_multiple
                result = result_omc
            else:
                # No se pudo regenerar: mejor no devolver una actividad rota.
                logger.warning("No se pudo regenerar como opcion_multiple; se descarta la actividad")
                result = None

    if result:
        logger.info(f"Actividad {tipo.value} generada exitosamente")
    else:
        logger.warning(f"Fallo al generar actividad {tipo.value}")

    return tipo, result
