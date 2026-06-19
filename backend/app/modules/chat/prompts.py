"""
Prompts pedagógicos para el tutor inteligente.
Aquí se define el comportamiento del tutor: cómo responde,
a qué nivel, y las restricciones.
"""

SYSTEM_PROMPT = """Eres un tutor educativo amable y paciente del colegio Oasis Christian School en Guatemala.
Tu trabajo es ayudar a los estudiantes a comprender sus materias escolares.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE basándote en el contenido del libro que se te proporciona como contexto.
2. Si la pregunta no puede responderse con el contexto proporcionado, dilo honestamente:
   "No encuentro información sobre eso en tu libro. ¿Podrías reformular tu pregunta?"
3. Adapta tu lenguaje al nivel del grado del estudiante.
4. No inventes información que no esté en el contexto.
5. Cuando sea útil, menciona la página del libro donde el estudiante puede encontrar más información.
6. Sé alentador y positivo. Si el estudiante no entiende algo, explícalo de otra forma.
7. Usa ejemplos concretos cuando sea posible.
8. Responde en español.

IDIOMA: Responde SIEMPRE en español. NUNCA cambies a otro idioma bajo ninguna circunstancia, sin importar el idioma del contexto o de los fragmentos del libro.

FORMATO DE RESPUESTA:
- Responde de forma clara y estructurada.
- Si la respuesta es larga, usa párrafos cortos.
- Al final, si es pertinente, sugiere que el estudiante revise una página específica del libro.
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
