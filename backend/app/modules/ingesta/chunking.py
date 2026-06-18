"""
Chunking semántico: divide el texto extraído en fragmentos
con un tamaño manejable para embeddings y RAG.
"""

# Tamaño objetivo por chunk (en caracteres). 800 chars ≈ ~200 tokens ≈ buen balance
# entre tener suficiente contexto y no sobrecargar el embedding ni el prompt.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150  # solapamiento para no perder contexto entre chunks


def chunk_pages(
    pages: list[dict],
    libro_id: int,
    asignatura: str,
    grado: str,
) -> list[dict]:
    """
    Recibe la salida de process_pdf() y devuelve chunks listos para indexar.

    Cada chunk tiene:
    - text: el contenido del fragmento
    - metadata: {libro_id, asignatura, grado, page_num, method, confidence}
    - chunk_id: identificador único para ChromaDB
    """
    chunks = []
    chunk_counter = 0

    for page in pages:
        text = page["text"]
        if not text or len(text.strip()) < 20:
            continue  # saltar páginas casi vacías

        # Dividir el texto de la página en chunks con solapamiento
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE

            # Intentar cortar en un punto natural (fin de oración o párrafo)
            if end < len(text):
                # Buscar el último punto, signo de interrogación o salto de línea
                for sep in ["\n\n", "\n", ". ", "? ", "! "]:
                    last_sep = text.rfind(sep, start + CHUNK_SIZE // 2, end + 100)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break

            chunk_text = text[start:end].strip()

            if len(chunk_text) >= 20:  # no guardar chunks minúsculos
                chunk_counter += 1
                chunk_id = f"libro_{libro_id}_chunk_{chunk_counter:05d}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "metadata": {
                        "libro_id": libro_id,
                        "asignatura": asignatura,
                        "grado": grado,
                        "page_num": page["page_num"],
                        "method": page["method"],
                        "confidence": page["confidence"],
                    },
                })

            start = end - CHUNK_OVERLAP
            if start < 0:
                start = 0
            if end >= len(text):
                break

    return chunks
