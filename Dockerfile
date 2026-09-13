FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        gcc \
        git \
        libc6-dev \
        libffi-dev \
        libnacl-dev \
        libopus0 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir wheel
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

COPY . /app

ENV TTS_DATA_DIR=/data/tts
RUN mkdir -p /data/tts
VOLUME ["/data"]

CMD ["python", "bot.py", "--voice"]
