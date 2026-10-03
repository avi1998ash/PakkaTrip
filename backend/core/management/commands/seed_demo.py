from django.core.management.base import BaseCommand

from core.demo_seed import seed


class Command(BaseCommand):
    help = "Load the PakkaTrip demo data (same operators, packages and scenarios as the prototype)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing marketplace data first.")

    def handle(self, *args, reset=False, **kwargs):
        self.stdout.write(self.style.SUCCESS(seed(reset=reset)))
