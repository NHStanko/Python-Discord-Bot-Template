import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from helpers.voice_store import VoiceStore


def test_voice_lifecycle_erases_all_files(tmp_path: Path) -> None:
    store = VoiceStore(tmp_path)
    voice = store.create_voice("Nick Calm", created_by=123)
    first = store.add_sample(voice.slug, "first.wav", b"sample-one")
    second = store.add_sample(voice.slug, "second.mp3", b"sample-two")
    (store.voices_dir / voice.slug / "chatterbox-nano-v1.pt").write_bytes(b"state")
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


@pytest.fixture
def tracked_connections(monkeypatch):
    connections = []
    connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    return connections


def assert_connections_closed(connections):
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")


def test_store_closes_connection_after_successful_operation(
    tmp_path: Path, tracked_connections
) -> None:
    store = VoiceStore(tmp_path)
    store.create_voice("test", created_by=123)
    assert store.get_voice("test").created_by == 123
    assert_connections_closed(tracked_connections)


def test_remove_one_sample_marks_voice_for_retrain(tmp_path: Path) -> None:
    store = VoiceStore(tmp_path)
    voice = store.create_voice("xqc", created_by=123)
    first = store.add_sample(voice.slug, "one.wav", b"one")
    store.add_sample(voice.slug, "two.wav", b"two")
    (store.voices_dir / voice.slug / "chatterbox-nano-v1.pt").write_bytes(b"state")
    store.mark_trained(voice.slug)

    removed = store.remove_sample(voice.slug, store.list_samples(voice.slug)[0].id)

    assert removed.original_filename == "one.wav"
    assert not first.exists()
    assert store.get_voice(voice.slug).needs_retrain
    with pytest.raises(ValueError):
        store.remove_sample(voice.slug, store.list_samples(voice.slug)[0].id)


def test_concurrent_sample_removals_retain_one_sample(
    tmp_path: Path, monkeypatch
) -> None:
    store = VoiceStore(tmp_path)
    voice = store.create_voice("xqc", created_by=123)
    store.add_sample(voice.slug, "one.wav", b"one")
    store.add_sample(voice.slug, "two.wav", b"two")
    sample_ids = [sample.id for sample in store.list_samples(voice.slug)]

    both_read_initial_count = Barrier(2)
    get_voice = store.get_voice

    def synchronized_get_voice(name: str):
        profile = get_voice(name)
        both_read_initial_count.wait(timeout=5)
        return profile

    monkeypatch.setattr(store, "get_voice", synchronized_get_voice)

    def remove(sample_id: str):
        try:
            return store.remove_sample(voice.slug, sample_id)
        except ValueError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(remove, sample_ids))

    monkeypatch.setattr(store, "get_voice", get_voice)
    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert sum(not isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert store.get_voice(voice.slug).sample_count == 1
    assert len(store.sample_paths(voice.slug)) == 1
    assert store.sample_paths(voice.slug)[0].is_file()


def test_failed_sample_delete_restores_file(
    tmp_path: Path, tracked_connections
) -> None:
    store = VoiceStore(tmp_path)
    voice = store.create_voice("xqc", created_by=123)
    sample_path = store.add_sample(voice.slug, "one.wav", b"one")
    store.add_sample(voice.slug, "two.wav", b"two")
    sample_id = store.list_samples(voice.slug)[0].id

    with sqlite3.connect(store.database_path) as database:
        database.execute("""CREATE TRIGGER block_sample_delete BEFORE DELETE ON samples
               BEGIN SELECT RAISE(ABORT, 'sample delete blocked'); END""")

    tracked_connections.clear()

    with pytest.raises(sqlite3.IntegrityError, match="sample delete blocked"):
        store.remove_sample(voice.slug, sample_id)

    assert_connections_closed(tracked_connections)
    assert sample_path.is_file()
    assert sample_path.read_bytes() == b"one"
    assert len(store.list_samples(voice.slug)) == 2
    assert not list(sample_path.parent.glob(".*.deleting"))


def test_duplicate_and_invalid_names_are_rejected(tmp_path: Path) -> None:
    store = VoiceStore(tmp_path)
    store.create_voice("valid", created_by=1)
    with pytest.raises(FileExistsError):
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


@pytest.mark.parametrize("volume", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_volume_is_rejected_without_changing_profile(tmp_path, volume):
    store = VoiceStore(tmp_path)
    profile = store.create_voice("valid", created_by=1)

    with pytest.raises(ValueError, match="Voice volume"):
        store.set_volume("valid", volume)

    assert store.get_voice("valid") == profile


def test_existing_voice_database_gains_default_volume(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "voices.sqlite3") as database:
        database.execute("""CREATE TABLE voices (
                slug TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                state_filename TEXT,
                needs_retrain INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")

    store = VoiceStore(tmp_path)
    profile = store.create_voice("legacy", created_by=1)

    assert profile.volume == 2.0
