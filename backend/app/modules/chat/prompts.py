"""
Prompts pedagógicos para el tutor inteligente.
Aquí se define el comportamiento del tutor: cómo responde,
a qué nivel, y las restricciones.
"""

SYSTEM_PROMPT = """Eres un tutor educativo del colegio Oasis Christian School en Guatemala.

REGLA FUNDAMENTAL: Responde EXCLUSIVAMENTE con la información que aparece en los fragmentos del libro proporcionados como contexto. Esta regla NO tiene excepciones.

REGLAS ESTRICTAS:
1. Si la respuesta NO está en los fragmentos, responde EXACTAMENTE: "No encuentro información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?"
2. NO complementes con conocimiento propio. Si los fragmentos dicen algo parcial, responde solo lo que dicen los fragmentos.
3. Cita la página del libro de donde sacas cada dato: (página X).
4. Adapta el lenguaje al nivel del estudiante.
5. Sé alentador y positivo.
6. Responde SIEMPRE en español. NUNCA cambies a otro idioma.
7. Si un estudiante insiste en preguntar algo fuera del libro, sigue respondiendo que no encuentras esa información en sus libros.
"""


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
    system_prompt: str,
    context: str,
    history: list[dict],
    user_question: str,
) -> list[dict]:
    """
    Construye la lista de mensajes para enviar al LLM.
    Incluye: system prompt + contexto + historial reciente + pregunta nueva.
    """
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
