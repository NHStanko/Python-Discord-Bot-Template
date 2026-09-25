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

## Gemini AI configuration

AI commands use the Gemini API. Set these keys in `config/config.json` and
restart the bot:

```json
{
  "gemini_api_key": "YOUR_GOOGLE_AI_STUDIO_API_KEY",
  "gemini_model": "gemini-2.5-pro",
  "gemini_debug": false
}
```

Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
The same model handles image input, structured Bajs replies, and Google Search
grounding for xQc explanations and Brock game TTS. Use a model available to your
Google AI Studio project that supports those features. The bot's old default is
`gemini-1.5-flash-002` when `gemini_model` is empty, so specify a current model.
Remove the old `ai_api_key`, `ai_base_url`, `ai_model`, `ai_search_model`,
`ai_web_search`, `ai_structured_output`, `ai_reasoning_effort`, `ai_debug`,
`ai_provider`, and `ai_provider_fallbacks` entries; Gemini ignores them.

`gemini_debug: true` saves request details and copies input images into `debug/`.
Keep it off unless you need those files for troubleshooting.

## Prompt resources

Long AI behavior prompts live in `prompts/` rather than in the Python command
handlers. `helpers/prompts.py` loads and renders those version-controlled files
independently of the process working directory. Rebuild the Docker image after
changing a prompt so the updated resource is copied into the container.

Discord messages, activity names, and other runtime values are passed separately
as untrusted data. Keep response schemas, authorization, and runtime control flow
in Python rather than adding them to prompt templates.

## Voice cloning (Chatterbox Nano)

The bot includes global reusable voice profiles powered by Chatterbox Nano. The
runtime keeps one CPU model in a separate worker process and serializes inference
because the model state is not thread-safe. Downloads and model initialization
run in that worker too, so they do not share Discord's Python interpreter.

The Brock game-aware TTS event requires the privileged **Presence Intent** to
be enabled for the bot in the Discord Developer Portal. It uses the configured
AI model with web search configured above and a trained `northernlion` voice.

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

Chatterbox Nano runs entirely on CPU and generates English speech. Use Python
3.12, FFmpeg, and the pinned dependencies in `requirements.txt`. Docker installs
matching CPU-only PyTorch and torchaudio builds. The first training or synthesis
request downloads the model weights; retain `/data/huggingface` between restarts.
If Hugging Face requests authentication, provide `HF_TOKEN` with model access.
The old `tts.language` / `POCKET_TTS_LANGUAGE` setting no longer applies.
CPU inference uses eight threads by default; adjust `tts.cpu_threads` or
`TTS_CPU_THREADS` to suit the hosting machine.
Commands report when TTS is busy instead of silently queueing behind an existing
job. Voice-name autocomplete remains available while the model is loading. A
first download can take several minutes; keep the Hugging Face cache mounted
and wait for the current job to finish before submitting another.

Training prepares and saves a reusable voice profile; it does not fine-tune the
model. Use clean speech from one speaker, preferably a continuous 6-15 second
recording without music. Combined references must exceed 5 seconds after leading
silence removal. Multiple samples share a 15-second reference budget. Natural
pauses are preserved, and output volume is peak-limited to prevent clipping.

Existing Pocket profiles automatically rebuild from retained recordings on their
first use. Names, samples, and volume settings remain intact; the original Pocket
state is retained. That first request takes longer. If the reference is too short,
add a longer recording with `/tts samples add` and run `/tts retrain`. You can also
run `/tts retrain` ahead of time to migrate a voice explicitly.

Attachment-size and sample-count limits can be set in `config.json` or overridden
with `MAX_VOICE_ATTACHMENT_BYTES` and `MAX_SAMPLES_PER_VOICE`.


## Built With

* [Python 3.12](https://www.python.org/)

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE.md](LICENSE.md) file for details

## Attribution

The original template was created by [kkrypt0nn](https://github.com/kkrypt0nn) and is available at [kkrypt0nn/Python-Discord-Bot-Template](https://github.com/kkrypt0nn/Python-Discord-Bot-Template).
