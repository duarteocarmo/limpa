import logging
import re
from dataclasses import dataclass
from urllib.request import urlopen

import feedparser

from limpa.services.s3 import upload_feed_xml

logger = logging.getLogger(__name__)


class FeedError(Exception):
    pass


@dataclass
class FeedData:
    title: str
    raw_xml: bytes
    episode_count: int


@dataclass
class Episode:
    guid: str
    url: str


def fetch_and_validate_feed(url: str) -> FeedData:
    try:
        with urlopen(url, timeout=30) as response:  # noqa: S310
            raw_xml = response.read()
    except Exception as e:
        raise FeedError(f"Failed to fetch feed: {e}") from e

    parsed = feedparser.parse(raw_xml)

    if parsed.bozo and not parsed.entries:
        raise FeedError(f"Invalid feed format: {parsed.bozo_exception}")

    title = parsed.feed.get("title", "").strip()
    if not title:
        raise FeedError("Feed has no title")

    if not parsed.entries:
        raise FeedError("Feed has no episodes")

    return FeedData(title=title, raw_xml=raw_xml, episode_count=len(parsed.entries))


def get_latest_episodes(url: str, count: int = 2) -> list[Episode]:
    """Fetches feed and returns the N most recent episodes by publish date."""
    with urlopen(url, timeout=30) as response:  # noqa: S310
        raw_xml = response.read()

    parsed = feedparser.parse(raw_xml)

    # Sort entries by published_parsed, most recent first
    sorted_entries = sorted(
        parsed.entries,
        key=lambda e: e.get("published_parsed") or (1970, 1, 1, 0, 0, 0, 0, 0, 0),
        reverse=True,
    )

    episodes = []
    for entry in sorted_entries:
        if len(episodes) >= count:
            break

        enclosure_url = None
        for link in entry.get("links", []):
            if link.get("rel") == "enclosure" or link.get("type", "").startswith(
                "audio/"
            ):
                enclosure_url = link.get("href")
                break
        if not enclosure_url:
            for enc in entry.get("enclosures", []):
                enclosure_url = enc.get("href")
                break

        if not enclosure_url:
            continue

        guid = entry.get("id") or entry.get("guid") or enclosure_url
        episodes.append(Episode(guid=guid, url=enclosure_url))

    return episodes


def regenerate_feed(url: str, url_hash: str, processed_episodes: dict) -> None:
    """Fetches original feed, replaces enclosure URLs for processed episodes, uploads to S3."""
    with urlopen(url, timeout=30) as response:  # noqa: S310
        raw_xml = response.read()

    xml_str = raw_xml.decode("utf-8")

    for guid, data in processed_episodes.items():
        original_url = data["original_url"]
        s3_url = data["s3_url"]
        xml_str = re.sub(
            rf'(<enclosure[^>]*url=["\']){re.escape(original_url)}(["\'][^>]*>)',
            rf"\g<1>{s3_url}\g<2>",
            xml_str,
        )

    upload_feed_xml(url_hash=url_hash, xml_content=xml_str.encode("utf-8"))
    logger.info(
        f"Regenerated feed for {url_hash} with {len(processed_episodes)} processed episodes"
    )
