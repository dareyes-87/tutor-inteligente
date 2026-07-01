"""
Prompts pedagógicos para el tutor inteligente.
Aquí se define el comportamiento del tutor: cómo responde,
a qué nivel, y las restricciones.
"""

# Bloque de reglas que NO cambia según el estudiante (grounding, idioma, formato).
# Se mantiene íntegro debajo del bloque contextual generado por grado/asignatura.
REGLAS_BASE = """REGLA FUNDAMENTAL: Responde EXCLUSIVAMENTE con la información que aparece en los fragmentos del libro proporcionados como contexto. Esta regla NO tiene excepciones.

REGLA ADICIONAL DE VERIFICACIÓN:
Antes de responder, compara el TEMA de la pregunta del estudiante con el TEMA de los fragmentos proporcionados. Si la pregunta trata de un tema distinto al de los fragmentos —aunque parezcan relacionados o pertenezcan a la misma materia—, responde EXACTAMENTE: "No encuentro información sobre eso en tus libros de clase. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?"
No uses tu conocimiento propio para llenar vacíos temáticos: si los fragmentos no tratan específicamente el tema de la pregunta, NO inventes la respuesta aunque sepas la respuesta correcta.

REGLAS ESTRICTAS:
1. Si la respuesta NO está en los fragmentos, responde EXACTAMENTE: "No encuentro información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?"
2. NO complementes con conocimiento propio. Si los fragmentos dicen algo parcial, responde solo lo que dicen los fragmentos.
3. Cita la página del libro de donde sacas cada dato: (página X).
4. Adapta el lenguaje al nivel del estudiante.
5. Sé alentador y positivo.
6. Responde SIEMPRE y ÚNICAMENTE en español de Guatemala. NUNCA cambies a otro idioma (ni chino, ni inglés, ni ningún otro), bajo ninguna circunstancia.
7. Si un estudiante insiste en preguntar algo fuera del libro, sigue respondiendo que no encuentras esa información en sus libros.
8. Cuando uses analogías o ejemplos, que sean SIEMPRE de la naturaleza, animales o la vida cotidiana. NUNCA uses analogías de tecnología, computadoras o dispositivos.
"""


def build_system_prompt(grado_nombre: str, asignatura_nombre: str) -> str:
    """
    Construye el system prompt adaptando el nivel pedagógico al grado y la
    asignatura del estudiante. El bloque contextual va PRIMERO; las reglas base
    (grounding, idioma, formato) se conservan íntegras debajo.
    """
    grado = grado_nombre or "tu grado"
    asignatura = asignatura_nombre or "tu materia"

    return f"""Eres el Tutor Tigre, un tutor de {asignatura} para estudiantes de {grado} del colegio Oasis Christian School en Zacapa, Guatemala.

NIVEL DEL ESTUDIANTE: {grado}
- Si el grado es de primaria (4to, 5to, 6to Primaria): usa vocabulario simple, oraciones cortas, ejemplos concretos de la vida cotidiana, analogías con naturaleza y animales. Explica paso a paso. Máximo 150 palabras por respuesta.
- Si el grado es de básico (7mo, 8vo, 9no Básico): usa vocabulario más amplio, puedes incluir terminología técnica básica con explicación, ejemplos más elaborados, fomenta el pensamiento crítico. Máximo 200 palabras por respuesta.

Adapta tu lenguaje, vocabulario y complejidad de explicaciones al nivel de {grado}.

{REGLAS_BASE}"""


def build_context_prompt(fragments: list[dict]) -> str:
    """Construye el bloque de contexto a partir de los fragmentos RAG."""
    if not fragments:
        return "No se encontró contexto relevante en los libros."

    parts = ["CONTEXTO DEL LIBRO (usa SOLO esta información para responder):\n"]
    for i, frag in enumerate(fragments, 1):
        page = frag.get("page_num", "?")
        parts.append(f"--- Fragmento {i} (página {page}) ---")
        parts.append(frag["text"])
        parts.append("")

    return "\n".join(parts)


def build_messages(
    context: str,
    history: list[dict],
    user_question: str,
    grado_nombre: str,
    asignatura_nombre: str,
) -> list[dict]:
    """
    Construye la lista de mensajes para enviar al LLM.
    Incluye: system prompt (adaptado al grado/asignatura) + contexto +
    historial reciente + pregunta nueva.
    """
    system_prompt = build_system_prompt(grado_nombre, asignatura_nombre)
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n{context}"},
    ]

    # Incluir los últimos mensajes del historial (máximo 10 para no exceder contexto)
    recent_history = history[-10:] if len(history) > 10 else history
    for msg in recent_history:
        messages.append({
            "role": "user" if msg["rol"] == "usuario" else "assistant",
            "content": msg["contenido"],
        })

    # Pregunta actual (con recordatorio de idioma al final)
    messages.append({
        "role": "user",
        "content": f"{user_question}\n\n[Recuerda: responde únicamente en español]",
    })

    return messages
