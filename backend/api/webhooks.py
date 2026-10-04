"""Razorpay → PakkaTrip server-to-server events — /api/payments/razorpay/webhook/

Set this URL on the Razorpay dashboard (Settings → Webhooks) with the events payment.captured,
payment.authorized, order.paid, refund.processed, refund.failed, payout.processed, payout.reversed,
payout.failed, payout.updated and transfer.failed (Route), and put the same secret in
RAZORPAY_WEBHOOK_SECRET. It is the safety net for travellers who pay but close the tab before the
checkout callback reaches us; every handler is idempotent because Razorpay retries deliveries.
"""
import json
import logging

from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bookings.services import SeatError, settle_online_payment
from payments import razorpay
from payments.models import Payment, Payout, Refund, Transfer
from payments.payouts import apply_payout

log = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    if not razorpay.verify_webhook_signature(request.body, request.headers.get("X-Razorpay-Signature")):
        return HttpResponse("bad signature", status=400)
    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse("bad json", status=400)
    kind, payload = event.get("event", ""), event.get("payload", {})

    if kind in ("payment.captured", "payment.authorized", "order.paid"):
        p = payload.get("payment", {}).get("entity", {})
        pay = Payment.objects.filter(gateway="razorpay", gateway_order_id=p.get("order_id")).first()
        if pay and p.get("id"):
            try:
                settle_online_payment(pay.booking_id, order_id=p["order_id"], payment_id=p["id"])
            except (SeatError, razorpay.GatewayError) as e:   # late payments are refunded inside settle_online_payment
                log.warning("Razorpay %s for %s not settled: %s", kind, p.get("order_id"), e)
                if isinstance(e, razorpay.GatewayError):
                    return HttpResponse("retry", status=503)   # Razorpay will redeliver

    elif kind in ("refund.processed", "refund.failed"):
        r = payload.get("refund", {}).get("entity", {})
        refund = Refund.objects.filter(gateway_refund_id=r.get("id")).first()
        if refund and refund.status not in (Refund.Status.PROCESSED, Refund.Status.FAILED):
            if kind == "refund.processed":
                refund.status, refund.processed_at = Refund.Status.PROCESSED, timezone.now()
            else:
                refund.status = Refund.Status.FAILED
            refund.save(update_fields=["status", "processed_at"])

    elif kind.startswith("payout."):
        e = payload.get("payout", {}).get("entity", {})
        payout = Payout.objects.filter(gateway_payout_id=e.get("id")).first()
        if payout:
            apply_payout(payout, e)

    elif kind == "transfer.failed":
        e = payload.get("transfer", {}).get("entity", {})
        Transfer.objects.filter(gateway_transfer_id=e.get("id")).update(status=Transfer.Status.FAILED)   # falls back to payouts

    return HttpResponse("ok")
