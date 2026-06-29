FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# torch CPU-only PRIMERO (evita descargar versión CUDA de 2GB)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/books

# Producción: migra (Alembic) y luego arranca uvicorn sin --reload, workers 1
COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]