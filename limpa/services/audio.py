import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def trim_audio_end(input_path: Path, seconds_to_trim: int = 30) -> Path:
    """Trims the last N seconds from an audio file using ffmpeg. Returns path to trimmed file."""
    _, output_file = tempfile.mkstemp(suffix=".mp3")
    output_path = Path(output_file)

    duration_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],  # noqa: E501
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(duration_result.stdout.strip())
    new_duration = max(0, duration - seconds_to_trim)

    subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(input_path),
            "-t",
            str(new_duration),
            "-c",
            "copy",
            "-y",
            str(output_path),
        ],
        capture_output=True,
        check=True,
    )

    logger.info(
        f"Trimmed audio from {duration:.1f}s to {new_duration:.1f}s: {output_path}"
    )
    return output_path
