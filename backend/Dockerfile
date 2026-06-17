FROM python:3.12-slim

WORKDIR /app

# Dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código (en desarrollo se sobrescribe con el volumen del compose)
COPY . .

# --reload hace que el servidor se reinicie solo cuando editas un archivo
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
