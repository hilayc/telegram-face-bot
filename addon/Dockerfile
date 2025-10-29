ARG BUILD_FROM
FROM $BUILD_FROM

ENV \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PIP_NO_CACHE_DIR=1 \
  LANG=C.UTF-8

# Install system dependencies and Python
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     python3 \
     python3-pip \
     python3-venv \
     python3-setuptools \
     python3-wheel \
     jq \
     build-essential \
     cmake \
     libopenblas-dev \
     liblapack-dev \
     libx11-dev \
     libjpeg62-turbo-dev \
     libpng-dev \
     zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/telegram-face-bot

# Install Python dependencies
COPY requirements.txt /opt/telegram-face-bot/requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel \
  && pip3 install --no-cache-dir -r requirements.txt face_recognition

# Copy application code
COPY main.py /opt/telegram-face-bot/main.py

# S6 service files
COPY rootfs / 

# Ensure run scripts are executable
RUN chmod +x /etc/services.d/telegram-face-bot/run

VOLUME ["/data"]


