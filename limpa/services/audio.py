import logging
import subprocess
import tempfile
from pathlib import Path

from .types import AdvertisementData

logger = logging.getLogger(__name__)


def remove_ads_from_audio(input_path: Path, ads: AdvertisementData) -> Path:
    """Remove advertisement segments from audio using ffmpeg. Returns path to cleaned file."""
    if not ads.ads_list:
        logger.info("No ads to remove, returning original file")
        return input_path

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
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    total_duration = float(duration_result.stdout.strip())

    ad_segments = sorted(
        [(ad.start_timestamp_seconds, ad.end_timestamp_seconds) for ad in ads.ads_list],
        key=lambda x: x[0],
    )

    # Build list of segments to keep (inverse of ad segments)
    keep_segments: list[tuple[float, float]] = []
    current_pos = 0.0

    for ad_start, ad_end in ad_segments:
        if ad_start > current_pos:
            keep_segments.append((current_pos, ad_start))
        current_pos = max(current_pos, ad_end)

    if current_pos < total_duration:
        keep_segments.append((current_pos, total_duration))

    if not keep_segments:
        logger.warning("No content left after removing ads")
        return input_path

    # Build ffmpeg filter complex for concatenating kept segments
    filter_parts = []
    for i, (start, end) in enumerate(keep_segments):
        filter_parts.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];"
        )

    concat_inputs = "".join(f"[a{i}]" for i in range(len(keep_segments)))
    filter_parts.append(f"{concat_inputs}concat=n={len(keep_segments)}:v=0:a=1[outa]")
    filter_complex = "".join(filter_parts)

    _, output_file = tempfile.mkstemp(suffix=".mp3")
    output_path = Path(output_file)

    subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(input_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outa]",
            "-y",
            str(output_path),
        ],
        capture_output=True,
        check=True,
    )

    total_ad_time = sum(end - start for start, end in ad_segments)
    logger.info(
        f"Removed {len(ads.ads_list)} ads ({total_ad_time:.1f}s) from audio: {output_path}"
    )
    return output_path
