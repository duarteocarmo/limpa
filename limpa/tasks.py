import logging
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen

from django.tasks import task  # type: ignore[import-not-found]
from django.utils import timezone

from limpa.services.audio import trim_audio_end
from limpa.services.feed import get_latest_episodes, regenerate_feed
from limpa.services.s3 import upload_episode_audio

logger = logging.getLogger(__name__)


@task
def process_podcast(podcast_id: int) -> None:
    from limpa.models import Podcast

    podcast = Podcast.objects.get(id=podcast_id)
    logger.info(f"Processing podcast: {podcast.title} (id={podcast_id})")

    podcast.last_refreshed_at = timezone.now()
    podcast.save(update_fields=["last_refreshed_at"])

    episodes = get_latest_episodes(url=podcast.url, count=5)
    processed_guids = set(podcast.processed_episodes.keys())

    for episode in episodes:
        if episode.guid in processed_guids:
            logger.info(f"Skipping already processed episode: {episode.guid}")
            continue

        process_episode.enqueue(
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

        temp_output = trim_audio_end(input_path=temp_input, seconds_to_keep=10)

        s3_url = upload_episode_audio(
            url_hash=podcast.url_hash, episode_guid=episode_guid, audio_path=temp_output
        )
        logger.info(f"Uploaded processed episode to {s3_url}")

        podcast.processed_episodes[episode_guid] = {
            "original_url": episode_url,
            "s3_url": s3_url,
        }
        podcast.last_refreshed_at = timezone.now()
        podcast.save()

        regenerate_feed(
            url=podcast.url,
            url_hash=podcast.url_hash,
            processed_episodes=podcast.processed_episodes,
        )

    finally:
        if temp_input and temp_input.exists():
            os.unlink(temp_input)
        if temp_output and temp_output.exists():
            os.unlink(temp_output)
