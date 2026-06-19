FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema para OCR y procesamiento de PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código (en desarrollo se sobrescribe con el volumen del compose)
COPY . .

# Directorio para almacenar los PDFs subidos
RUN mkdir -p /data/books

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
