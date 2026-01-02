"""
Extraction service for structured data from transcriptions.
"""

import os

from openai import OpenAI

from .types import AdvertisementData, TranscriptionResult


def extract_from_transcription(
    transcription: TranscriptionResult,
    model: str = "deepseek/deepseek-v3.2",
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
""".strip()

    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": transcription.readable_segments()},
        ],
        text_format=AdvertisementData,
    )

    assert isinstance(response.output_parsed, AdvertisementData)

    return response.output_parsed
