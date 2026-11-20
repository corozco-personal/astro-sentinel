# Dockerfile para TESS Black Hole Sentinel
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema requeridas por astropy y gcc
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requerimientos
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del proyecto
COPY . /app/

# Crear directorios de salida
RUN mkdir -p /app/outputs/candidates /app/outputs/plots

EXPOSE 5055

# Variables de entorno por defecto
ENV PORT=5055
ENV PYTHONUNBUFFERED=1

CMD ["python", "app/server.py", "5055"]
