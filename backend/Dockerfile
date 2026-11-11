FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# torch CPU-only PRIMERO (evita descargar versión CUDA de 2GB)
RUN pip install --no-cache-dir torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelo de embeddings dentro de la imagen: en runtime no se depende de
# Hugging Face (HF_HUB_OFFLINE impide cualquier descarga posterior).
# Se descargan los dos modelos que acepta EMBEDDING_MODEL (app/config.py): MiniLM
# (por defecto) y multilingual-e5-small (ventana de 512 tokens, correcciones del jurado).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2'); SentenceTransformer('intfloat/multilingual-e5-small')"
ENV HF_HUB_OFFLINE=1

COPY . .

RUN mkdir -p /data/books

# Producción: migra (Alembic) y luego arranca uvicorn sin --reload, workers 1
COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]