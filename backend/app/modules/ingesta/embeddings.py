"""
Generación de embeddings con sentence-transformers (MiniLM).
Corre en CPU dentro del backend — no necesita GPU.
El modelo se carga UNA vez al arrancar y se reutiliza.
"""
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Modelo multilingüe, buen rendimiento en español, liviano (~120MB)
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Carga el modelo de embeddings (singleton, se carga una sola vez)."""
    global _model
    if _model is None:
        logger.info(f"Cargando modelo de embeddings: {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Modelo de embeddings cargado.")
    return _model


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Genera embeddings para una lista de textos.
    Devuelve una lista de vectores (listas de floats).
    """
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()
