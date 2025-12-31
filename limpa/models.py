import hashlib
from typing import ClassVar

from django.db import models
from django.db.models import Manager


class Podcast(models.Model):
    objects: ClassVar[Manager]

    class Status(models.TextChoices):
        PENDING = "pending"
        UPLOADED = "uploaded"
        FAILED = "failed"

    url = models.URLField(unique=True)
    url_hash = models.CharField(max_length=64)
    title = models.CharField(max_length=500)
    episode_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return str(self.title)

    def save(self, *args, **kwargs):
        if not self.url_hash:
            self.url_hash = hashlib.sha256(str(self.url).encode()).hexdigest()
        super().save(*args, **kwargs)
