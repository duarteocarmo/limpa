import logging

from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from limpa.models import Podcast
from limpa.services.feed import FeedError, fetch_and_validate_feed
from limpa.services.s3 import get_feed_xml, upload_feed_xml
from limpa.tasks import process_podcast

logger = logging.getLogger(__name__)


def _error_response(request, message: str):
    return render(
        request, "limpa/home.html#error_message", {"message": message}, status=400
    )


def home(request):
    podcasts = Podcast.objects.all()
    return render(request, "limpa/home.html", {"podcasts": podcasts})


@require_POST  # ty: ignore[invalid-argument-type]
def add_podcast(request):
    url = request.POST.get("url", "").strip()

    if not url:
        return _error_response(request, "Please enter a podcast feed URL")

    try:
        feed_data = fetch_and_validate_feed(url)
    except FeedError as e:
        logger.warning("Feed validation failed for %s: %s", url, e)
        return _error_response(request, str(e))

    try:
        podcast = Podcast.objects.create(
            url=url, title=feed_data.title, episode_count=feed_data.episode_count
        )
    except IntegrityError:
        return _error_response(request, "This podcast has already been added")

    try:
        upload_feed_xml(url_hash=podcast.url_hash, xml_content=feed_data.raw_xml)
        podcast.status = Podcast.Status.UPLOADED
        podcast.save()
        logger.info("Uploaded feed for podcast %s", podcast.title)
    except Exception as e:
        podcast.status = Podcast.Status.FAILED
        podcast.save()
        logger.error("S3 upload failed for podcast %s: %s", podcast.title, e)

    process_podcast.enqueue(podcast_id=podcast.id)

    return render(request, "limpa/home.html#podcast_item", {"podcast": podcast})


@require_http_methods(["DELETE"])
def delete_podcast(request, podcast_id: int):
    podcast = get_object_or_404(Podcast, id=podcast_id)
    podcast.delete()
    logger.info("Deleted podcast %s", podcast.title)
    return HttpResponse("")


@require_GET  # ty: ignore[invalid-argument-type]
def serve_feed(request, url_hash: str):
    podcast = get_object_or_404(Podcast, url_hash=url_hash)
    feed_xml = get_feed_xml(url_hash=podcast.url_hash)
    if feed_xml is None:
        return HttpResponse(status=404)
    return HttpResponse(feed_xml, content_type="application/xml")


@require_GET  # ty: ignore[invalid-argument-type]
def podcast_stats(request, podcast_id: int):
    podcast = get_object_or_404(Podcast, id=podcast_id)
    return render(request, "limpa/home.html#podcast_stats", {"podcast": podcast})
