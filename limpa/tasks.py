import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

from django.tasks import task  # type: ignore[import-not-found]
from django.utils import timezone

from limpa.services.audio import remove_ads_from_audio
from limpa.services.extract import extract_from_transcription
from limpa.services.feed import Episode, get_latest_episodes, regenerate_feed
from limpa.services.s3 import upload_episode_audio, upload_episode_transcript
from limpa.services.transcribe import transcribe_audio_batch
from limpa.services.types import TranscriptionResult

logger = logging.getLogger(__name__)


def _download_episode(episode: Episode) -> tuple[Path, bytes]:
    """Download episode audio and return (temp_path, audio_bytes)."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        temp_path = Path(f.name)
        with urlopen(episode.url, timeout=300) as response:  # noqa: S310
            while chunk := response.read(8192):
                f.write(chunk)
    audio_bytes = temp_path.read_bytes()
    return temp_path, audio_bytes


@task
def process_podcast(podcast_id: int) -> None:
    from limpa.models import Podcast

    podcast = Podcast.objects.get(id=podcast_id)
    logger.info(f"Processing podcast: {podcast.title} (id={podcast_id})")

    podcast.status = Podcast.Status.PROCESSING
    podcast.last_refreshed_at = timezone.now()
    podcast.save(update_fields=["status", "last_refreshed_at"])

    episodes = get_latest_episodes(url=podcast.url, count=2)
    processed_guids = set(podcast.processed_episodes.keys())

    new_episodes = [ep for ep in episodes if ep.guid not in processed_guids]
    if not new_episodes:
        logger.info("No new episodes to process")
        podcast.status = Podcast.Status.READY
        podcast.save(update_fields=["status"])
        return

    logger.info(f"Found {len(new_episodes)} new episodes to process")

    temp_files: list[Path] = []
    try:
        downloaded = []
        for episode in new_episodes:
            temp_path, audio_bytes = _download_episode(episode)
            temp_files.append(temp_path)
            downloaded.append((episode, temp_path, audio_bytes))
            logger.info(f"Downloaded episode {episode.guid}")

        audio_items = [
            (f"{ep.guid}.mp3", audio_bytes) for ep, _, audio_bytes in downloaded
        ]
        transcriptions = transcribe_audio_batch(audio_items=audio_items)
        logger.info(f"Transcribed {len(transcriptions)} episodes in parallel")

        def _upload_transcript(
            episode: Episode, transcription: TranscriptionResult
        ) -> str:
            url = upload_episode_transcript(
                url_hash=podcast.url_hash,
                episode_guid=episode.guid,
                transcript_json=transcription.model_dump_json(),
            )
            logger.info(f"Uploaded transcript for {episode.guid}")
            return url

        with ThreadPoolExecutor() as executor:
            transcript_futures = [
                executor.submit(_upload_transcript, ep, tr)
                for (ep, _, _), tr in zip(downloaded, transcriptions)
            ]
            ad_futures = [
                executor.submit(extract_from_transcription, transcription=tr)
                for tr in transcriptions
            ]
            transcript_urls = [f.result() for f in transcript_futures]
            ads_list = [f.result() for f in ad_futures]

        for i, ((episode, temp_path, _), transcription) in enumerate(
            zip(downloaded, transcriptions)
        ):  # noqa: E501
            ads = ads_list[i]
            transcript_url = transcript_urls[i]
            logger.info(f"Extracted {len(ads.ads_list)} ads from {episode.guid}")

            temp_output = remove_ads_from_audio(input_path=temp_path, ads=ads)
            temp_files.append(temp_output)

            s3_url = upload_episode_audio(
                url_hash=podcast.url_hash,
                episode_guid=episode.guid,
                audio_path=temp_output,
            )
            logger.info(f"Uploaded processed audio for {episode.guid}")

            podcast.processed_episodes[episode.guid] = {
                "original_url": episode.url,
                "s3_url": s3_url,
                "transcript_url": transcript_url,
                "ads": ads.model_dump(),
            }

        # Add [No ads] to podcast title if not already present
        if not podcast.title.startswith("[No ads]"):
            podcast.title = f"[No ads] {podcast.title}"

        podcast.status = Podcast.Status.READY
        podcast.last_refreshed_at = timezone.now()
        podcast.save()
        logger.info(f"Processed {len(new_episodes)} episodes for {podcast.title}")

        regenerate_feed(
            url=podcast.url,
            url_hash=podcast.url_hash,
            processed_episodes=podcast.processed_episodes,
        )

    except Exception as e:
        logger.error(f"Failed to process podcast {podcast.title}: {e}")
        podcast.status = Podcast.Status.FAILED
        podcast.save(update_fields=["status"])
        raise

    finally:
        for temp_file in temp_files:
            if temp_file.exists():
                os.unlink(temp_file)
