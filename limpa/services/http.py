import logging
from urllib.request import Request, urlopen

from django.conf import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def get_with_retry(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": settings.REQUESTS_USER_AGENT})
    with urlopen(req, timeout=settings.REQUESTS_TIMEOUT) as response:  # noqa: S310
        return response.read()
