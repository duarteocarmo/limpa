import logging
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen

from django.tasks import task  # type: ignore[import-not-found]
from django.utils import timezone

from limpa.services.audio import remove_ads_from_audio
from limpa.services.extract import extract_from_transcription
from limpa.services.feed import get_latest_episodes, regenerate_feed
from limpa.services.s3 import upload_episode_audio, upload_episode_transcript
from limpa.services.transcribe import transcribe_audio

logger = logging.getLogger(__name__)


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

    for episode in episodes:
        if episode.guid in processed_guids:
            logger.info(f"Skipping already processed episode: {episode.guid}")
            continue

        process_episode.enqueue(  # type: ignore[attr-defined]
            podcast_id=podcast_id, episode_guid=episode.guid, episode_url=episode.url
        )


@task
def process_episode(podcast_id: int, episode_guid: str, episode_url: str) -> None:
    from limpa.models import Podcast

    podcast = Podcast.objects.get(id=podcast_id)
    logger.info(f"Processing episode {episode_guid} for podcast {podcast.title}")

    temp_input = None
    temp_output = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_input = Path(f.name)
            with urlopen(episode_url, timeout=300) as response:  # noqa: S310
                while chunk := response.read(8192):
                    f.write(chunk)

        logger.info(f"Downloaded episode to {temp_input}")

        transcription = transcribe_audio(audio_path=temp_input)
        logger.info(f"Transcribed episode: {len(transcription.segments)} segments")

        transcript_url = upload_episode_transcript(
            url_hash=podcast.url_hash,
            episode_guid=episode_guid,
            transcript_json=transcription.model_dump_json(),
        )
        logger.info(f"Uploaded transcript to {transcript_url}")

        ads = extract_from_transcription(transcription=transcription)
        logger.info(f"Extracted {len(ads.ads_list)} ads from transcription")

        temp_output = remove_ads_from_audio(input_path=temp_input, ads=ads)

        s3_url = upload_episode_audio(
            url_hash=podcast.url_hash, episode_guid=episode_guid, audio_path=temp_output
        )
        logger.info(f"Uploaded processed episode to {s3_url}")

        podcast.processed_episodes[episode_guid] = {
            "original_url": episode_url,
            "s3_url": s3_url,
            "transcript_url": transcript_url,
            "ads": ads.model_dump(),
        }
        podcast.status = Podcast.Status.READY
        podcast.last_refreshed_at = timezone.now()
        podcast.save()

        regenerate_feed(
            url=podcast.url,
            url_hash=podcast.url_hash,
            processed_episodes=podcast.processed_episodes,
        )

    except Exception as e:
        logger.error(f"Failed to process episode {episode_guid}: {e}")
        podcast.status = Podcast.Status.FAILED
        podcast.save(update_fields=["status"])
        raise

    finally:
        if temp_input and temp_input.exists():
            os.unlink(temp_input)
        if temp_output and temp_output.exists():
            os.unlink(temp_output)
