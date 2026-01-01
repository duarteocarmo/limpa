import logging

from django.tasks import task  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


@task
def process_podcast(podcast_id: int) -> None:
    from limpa.models import Podcast

    podcast = Podcast.objects.get(id=podcast_id)
    logger.info(f"Processing podcast: {podcast.title} (id={podcast_id})")
