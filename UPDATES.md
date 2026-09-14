# Updates List

Here is the most recent update made on this template.

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

### Also included

* Changed the bot presence text to `gex update`
* Added a `gex` command with a button that returns 20 random facts about the Gex video game series
* Removed `etc` from the `isbabysleeping` reply pool
