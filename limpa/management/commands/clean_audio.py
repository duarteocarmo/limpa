from pathlib import Path

from django.core.management.base import BaseCommand

from limpa.services.audio import remove_ads_from_audio
from limpa.services.extract import extract_from_transcription
from limpa.services.transcribe import transcribe_audio_batch


class Command(BaseCommand):
    help = "Transcribe an audio file, detect ads, and remove them"

    def add_arguments(self, parser):
        parser.add_argument(
            "audio_file", type=str, help="Path to the audio file to clean"
        )
        parser.add_argument(
            "-o",
            "--output",
            type=str,
            help="Output path for cleaned file (default: <filename>_clean.<ext>)",
        )

    def handle(self, *args, **options):
        audio_path = Path(options["audio_file"])

        if not audio_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {audio_path}"))
            return

        if options["output"]:
            output_path = Path(options["output"])
        else:
            output_path = audio_path.with_stem(f"{audio_path.stem}_clean")

        self.stdout.write(f"Transcribing {audio_path}...")
        audio_bytes = audio_path.read_bytes()
        transcription = transcribe_audio_batch([(audio_path.name, audio_bytes)])[0]

        self.stdout.write("Transcription:")
        readable = transcription.readable_segments()
        self.stdout.write(readable)

        transcript_path = output_path.with_suffix(".txt")
        transcript_path.write_text(readable)
        self.stdout.write(f"Transcript saved to: {transcript_path}")

        self.stdout.write("\nExtracting ads from transcription...")
        ads = extract_from_transcription(transcription)

        if not ads.ads_list:
            self.stdout.write(self.style.WARNING("No ads detected"))
            return

        self.stdout.write(f"Found {len(ads.ads_list)} ad(s):")
        for ad in ads.ads_list:
            self.stdout.write(
                f"  - {ad.short_summary}: {ad.start_timestamp_seconds}s - {ad.end_timestamp_seconds}s"  # noqa: E501
            )

        self.stdout.write(f"\nRemoving ads and saving to {output_path}...")
        remove_ads_from_audio(input_path=audio_path, ads=ads, output_path=output_path)

        self.stdout.write(self.style.SUCCESS(f"Cleaned audio saved to: {output_path}"))
