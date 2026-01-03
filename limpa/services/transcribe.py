import modal

from .modal_transcription import Transcriber, app
from .types import Segment, TranscriptionResult


def transcribe_audio_batch(
    audio_items: list[tuple[str, bytes]],
) -> list[TranscriptionResult]:
    if not audio_items:
        return []

    with modal.enable_output(), app.run():
        transcriber = Transcriber()
        results = list(
            transcriber.transcribe.map(
                [audio_bytes for _, audio_bytes in audio_items],
                [filename for filename, _ in audio_items],
            )
        )

    return [
        TranscriptionResult(
            text=result["text"],
            segments=[
                Segment(start=seg["start"], end=seg["end"], text=seg["segment"])
                for seg in result["segments"]
            ],
        )
        for result in results
    ]
