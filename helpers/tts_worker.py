"""Persistent CPU model worker. Stdout is reserved for JSON job responses."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

from helpers.tts_service import ChatterboxTTSService
from helpers.voice_store import VoiceStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--cpu-threads", type=int, default=8)
    options = parser.parse_args()
    # The parent already performed startup cleanup. Its generated files may be
    # queued or playing, so worker startup/restart must never erase them.
    store = VoiceStore(options.data_dir, cleanup=False)
    service = ChatterboxTTSService(store, options.cpu_threads)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            args = request["args"]
            with redirect_stdout(sys.stderr):
                match request["operation"]:
                    case "train":
                        service._train_sync(*args)
                    case "synthesize":
                        slug, text, output = args
                        service._synthesize_sync(slug, text, Path(output))
                    case "delete":
                        service._delete_sync(*args)
                    case _:
                        raise ValueError("Unknown TTS job")
            response = {"ok": True}
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            response = {"error": str(exc)}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
