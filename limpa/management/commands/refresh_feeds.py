from django.core.management.base import BaseCommand

from limpa.models import Podcast
from limpa.tasks import process_podcast


class Command(BaseCommand):
    help = "Refresh all podcast feeds by processing their latest episodes"

    def handle(self, *args, **options):
        podcasts = Podcast.objects.all()
        count = podcasts.count()

        if count == 0:
            self.stdout.write("No podcasts to refresh")
            return

        for podcast in podcasts:
            process_podcast.enqueue(podcast_id=podcast.id)  # type: ignore[attr-defined]
            self.stdout.write(f"Enqueued processing for: {podcast.title}")

        self.stdout.write(
            self.style.SUCCESS(f"Enqueued {count} podcast(s) for refresh")
        )
