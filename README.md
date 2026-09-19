# Python Discord Bot

This project is based off of the [kkrypt0nn/Python-Discord-Bot-Template](https://github.com/kkrypt0nn/Python-Discord-Bot-Template).

It has additional commands being added to it, notably voice functionality.

## How to download it

This repository is now a template, on the top left you can simply click on "**Use this template**" to create a GitHub
repository based on this template.

Alternatively you can do the following:

* Clone/Download the repository
    * To clone it and get the updates you can definitely use the command
      `git clone`
* Create a discord bot [here](https://discord.com/developers/applications)
* Get your bot token
* Invite your bot on servers using the following invite:
  https://discord.com/oauth2/authorize?&client_id=YOUR_APPLICATION_ID_HERE&scope=bot+applications.commands&permissions=PERMISSIONS (
  Replace `YOUR_APPLICATION_ID_HERE` with the application ID and replace `PERMISSIONS` with the required permissions
  your bot needs that it can be get at the bottom of a this
  page https://discord.com/developers/applications/YOUR_APPLICATION_ID_HERE/bot)

## How to set up

Copy the example configuration, then edit the new file with your bot settings:

```sh
mkdir -p config
cp config.json.default config/config.json
```

Here is an explanation of what everything is:

| Setting            | What it is                                                   |
| ------------------ | ------------------------------------------------------------ |
| `prefix`           | The prefix for normal commands                               |
| `token`            | The bot token                                                 |
| `permissions`      | The permissions integer used when inviting the bot           |
| `application_id`   | The bot application's ID                                      |
| `owners`           | Discord user IDs allowed to use owner-only commands          |


## How to start

To start the bot you simply need to launch, either your terminal (Linux, Mac & Windows), or your Command Prompt (
Windows)
.

Before running the bot you will need to install all the requirements with this command:

```
python -m pip install -r requirements.txt
```

After that you can start it with

```
python bot.py --voice
```

> **Note** You may need to replace `python` with `py`, `python3`, `python3.11`, etc. depending on what Python versions you have installed on the machine.

For development, install the development requirements, then run the quality checks:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
```

For a foreground deployment, use the bundled runner:

```sh
./runner.sh
```

The runner uses `exec` so Docker, systemd, or another supervisor receives the
bot process directly and can restart it when needed. It no longer performs a
scheduled daily restart; configure restart policy and log rotation in the
supervisor instead.

## Prompt resources

Long AI behavior prompts live in `prompts/` rather than in the Python command
handlers. `helpers/prompts.py` loads and renders those version-controlled files
independently of the process working directory. Rebuild the Docker image after
changing a prompt so the updated resource is copied into the container.

Discord messages, activity names, and other runtime values are passed separately
as untrusted data. Keep response schemas, authorization, and runtime control flow
in Python rather than adding them to prompt templates.

## Voice cloning (Pocket TTS)

The bot includes global reusable voice profiles powered by Pocket TTS. The
runtime uses one CPU model and serializes inference because the model state is
not thread-safe.

The Brock game-aware TTS event requires the privileged **Presence Intent** to
be enabled for the bot in the Discord Developer Portal. It uses the configured
Gemini model with Google Search grounding and a trained `northernlion` voice.

Available slash commands:

* `/tts speak voice text` speaks in the caller's voice channel.
* `/tts sequence` lines up multiple voices and timed pauses in one message. For
  example: `(forsen) hey (pause) 2 (xqc) hello`. Use `(random) text` to choose
  any trained voice for a line. The older `(silence)` tag remains an alias for
  `(pause)`.
* `/tts list` lists trained voices.
* `/tts volume` opens an owner-only button panel for adjusting a voice from
  0% to 400%. Voices default to 200%, and the saved level applies to future
  playback.
* `/tts train`, `/tts retrain`, and `/tts delete` manage profiles. Training can
  use either an audio attachment or a YouTube URL with a start time and duration.
* `/tts samples add`, `/tts samples list`, and `/tts samples remove` manage
  retained recordings. Additional samples can also come from a timed YouTube
  clip. Management commands are restricted to IDs in the `owners` config setting.

Reference recordings are retained under `tts.data_dir` and should be treated as
sensitive biometric-like data. The directory is ignored by Git; mount `/data`
as a persistent volume when using Docker.

Pocket TTS requires Python 3.10-3.14, FFmpeg, and access to its gated model
weights. Accept the model terms on Hugging Face, then authenticate with
`hf auth login` or provide `HF_TOKEN`. Attachment-size and sample-count limits
can be set in `config.json` or overridden with `MAX_VOICE_ATTACHMENT_BYTES`
and `MAX_SAMPLES_PER_VOICE`.


## Built With

* [Python 3.12](https://www.python.org/)

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE.md](LICENSE.md) file for details

## Attribution

The original template was created by [kkrypt0nn](https://github.com/kkrypt0nn) and is available at [kkrypt0nn/Python-Discord-Bot-Template](https://github.com/kkrypt0nn/Python-Discord-Bot-Template).
