FROM python:3.12-bullseye

WORKDIR /app


# Install gcc
RUN apt-get update
RUN apt install -y gcc libffi-dev libc-dev libffi-dev ffmpeg
RUN apt install -y python3-dev python3-pip libnacl-dev
RUN pip install wheel
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
RUN pip install "discord.py[voice] @ git+https://github.com/rapptz/discord.py"

COPY . /app

CMD ["python", "bot.py", "--voice"]
