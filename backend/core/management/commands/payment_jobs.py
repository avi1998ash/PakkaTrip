from django.core.management.base import BaseCommand

from bookings.services import process_refund, release_expired_holds
from payments.models import Payout, Refund
from payments.payouts import PayoutError, release_completed_transfers, sync_payout


class Command(BaseCommand):
    help = ("Release seats from unpaid checkouts, retry refunds that didn't reach Razorpay, refresh operator payouts "
            "and release Route transfers for completed trips. Schedule every 5 minutes.")

    def handle(self, *args, **options):
        released = release_expired_holds()
        retried = 0
        for pk in Refund.objects.filter(status=Refund.Status.PENDING, payment__gateway="razorpay").values_list("pk", flat=True):
            process_refund(pk)
            retried += 1
        open_payouts = list(Payout.objects.exclude(status__in=[*Payout.FINAL_FAILED, Payout.Status.PROCESSED]))
        for p in open_payouts:
            try:
                sync_payout(p)
            except PayoutError as e:   # recorded on the payout; its bookings become due again
                self.stderr.write(f"Payout {p.pk}: {e}")
        transfers = release_completed_transfers()
        self.stdout.write(self.style.SUCCESS(
            f"Released {released} expired hold(s); retried {retried} refund(s); refreshed {len(open_payouts)} payout(s); "
            f"released {transfers} Route transfer(s)."))
