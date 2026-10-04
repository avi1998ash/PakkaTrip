from django.core.management.base import BaseCommand

from bookings.services import mark_completed_trips
from payments.payouts import release_completed_transfers


class Command(BaseCommand):
    help = "Mark confirmed bookings as completed once their trip has ended, and release their Route transfers. Schedule nightly."

    def handle(self, *args, **kwargs):
        done = mark_completed_trips()
        released = release_completed_transfers()
        self.stdout.write(self.style.SUCCESS(f"{done} bookings marked completed; {released} Route transfer(s) released."))
