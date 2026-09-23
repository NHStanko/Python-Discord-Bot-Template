# Updates List

Here is the most recent update made on this template.

### TTS responsiveness (22 September 2026)

* Isolated model downloads, loading, and inference in a persistent CPU worker.
* Added busy responses and first-use progress messages for TTS commands.
* Moved autocomplete database reads off the event loop and bounded their wait.
* Added worker cancellation and shutdown cleanup without removing playing audio.

### Chatterbox Nano TTS (22 September 2026)

* Replaced Pocket TTS with CPU-only Chatterbox Nano and saved voice profiles.
* Existing voices rebuild automatically from retained samples on first use.
* Preserved reference pauses, validated reference length, and reduced speech splits.
* Added peak limiting to voice playback and multi-voice sequences.

### Configurable AI API (22 September 2026)

* Replaced the Google AI SDK with asynchronous OpenAI-compatible API requests.
* Added configurable API keys, endpoints, models, structured output, and reasoning.
* Preserved image input and added OpenRouter/OpenAI web search routing with an
  optional separate search model.
* Documented model requirements, configuration migration, and provider limitations.

### Pocket TTS Update (13 September 2026)

* Added reusable global voice profiles powered by Pocket TTS
* Added `/tts speak` for generated speech and `/tts list` for voice discovery
* Added owner-only commands to train, retrain, inspect, and delete voice profiles
* Added voice and sample autocomplete
* Added configurable attachment, sample-count, and generated-text limits
* Added persistent profile storage and CPU-only Docker support
* Added timed YouTube clips as a source for training and additional samples
* Added live progress updates while `/tts train` processes and builds a voice
* Reduced container size with CPU-only PyTorch, a multi-stage build, and a smaller build context
* Added a persistent button-based volume panel for trained voices
* Set the default and reset TTS voice volume to 200%, adjustable up to 400%
* Added multi-voice TTS sequences with timed `(pause)` segments and random voices
* Added a 1-in-100 researched Northernlion-style TTS monologue when Brock starts
  a game in voice chat or joins voice while already playing
* Made all ephemeral TTS command responses disappear after five seconds

### Also included

* Changed the bot presence text to `gex update`
* Added a `gex` command with a button that returns 20 random facts about the Gex video game series
* Removed `etc` from the `isbabysleeping` reply pool
