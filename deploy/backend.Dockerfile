# Routiq backend — production image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Mexico_City

# System deps for reportlab (fonts) and bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libfreetype6 \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r /app/requirements.txt

COPY backend/ /app/

# Directorio de uploads (montado como volumen en docker-compose)
RUN mkdir -p /app/uploads/logos && chmod -R 755 /app/uploads

# Run as non-root
RUN useradd -m -u 1000 routiq && chown -R routiq:routiq /app
USER routiq

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://127.0.0.1:8000/api/ || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
