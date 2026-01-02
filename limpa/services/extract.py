"""
Extraction service for structured data from transcriptions.
"""

import logging
import os
import time
from functools import wraps

from openai import APITimeoutError, OpenAI
from pydantic import ValidationError

from .types import AdvertisementData, TranscriptionResult


def retry_with_error_injection(max_attempts: int = 3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            error_msg = kwargs.get("error_msg")
            for attempt in range(max_attempts):
                try:
                    kwargs["error_msg"] = error_msg
                    return func(*args, **kwargs)
                except (ValidationError, APITimeoutError) as e:
                    if attempt == max_attempts - 1:
                        logging.warning(f"Final attempt failed: {type(e).__name__}")
                        raise
                    if isinstance(e, ValidationError):
                        error_msg = str(e)
                    logging.info(
                        f"Attempt {attempt + 1} failed with {type(e).__name__}, retrying..."
                    )
                    time.sleep(2**attempt)

        return wrapper

    return decorator


@retry_with_error_injection(max_attempts=3)
def extract_from_transcription(
    transcription: TranscriptionResult | str,
    error_msg: str | None = None,
) -> AdvertisementData:
    """Extract structured data from a transcription result using a Pydantic model."""
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    prompt = """
You will be given a transcript of a podcast episode.
Your transcript contains segments with the starting timestamp in seconds and the first N words of that segment.
Your goal is to identify and extract all the advertisements mentioned in the podcast.
You should detect both advertisements that are read by the podcast host and those that are played as audio clips.
Also detect sponsored sections where the host talks about a sponsor.
If the host is actively trying to sell or promote a product or service, consider that an advertisement.
The goal is to detect advertisement sections that could be removed from the podcast without losing important content.
""".strip()

    if error_msg:
        prompt += f"\n\nYou previously failed with the following error: {error_msg}"

    user_msg = (
        transcription.readable_segments()
        if isinstance(transcription, TranscriptionResult)
        else transcription
    )

    response = client.responses.parse(
        model="deepseek/deepseek-v3.2:nitro",
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ],
        text_format=AdvertisementData,
        temperature=0.0,
        extra_body={"models": ["google/gemini-2.5-flash-lite", "openai/gpt-5-nano"]},
    )

    assert isinstance(response.output_parsed, AdvertisementData)
    return response.output_parsed
