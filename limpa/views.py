import logging

from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from limpa.models import Podcast
from limpa.services.feed import FeedError, fetch_and_validate_feed
from limpa.services.s3 import upload_feed_xml

logger = logging.getLogger(__name__)


def home(request):
    podcasts = Podcast.objects.all()
    return render(request, "limpa/home.html", {"podcasts": podcasts})


@require_POST
def add_podcast(request):
    url = request.POST.get("url", "").strip()

    if not url:
        return HttpResponse(
            '<div class="error">Please enter a podcast feed URL</div>', status=400
        )

    try:
        feed_data = fetch_and_validate_feed(url)
    except FeedError as e:
        logger.warning("Feed validation failed for %s: %s", url, e)
        return HttpResponse(f'<div class="error">{e}</div>', status=400)

    try:
        podcast = Podcast.objects.create(url=url, title=feed_data.title)
    except IntegrityError:
        return HttpResponse(
            '<div class="error">This podcast has already been added</div>', status=400
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

    return render(request, "limpa/_podcast_item.html", {"podcast": podcast})
