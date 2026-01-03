import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import feedparser

from limpa.services.s3 import upload_feed_xml

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_url(url: str, timeout: int = 30) -> bytes:
    """Fetch URL content, retrying with browser User-Agent on 403 errors."""
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except HTTPError as e:
        if e.code != 403:
            raise
        logger.debug(f"Got 403 for {url}, retrying with browser User-Agent")

    req = Request(url, headers={"User-Agent": BROWSER_USER_AGENT})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310
        return response.read()


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
        raw_xml = fetch_url(url)
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


def get_latest_episodes(url: str, count: int = 1) -> list[Episode]:
    """Fetches feed and returns the N most recent episodes by publish date."""
    raw_xml = fetch_url(url)

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

        guid = entry.get("id") or entry.get("guid") or enclosure_url  # type: ignore[arg-type]
        episodes.append(Episode(guid=guid, url=enclosure_url))  # type: ignore[arg-type]

    return episodes


def regenerate_feed(url: str, url_hash: str, processed_episodes: dict) -> None:
    """Fetches original feed, replaces enclosure URLs and adds [No ads] to titles for processed episodes, uploads to S3."""
    raw_xml = fetch_url(url)

    # Parse the XML
    try:
        # Register common podcast namespaces to preserve them
        ET.register_namespace('', 'http://www.w3.org/2005/Atom')
        ET.register_namespace('itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
        ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')

        root = ET.fromstring(raw_xml)

        # Update podcast title in the feed if it doesn't have [No ads]
        channel = root.find(".//channel")
        if channel is not None:
            channel_title = channel.find("title")
            if channel_title is not None and channel_title.text:
                if not channel_title.text.startswith("[No ads]"):
                    channel_title.text = f"[No ads] {channel_title.text}"

        # Build a mapping of original_url -> (s3_url, guid) for quick lookup
        url_to_data = {
            data["original_url"]: {"s3_url": data["s3_url"], "guid": guid}
            for guid, data in processed_episodes.items()
        }

        # Find all item elements (episodes)
        # RSS feeds can have different structures, check for both common patterns
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}item")

        for item in items:
            # Find enclosure element
            enclosure = item.find("enclosure")
            if enclosure is None:
                continue

            enclosure_url = enclosure.get("url")
            if not enclosure_url:
                continue

            # Check if this episode has been processed
            if enclosure_url in url_to_data:
                # Update the enclosure URL to point to S3
                enclosure.set("url", url_to_data[enclosure_url]["s3_url"])

                # Update the episode title to add [No ads]
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    if not title_elem.text.startswith("[No ads]"):
                        title_elem.text = f"[No ads] {title_elem.text}"

        # Serialize back to string
        xml_str = ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")

    except ET.ParseError:
        # Fallback to regex-based replacement if XML parsing fails
        logger.warning("Failed to parse XML, falling back to regex replacement")
        xml_str = raw_xml.decode("utf-8")

        for guid, data in processed_episodes.items():
            original_url = data["original_url"]
            original_url_escaped = original_url.replace("&", "&amp;")
            s3_url = data["s3_url"]
            xml_str = re.sub(
                rf'(<enclosure[^>]*url=["\']){re.escape(original_url_escaped)}(["\'][^>]*>)',
                rf"\g<1>{s3_url}\g<2>",
                xml_str,
            )

    upload_feed_xml(url_hash=url_hash, xml_content=xml_str.encode("utf-8"))
    logger.info(
        f"Regenerated feed for {url_hash} with {len(processed_episodes)} processed episodes"
    )
