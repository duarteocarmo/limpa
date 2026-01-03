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
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    prompt = """
You will be given a transcript of a podcast episode.

The transcript is divided into segments, each with:
- a starting timestamp (in seconds)
- the first N words spoken from that timestamp onward

Your task is to identify and extract ALL advertisement segments.

Definition of an advertisement:
- Host-read ads
- Pre-roll, mid-roll, or post-roll ads
- Sponsored segments where the host promotes, endorses, or sells a product, service, or brand
- Any segment whose primary intent is marketing or promotion and could be removed without harming the editorial content

Important rules:
- Include ad "lead-ins" where the host sets up a purchase recommendation, even if the brand name appears later
- Treat contiguous promotional speech as a single ad, even if the brand is mentioned partway through
- If the host is persuading the listener to buy, try, subscribe, or visit a product/service, it is an ad
- Exclude pure announcements, show intros, or personal reflections unless they directly support a promotion
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
