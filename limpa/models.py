import hashlib
from typing import TYPE_CHECKING, ClassVar

from django.db import models

if TYPE_CHECKING:
    from django.db.models import Manager


class Podcast(models.Model):
    objects: ClassVar[Manager]

    class Status(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    url = models.URLField(unique=True)
    url_hash = models.CharField(max_length=64)
    title = models.CharField(max_length=500)
    episode_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_episodes = models.JSONField(
        default=dict
    )  # {guid: {original_url, s3_url}}
    last_refreshed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return str(self.title)

    @property
    def total_ads(self) -> int:
        return sum(
            len(ep.get("ads", {}).get("ads_list", []))
            for ep in self.processed_episodes.values()
        )

    def save(self, *args, **kwargs):
        if not self.url_hash:
            self.url_hash = hashlib.sha256(str(self.url).encode()).hexdigest()
        super().save(*args, **kwargs)
