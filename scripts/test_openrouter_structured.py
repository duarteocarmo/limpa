# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai",
#     "pydantic",
# ]
# ///
"""Test OpenRouter structured outputs with the OpenAI Python SDK."""

import os

from openai import OpenAI
from pydantic import BaseModel


class ExtractedInfo(BaseModel):
    name: str
    location: str
    date: str
    attendees: list[str]


SAMPLE_TEXT = """
Last Tuesday, Sarah organized a team meeting at the downtown conference center.
The meeting was attended by John, Maria, and Carlos to discuss the Q4 roadmap.
"""

MODELS = [
    "z-ai/glm-4.7",
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v3.2"

]


def test_structured_output(model: str) -> ExtractedInfo:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )

    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": "Extract the event information."},
            {
                "role": "user",
                "content": "Alice and Bob are going to a science fair on Friday.",
            },
        ],
        text_format=ExtractedInfo,
    )

    assert isinstance(response.output_parsed, ExtractedInfo)

    return response.output_parsed




if __name__ == "__main__":
    for model in MODELS:
        print(f"\n{'=' * 50}")
        print(f"Model: {model}")
        print("=" * 50)
        result = test_structured_output(model=model)
        print(f"Name: {result.name}")
        print(f"Location: {result.location}")
        print(f"Date: {result.date}")
        print(f"Attendees: {result.attendees}")
