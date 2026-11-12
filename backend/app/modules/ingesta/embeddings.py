"""
Generación de embeddings con sentence-transformers.
Corre en CPU dentro del backend — no necesita GPU.
El modelo se carga UNA vez al arrancar y se reutiliza.

Modelo configurable con EMBEDDING_MODEL (config.py):
- paraphrase-multilingual-MiniLM-L12-v2 (por defecto): 384 dim, ventana de 128 tokens.
- intfloat/multilingual-e5-small: 384 dim, ventana de 512 tokens; exige los
  prefijos "passage: " (al indexar) y "query: " (al buscar).
"""
import logging
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = settings.EMBEDDING_MODEL
ES_E5 = "e5" in MODEL_NAME.lower()

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Carga el modelo de embeddings (singleton, se carga una sola vez)."""
    global _model
    if _model is None:
        logger.info(f"Cargando modelo de embeddings: {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Modelo de embeddings cargado.")
    return _model


def generate_embeddings(texts: list[str], es_consulta: bool = False) -> list[list[float]]:
    """
    Genera embeddings para una lista de textos.
    Devuelve una lista de vectores (listas de floats).
    `es_consulta=True` para la pregunta del estudiante (solo cambia algo con e5).
    """
    if ES_E5:
        prefijo = "query: " if es_consulta else "passage: "
        texts = [prefijo + t for t in texts]
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()
