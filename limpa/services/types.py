"""
Common types for limpa services.
"""

from pydantic import BaseModel


class Segment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptionResult(BaseModel):
    text: str
    segments: list[Segment]

    def readable_segments(self, first_n_words: int = 15) -> str:
        """Return a list of readable text segments with start time and first N words."""
        return "\n".join(
            [
                f"[{seg.start:.2f} secs] {' '.join(seg.text.split()[:first_n_words])}..."
                for seg in self.segments
            ]
        )


class AdvertisementItem(BaseModel):
    short_summary: str
    start_timestamp_seconds: float
    end_timestamp_seconds: float


class AdvertisementData(BaseModel):
    ads_list: list[AdvertisementItem]
