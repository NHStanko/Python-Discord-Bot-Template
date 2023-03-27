FROM python:3.8-bullseye

WORKDIR /app

COPY . /app
# Install gcc
RUN apt-get update
RUN apt install -y gcc libffi-dev libc-dev libffi-dev ffmpeg
RUN apt install -y python3-dev python3-pip libnacl-dev
RUN pip install wheel
RUN pip install -r requirements.txt


CMD ["python", "bot.py"]