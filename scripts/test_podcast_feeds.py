# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

urls: list[str] = [
    "https://api.substack.com/feed/podcast/458709.rss",
    "https://feeds.megaphone.fm/vergecast",
]


def check_feed(url: str, timeout: int = 10) -> tuple[str, int | str]:
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return (url, response.status)
    except HTTPError as e:
        return (url, e.code)
    except URLError as e:
        return (url, str(e.reason))


def main() -> None:
    if not urls:
        print("No URLs to check. Add URLs to the 'urls' list.")
        return

    for url in urls:
        url, status = check_feed(url)
        print(f"{status} - {url}")


if __name__ == "__main__":
    main()
