from django.core.management.base import BaseCommand

from phone import voicemail


class Command(BaseCommand):
    help = "Keep the MP3 of each new voicemail message here, so that it plays at once. The worker runs it each minute."

    def handle(self, *args, **options):
        voicemail.download()
