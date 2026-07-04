"""Mapeo curado de emoji por tema, usado para las tarjetas de la micro-lección.

El LLM elige emojis libremente y a veces acierta poco (p. ej. 🧬 para
"Intersección de conjuntos" en Matemáticas). En vez de depender de su criterio,
el emoji de cada tarjeta se asigna DESPUÉS de generar el contenido, buscando
palabras clave del tema en este mapeo por asignatura.
"""

# Mapeo de palabras clave → emoji por asignatura.
# Se busca en el nombre del tema/concepto; la primera coincidencia gana.
EMOJI_MAP: dict[str, dict[str, str]] = {
    # === MATEMÁTICAS (asignatura_id=2) ===
    "matemáticas": {
        # Conjuntos
        "conjunto": "🔵",
        "intersección": "🔗",
        "unión": "➕",
        "subconjunto": "📦",
        "pertenencia": "📍",
        "diagrama de venn": "⭕",
        # Números
        "número": "🔢",
        "natural": "🔢",
        "entero": "🔢",
        "fracción": "🍕",
        "decimal": "🔢",
        # Operaciones
        "suma": "➕",
        "resta": "➖",
        "multiplicación": "✖️",
        "división": "➗",
        "potencia": "⬆️",
        "raíz": "√",
        # Geometría
        "geometría": "📐",
        "triángulo": "🔺",
        "círculo": "⭕",
        "ángulo": "📐",
        "perímetro": "📏",
        "área": "📐",
        # Álgebra
        "ecuación": "⚖️",
        "variable": "❌",
        "expresión": "📝",
        # Estadística
        "estadística": "📊",
        "gráfica": "📊",
        "promedio": "📊",
        "probabilidad": "🎲",
        # Default matemáticas
        "_default": "📐",
    },
    # === CIENCIAS NATURALES (asignatura_id=1) ===
    "ciencias naturales": {
        "célula": "🔬",
        "planta": "🌱",
        "animal": "🐾",
        "ecosistema": "🌍",
        "agua": "💧",
        "energía": "⚡",
        "cuerpo": "🫀",
        "sistema digestivo": "🍽️",
        "sistema respiratorio": "🫁",
        "sistema circulatorio": "🫀",
        "sistema nervioso": "🧠",
        "reproducción": "🌸",
        "nutrición": "🥗",
        "alimento": "🥗",
        "materia": "🧪",
        "átomo": "⚛️",
        "mezcla": "🧪",
        "fuerza": "💪",
        "movimiento": "🏃",
        "luz": "💡",
        "sonido": "🔊",
        "tierra": "🌎",
        "volcán": "🌋",
        "clima": "🌤️",
        "contaminación": "🏭",
        "_default": "🔬",
    },
    # === COMUNICACIÓN Y LENGUAJE (asignatura_id=3, futuro) ===
    "comunicación y lenguaje": {
        "lectura": "📖",
        "escritura": "✍️",
        "gramática": "📝",
        "ortografía": "🔤",
        "verbo": "📝",
        "sustantivo": "📝",
        "oración": "💬",
        "cuento": "📚",
        "poesía": "🎭",
        "comprensión": "📖",
        "_default": "📖",
    },
}


def get_emoji_for_topic(tema: str, asignatura_nombre: str) -> str:
    """Busca el emoji curado para un tema dado. Fallback: emoji default de la asignatura.

    Entre varias palabras clave que aparecen en el tema, gana la MÁS LARGA (más
    específica): p. ej. para "Intersección de conjuntos" tanto "conjunto" como
    "intersección" son substrings, pero "intersección" es más específica y debe
    ganar (🔗), no el genérico "conjunto" (🔵). Empates se resuelven por el orden
    de inserción en el mapeo.
    """
    tema_lower = (tema or "").lower()
    asig_lower = (asignatura_nombre or "").lower()

    asig_map = EMOJI_MAP.get(asig_lower, {})

    mejor_keyword: str | None = None
    mejor_emoji: str | None = None
    for keyword, emoji in asig_map.items():
        if keyword == "_default" or keyword not in tema_lower:
            continue
        if mejor_keyword is None or len(keyword) > len(mejor_keyword):
            mejor_keyword, mejor_emoji = keyword, emoji

    if mejor_emoji is not None:
        return mejor_emoji

    # Default de la asignatura (o genérico si la asignatura no está mapeada).
    return asig_map.get("_default", "📚")
