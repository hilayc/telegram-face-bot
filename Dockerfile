FROM python:3.11-slim

# System-level dependencies for dlib/face_recognition and Pillow
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       cmake \
       libopenblas-dev \
       liblapack-dev \
       libx11-dev \
       libjpeg62-turbo-dev \
       libpng-dev \
       zlib1g-dev \
       jq \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt
RUN pip install --upgrade pip setuptools wheel
RUN pip install python-telegram-bot face_recognition Pillow cryptography cffi

# Copy app source
COPY main.py /app/main.py
COPY dlib /app/dlib

# Data directory for stored encodings per user (matches main.py DATA_DIR="/data")
RUN mkdir -p /data
RUN mkdir -p /config/known_faces
VOLUME ["/data", "/config/known_faces"]

# Run the bot; token is read from env TELEGRAM_BOT_API_TOKEN
# Add entrypoint that reads HA add-on options.json if env not set
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]


