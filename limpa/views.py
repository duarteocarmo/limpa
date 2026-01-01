import logging

from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from limpa.models import Podcast
from limpa.services.feed import FeedError, fetch_and_validate_feed
from limpa.services.s3 import upload_feed_xml

logger = logging.getLogger(__name__)


def home(request):
    podcasts = Podcast.objects.all()
    return render(request, "limpa/home.html", {"podcasts": podcasts})


@require_POST  # ty: ignore[invalid-argument-type]
def add_podcast(request):
    url = request.POST.get("url", "").strip()

    if not url:
        return render(
            request,
            "limpa/home.html#error_message",
            {"message": "Please enter a podcast feed URL"},
            status=400,
        )

    try:
        feed_data = fetch_and_validate_feed(url)
    except FeedError as e:
        logger.warning("Feed validation failed for %s: %s", url, e)
        return render(
            request,
            "limpa/home.html#error_message",
            {"message": str(e)},
            status=400,
        )

    try:
        podcast = Podcast.objects.create(
            url=url, title=feed_data.title, episode_count=feed_data.episode_count
        )
    except IntegrityError:
        return render(
            request,
            "limpa/home.html#error_message",
            {"message": "This podcast has already been added"},
            status=400,
        )

    try:
        upload_feed_xml(url_hash=podcast.url_hash, xml_content=feed_data.raw_xml)
        podcast.status = Podcast.Status.UPLOADED
        podcast.save()
        logger.info("Uploaded feed for podcast %s", podcast.title)
    except Exception as e:
        podcast.status = Podcast.Status.FAILED
        podcast.save()
        logger.error("S3 upload failed for podcast %s: %s", podcast.title, e)

    return render(request, "limpa/home.html#podcast_item", {"podcast": podcast})


@require_http_methods(["DELETE"])
def delete_podcast(request, podcast_id: int):
    podcast = get_object_or_404(Podcast, id=podcast_id)
    podcast.delete()
    logger.info("Deleted podcast %s", podcast.title)
    return HttpResponse("")
