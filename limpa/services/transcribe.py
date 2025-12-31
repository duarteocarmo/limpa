"""
Transcription service for audio files.
"""

from dataclasses import dataclass
from pathlib import Path

import modal

from .modal_transcription import Transcriber, app


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]


def transcribe_audio(audio_path: str | Path) -> TranscriptionResult:
    """Transcribe an audio file (mp3/wav/flac) and return the transcript with segments."""
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if audio_path.suffix.lower() not in (".wav", ".mp3", ".flac"):
        raise ValueError("Only .wav, .mp3, and .flac files are supported")

    audio_bytes = audio_path.read_bytes()

    with modal.enable_output():
        with app.run():
            transcriber = Transcriber()
            result = transcriber.transcribe.remote(audio_bytes, audio_path.name)  # type: ignore[attr-defined]

    segments = [
        Segment(start=seg["start"], end=seg["end"], text=seg["segment"])
        for seg in result["segments"]
    ]

    return TranscriptionResult(text=result["text"], segments=segments)


if __name__ == "__main__":
    transcribe_audio("./scripts/episode.mp3")
