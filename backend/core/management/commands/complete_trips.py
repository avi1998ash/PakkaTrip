from django.core.management.base import BaseCommand

from bookings.services import mark_completed_trips


class Command(BaseCommand):
    help = "Mark confirmed bookings as completed once their trip has ended. Schedule nightly."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS(f"{mark_completed_trips()} bookings marked completed."))
