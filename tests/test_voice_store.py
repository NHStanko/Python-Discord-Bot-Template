from pathlib import Path
import sqlite3

import pytest

from helpers.voice_store import VoiceStore


def test_voice_lifecycle_erases_all_files(tmp_path: Path) -> None:
    store = VoiceStore(tmp_path)
    voice = store.create_voice("Nick Calm", created_by=123)
    first = store.add_sample(voice.slug, "first.wav", b"sample-one")
    second = store.add_sample(voice.slug, "second.mp3", b"sample-two")
    (store.voices_dir / voice.slug / "voice.safetensors").write_bytes(b"state")
    store.mark_trained(voice.slug)

    assert first.is_file() and second.is_file()
    assert store.get_voice("nick-calm").sample_count == 2
    assert store.get_voice("nick-calm").trained
    assert store.get_voice("nick-calm").volume == 2.0

    updated = store.set_volume("nick-calm", 1.4)
    assert updated.volume == 1.4
    assert store.get_voice("nick-calm").volume == 1.4

    deleted = store.delete_voice("nick-calm")

    assert deleted.slug == "nick-calm"
    assert not (store.voices_dir / "nick-calm").exists()
    assert store.list_voices() == []


def test_remove_one_sample_marks_voice_for_retrain(tmp_path: Path) -> None:
    store = VoiceStore(tmp_path)
    voice = store.create_voice("xqc", created_by=123)
    first = store.add_sample(voice.slug, "one.wav", b"one")
    store.add_sample(voice.slug, "two.wav", b"two")
    (store.voices_dir / voice.slug / "voice.safetensors").write_bytes(b"state")
    store.mark_trained(voice.slug)

    removed = store.remove_sample(voice.slug, store.list_samples(voice.slug)[0].id)

    assert removed.original_filename == "one.wav"
    assert not first.exists()
    assert store.get_voice(voice.slug).needs_retrain
    with pytest.raises(ValueError):
        store.remove_sample(voice.slug, store.list_samples(voice.slug)[0].id)


def test_duplicate_and_invalid_names_are_rejected(tmp_path: Path) -> None:
    store = VoiceStore(tmp_path)
    store.create_voice("valid", created_by=1)
    with pytest.raises(Exception):
        store.create_voice("valid", created_by=2)
    with pytest.raises(ValueError):
        store.create_voice("../escape", created_by=1)


def test_voice_volume_is_limited_to_safe_ffmpeg_values(tmp_path: Path) -> None:
    store = VoiceStore(tmp_path)
    store.create_voice("valid", created_by=1)

    with pytest.raises(ValueError):
        store.set_volume("valid", -0.1)
    assert store.set_volume("valid", 4.0).volume == 4.0
    with pytest.raises(ValueError):
        store.set_volume("valid", 4.1)


def test_existing_voice_database_gains_default_volume(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "voices.sqlite3") as database:
        database.execute(
            """CREATE TABLE voices (
                slug TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                state_filename TEXT,
                needs_retrain INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

    store = VoiceStore(tmp_path)
    profile = store.create_voice("legacy", created_by=1)

    assert profile.volume == 2.0
