FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        git \
        libc6-dev \
        libffi-dev \
        libnacl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements-base.txt /app/
RUN python -m pip install --no-cache-dir \
        wheel \
    && python -m pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.5,<2.15" \
    && python -m pip install --no-cache-dir \
    -r requirements.txt


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TTS_DATA_DIR=/data/tts \
    HF_HOME=/data/huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libopus0 \
        libsodium23 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY . /app

RUN mkdir -p /data/tts /data/huggingface
VOLUME ["/data"]

CMD ["python", "bot.py", "--voice"]
