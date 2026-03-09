FROM python:3.12-bullseye

WORKDIR /app


# Install gcc
RUN apt-get update
RUN apt install -y gcc git libffi-dev libc-dev libffi-dev ffmpeg
RUN apt install -y python3-dev python3-pip libnacl-dev
RUN pip install wheel
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY . /app

CMD ["python", "bot.py", "--voice"]
