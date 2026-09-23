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

## AI provider configuration

AI commands use an OpenAI-compatible API. Set these keys in `config/config.json`
and restart the bot:

```json
{
  "ai_api_key": "YOUR_PROVIDER_KEY",
  "ai_base_url": "https://openrouter.ai/api/v1",
  "ai_model": "YOUR_OPENROUTER_MODEL_ID",
  "ai_search_model": "",
  "ai_web_search": "auto",
  "ai_structured_output": "json_schema",
  "ai_reasoning_effort": "",
  "ai_debug": false
}
```

Use an OpenRouter model ID including its provider prefix. For direct OpenAI,
change `ai_base_url` to `https://api.openai.com/v1`, use an OpenAI API key,
and set `ai_model` to an OpenAI model ID available to your account. Other
OpenAI-compatible base URLs also work for Chat Completions. Supply the base URL,
not the full `/chat/completions` path. Only configure endpoints you trust:
they receive the API key and message/image content.

Alternatively, leave `ai_api_key` blank and set the `AI_API_KEY` environment
variable. Old provider-specific keys are no longer used; replace them with
these settings. No new SDK dependency is needed: requests use the existing
asynchronous HTTP client.

Feature requirements:

* Image explanations and image-based Bajs reactions require a vision model.
  Animated images are sent as their first frame. This does not add video or
  audio understanding.
* Bajs React defaults to strict JSON schema output. Choose a model supporting
  structured outputs, or set `ai_structured_output` to `json_object` (JSON mode)
  or `prompt` (no API format constraint). These fallbacks are less reliable;
  malformed output can fail the command.
* xQc explanations and Brock game TTS request web search. `ai_web_search: "auto"`
  uses OpenRouter's web plugin or OpenAI's Responses API with the web search tool,
  based on the endpoint hostname. OpenAI needs a model supporting Responses and
  web search. `ai_search_model` optionally selects a separate model for these
  requests; blank reuses `ai_model`. For compatible proxy endpoints explicitly
  select `openrouter` or `openai`. Set `off` to knowingly use model knowledge
  without live research. Unknown endpoints otherwise return a search configuration
  error rather than silently omitting research.
* Reasoning is optional: leave `ai_reasoning_effort` blank for broad compatibility,
  or set a value supported by your model (such as `high`). The setting applies
  to both regular and search models; internal reasoning is not displayed.
* Provider moderation, model access, context limits, rate limits, and billing
  still apply. Search can incur additional charges. Refusals and unsupported
  feature errors are reported without retrying with reduced capabilities.
* Chatterbox Nano voice training and ordinary speech remain local and independent
  of the AI provider. Only the game-aware generated script uses this API.

`ai_debug` logs request metadata only, not private prompts, images, responses,
or API keys. The bot does not modify existing configuration or credentials.

See [OpenAI vision](https://developers.openai.com/api/docs/guides/images-vision),
[OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search),
and [OpenRouter web search](https://openrouter.ai/docs/guides/features/plugins/web-search)
for provider capability details.

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
