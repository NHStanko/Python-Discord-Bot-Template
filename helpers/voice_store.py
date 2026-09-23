from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VOICE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
VOICE_STATE_FILENAME = "chatterbox-nano-v1.pt"


@dataclass(frozen=True)
class VoiceProfile:
    slug: str
    display_name: str
    created_by: int
    sample_count: int
    trained: bool
    needs_retrain: bool
    volume: float
    updated_at: str


@dataclass(frozen=True)
class VoiceSample:
    id: str
    voice_slug: str
    original_filename: str
    created_at: str


class VoiceStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.voices_dir = self.data_dir / "voices"
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        for interrupted_delete in self.voices_dir.glob(".*.deleting"):
            shutil.rmtree(interrupted_delete, ignore_errors=True)
        for interrupted_sample_delete in self.voices_dir.glob("*/samples/.*.deleting"):
            interrupted_sample_delete.unlink(missing_ok=True)

        self.generated_dir = self.data_dir / "generated"
        self.generated_dir.mkdir(exist_ok=True)
        for stale_output in self.generated_dir.glob("*.wav"):
            stale_output.unlink(missing_ok=True)

        self.database_path = self.data_dir / "voices.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS voices (
                    slug TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    state_filename TEXT,
                    needs_retrain INTEGER NOT NULL DEFAULT 0,
                    volume REAL NOT NULL DEFAULT 2.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS samples (
                    id TEXT PRIMARY KEY,
                    voice_slug TEXT NOT NULL REFERENCES voices(slug) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row[1] for row in db.execute("PRAGMA table_info(voices)").fetchall()
            }
            if "volume" not in columns:
                db.execute(
                    "ALTER TABLE voices ADD COLUMN volume REAL NOT NULL DEFAULT 2.0"
                )

    @staticmethod
    def normalize_name(name: str) -> str:
        slug = name.strip().lower().replace(" ", "-")
        if not VOICE_NAME.fullmatch(slug):
            raise ValueError(
                "Voice names must be 2-32 letters, numbers, hyphens, or underscores"
            )
        return slug

    @staticmethod
    def _profile(row: sqlite3.Row) -> VoiceProfile:
        return VoiceProfile(
            slug=row["slug"],
            display_name=row["display_name"],
            created_by=row["created_by"],
            sample_count=row["sample_count"],
            trained=bool(row["state_filename"]),
            needs_retrain=bool(row["needs_retrain"]),
            volume=float(row["volume"]),
            updated_at=row["updated_at"],
        )

    def create_voice(self, name: str, created_by: int) -> VoiceProfile:
        slug = self.normalize_name(name)
        now = datetime.now(timezone.utc).isoformat()
        voice_dir = self.voices_dir / slug
        (voice_dir / "samples").mkdir(parents=True, exist_ok=False)
        try:
            with self._connect() as db:
                db.execute(
                    """INSERT INTO voices
                       (slug, display_name, created_by, state_filename,
                        needs_retrain, created_at, updated_at)
                       VALUES (?, ?, ?, NULL, 0, ?, ?)""",
                    (slug, name.strip(), created_by, now, now),
                )
        except Exception:
            shutil.rmtree(voice_dir, ignore_errors=True)
            raise
        return self.get_voice(slug)

    def get_voice(self, name: str) -> VoiceProfile:
        slug = self.normalize_name(name)
        with self._connect() as db:
            row = db.execute(
                """SELECT v.*, COUNT(s.id) AS sample_count
                   FROM voices v LEFT JOIN samples s ON s.voice_slug = v.slug
                   WHERE v.slug = ? GROUP BY v.slug""",
                (slug,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown voice: {slug}")
        return self._profile(row)

    def list_voices(self) -> list[VoiceProfile]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT v.*, COUNT(s.id) AS sample_count
                   FROM voices v LEFT JOIN samples s ON s.voice_slug = v.slug
                   GROUP BY v.slug ORDER BY v.slug"""
            ).fetchall()
        return [self._profile(row) for row in rows]

    def add_sample(self, name: str, original_filename: str, content: bytes) -> Path:
        voice = self.get_voice(name)
        suffix = Path(original_filename).suffix.lower() or ".audio"
        sample_id = uuid.uuid4().hex
        relative = Path("samples") / f"{sample_id}{suffix}"
        destination = self.voices_dir / voice.slug / relative
        destination.write_bytes(content)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        sample_id,
                        voice.slug,
                        str(relative),
                        Path(original_filename).name,
                        hashlib.sha256(content).hexdigest(),
                        now,
                    ),
                )
                db.execute(
                    """UPDATE voices SET updated_at = ?,
                       needs_retrain = CASE WHEN state_filename IS NULL THEN 0 ELSE 1 END
                       WHERE slug = ?""",
                    (now, voice.slug),
                )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return destination

    def list_samples(self, name: str) -> list[VoiceSample]:
        voice = self.get_voice(name)
        with self._connect() as db:
            rows = db.execute(
                """SELECT id, voice_slug, original_filename, created_at
                   FROM samples WHERE voice_slug = ? ORDER BY created_at, id""",
                (voice.slug,),
            ).fetchall()
        return [VoiceSample(**dict(row)) for row in rows]

    def remove_sample(self, name: str, sample_id: str) -> VoiceSample:
        voice = self.get_voice(name)
        with self._connect() as db:
            row = db.execute(
                """SELECT id, voice_slug, filename, original_filename, created_at
                   FROM samples WHERE voice_slug = ? AND id = ?""",
                (voice.slug, sample_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown sample for {voice.slug}: {sample_id}")
        if voice.sample_count <= 1:
            raise ValueError("A voice must retain at least one sample; delete the voice instead")

        path = self.voices_dir / voice.slug / row["filename"]
        tombstone = path.with_name(f".{path.name}.deleting")
        path.rename(tombstone)
        try:
            with self._connect() as db:
                db.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
                db.execute(
                    "UPDATE voices SET needs_retrain = 1, updated_at = ? WHERE slug = ?",
                    (datetime.now(timezone.utc).isoformat(), voice.slug),
                )
        except Exception:
            tombstone.rename(path)
            raise
        tombstone.unlink()
        return VoiceSample(
            row["id"], row["voice_slug"], row["original_filename"], row["created_at"]
        )

    def sample_paths(self, name: str) -> list[Path]:
        voice = self.get_voice(name)
        with self._connect() as db:
            rows = db.execute(
                "SELECT filename FROM samples WHERE voice_slug = ? ORDER BY created_at, id",
                (voice.slug,),
            ).fetchall()
        return [self.voices_dir / voice.slug / row["filename"] for row in rows]

    def state_path(self, name: str) -> Path:
        voice = self.get_voice(name)
        with self._connect() as db:
            row = db.execute(
                "SELECT state_filename FROM voices WHERE slug = ?", (voice.slug,)
            ).fetchone()
        filename = row["state_filename"]
        if filename not in {VOICE_STATE_FILENAME, "voice.safetensors"}:
            raise FileNotFoundError(f"Voice {voice.slug} has not been trained yet")
        path = self.voices_dir / voice.slug / filename
        if not path.is_file():
            raise FileNotFoundError(f"Voice {voice.slug} has not been trained yet")
        return path

    def mark_trained(self, name: str) -> None:
        voice = self.get_voice(name)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """UPDATE voices SET state_filename = ?, needs_retrain = 0,
                   updated_at = ? WHERE slug = ?""",
                (VOICE_STATE_FILENAME, now, voice.slug),
            )

    def set_volume(self, name: str, volume: float) -> VoiceProfile:
        voice = self.get_voice(name)
        if volume < 0 or volume > 4:
            raise ValueError("Voice volume must be between 0% and 400%")
        with self._connect() as db:
            db.execute(
                "UPDATE voices SET volume = ?, updated_at = ? WHERE slug = ?",
                (round(volume, 2), datetime.now(timezone.utc).isoformat(), voice.slug),
            )
        return self.get_voice(voice.slug)

    def delete_voice(self, name: str) -> VoiceProfile:
        voice = self.get_voice(name)
        voice_dir = self.voices_dir / voice.slug
        tombstone = self.voices_dir / f".{voice.slug}.{uuid.uuid4().hex}.deleting"
        voice_dir.rename(tombstone)
        try:
            with self._connect() as db:
                db.execute("DELETE FROM voices WHERE slug = ?", (voice.slug,))
        except Exception:
            tombstone.rename(voice_dir)
            raise
        shutil.rmtree(tombstone)
        return voice
