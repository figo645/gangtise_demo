FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=5001 \
    APP_SERVER=gunicorn \
    DEBUG=0 \
    TMPDIR=/tmp

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        ffmpeg \
        gcc \
        git \
        libglib2.0-0 \
        libgl1 \
        libpq-dev \
        libsm6 \
        libxext6 \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 5001

CMD ["python3", "-u", "/app/app.py"]
