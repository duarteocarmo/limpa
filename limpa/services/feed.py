from dataclasses import dataclass
from urllib.request import urlopen

import feedparser


class FeedError(Exception):
    pass


@dataclass
class FeedData:
    title: str
    raw_xml: bytes
    episode_count: int


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
