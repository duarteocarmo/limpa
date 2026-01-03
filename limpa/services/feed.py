import logging
import re
from dataclasses import dataclass

import feedparser

from limpa.services.http import get_with_retry
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
    title: str


def fetch_and_validate_feed(url: str) -> FeedData:
    try:
        raw_xml = get_with_retry(url)
    except Exception as e:
        raise FeedError(f"Failed to fetch feed: {e}") from e

    parsed = feedparser.parse(raw_xml)

    if parsed.bozo and not parsed.entries:
        raise FeedError(f"Invalid feed format: {parsed.bozo_exception}")

    title = parsed.feed.get("title", "").strip()  # type: ignore[union-attr]
    if not title:
        raise FeedError("Feed has no title")

    if not parsed.entries:
        raise FeedError("Feed has no episodes")

    return FeedData(title=title, raw_xml=raw_xml, episode_count=len(parsed.entries))


def get_latest_episodes(url: str, count: int) -> list[Episode]:
    raw_xml = get_with_retry(url)

    parsed = feedparser.parse(raw_xml)

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
        for link in entry.get("links", []):  # type: ignore[union-attr]
            if link.get("rel") == "enclosure" or link.get("type", "").startswith(  # type: ignore[union-attr]
                "audio/"
            ):
                enclosure_url = link.get("href")
                break
        if not enclosure_url:
            for enc in entry.get("enclosures", []):  # type: ignore[union-attr]
                enclosure_url = enc.get("href")
                break

        if not enclosure_url:
            continue

        if not isinstance(enclosure_url, str):
            raise FeedError("Enclosure URL is not a string")

        title: str = entry.get("title", "Untitled Episode")  # type: ignore[union-attr]
        guid: str = entry.get("id") or entry.get("guid") or enclosure_url  # type: ignore[arg-type]

        episodes.append(Episode(guid=guid, url=enclosure_url, title=title))

    return episodes


def regenerate_feed(
    url: str, url_hash: str, processed_episodes: dict, podcast_title: str
) -> None:
    raw_xml = get_with_retry(url)

    xml_str = raw_xml.decode("utf-8")

    for _, data in processed_episodes.items():
        original_url = data["original_url"]
        original_url_escaped = original_url.replace("&", "&amp;")
        original_title = data["title"]
        s3_url = data["s3_url"]
        xml_str = re.sub(
            rf'(<enclosure[^>]*url=["\']){re.escape(original_url_escaped)}(["\'][^>]*>)',
            rf"\g<1>{s3_url}\g<2>",
            xml_str,
        )
        # Handle both plain titles and CDATA-wrapped titles
        # Pattern matches: <title>Title</title> or <title><![CDATA[ Title ]]></title>
        xml_str = re.sub(
            rf"(<item>.*?<title>(?:<!\[CDATA\[)?\s*){re.escape(original_title)}(\s*(?:\]\]>)?</title>.*?</item>)",
            rf"\g<1>{original_title} [AD-FREE]\g<2>",
            xml_str,
            flags=re.DOTALL,
        )
        xml_str = re.sub(
            rf"(<item>.*?<itunes:title>(?:<!\[CDATA\[)?\s*){re.escape(original_title)}(\s*(?:\]\]>)?</itunes:title>.*?</item>)",
            rf"\g<1>{original_title} [AD-FREE]\g<2>",
            xml_str,
            flags=re.DOTALL,
        )

    xml_str = re.sub(
        r"(<title>)(.*?)(</title>)", rf"\1{podcast_title} [AD-FREE]\3", xml_str, count=1
    )

    upload_feed_xml(url_hash=url_hash, xml_content=xml_str.encode("utf-8"))
    logger.info(
        f"Regenerated feed for {url_hash} with {len(processed_episodes)} processed episodes"  # noqa: E501
    )
