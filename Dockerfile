FROM python:3.12-bullseye

WORKDIR /app


# Install gcc
RUN apt-get update
RUN apt install -y gcc git libffi-dev libc-dev libffi-dev ffmpeg libopus0
RUN apt install -y python3-dev python3-pip libnacl-dev
RUN pip install wheel
COPY requirements.txt /app/requirements.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY . /app

ENV TTS_DATA_DIR=/data/tts
RUN mkdir -p /data/tts
VOLUME ["/data"]

CMD ["python", "bot.py", "--voice"]
