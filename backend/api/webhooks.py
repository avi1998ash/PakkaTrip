"""Razorpay → PakkaTrip server-to-server events — /api/payments/razorpay/webhook/

Set this URL on the Razorpay dashboard (Settings → Webhooks) with the events payment.captured,
payment.authorized, order.paid, refund.processed, refund.failed, payout.processed, payout.reversed,
payout.failed, payout.updated and transfer.failed (Route), and put the same secret in
RAZORPAY_WEBHOOK_SECRET. It is the safety net for travellers who pay but close the tab before the
checkout callback reaches us; every handler is idempotent because Razorpay retries deliveries.
"""
import json
import logging

from django.conf import settings
from django.db import models
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


@csrf_exempt
@require_POST
def cashfree_webhook(request):
    """Cashfree -> PakkaTrip server-to-server webhook events - /api/payments/cashfree/webhook/

    Events: PAYMENT_SUCCESS_WEBHOOK, PAYMENT_FAILED_WEBHOOK, PAYMENT_USER_DROPPED_WEBHOOK, REFUND_STATUS_WEBHOOK
    """
    from bookings.services import settle_cashfree_payment
    from payments import cashfree

    timestamp = request.headers.get("x-webhook-timestamp")
    signature = request.headers.get("x-webhook-signature")

    # In production or whenever signature header is sent, verify signature
    if signature or not settings.DEBUG:
        if not cashfree.verify_webhook_signature(timestamp, request.body, signature):
            return HttpResponse("bad signature", status=400)

    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse("bad json", status=400)

    event_type = event.get("type", "") or event.get("event", "")
    data = event.get("data", {})

    if event_type in ("PAYMENT_SUCCESS_WEBHOOK", "payment.captured", "payment.success"):
        payment_data = data.get("payment", {})
        order_data = data.get("order", {})
        order_id = order_data.get("order_id") or payment_data.get("order_id")
        cf_payment_id = payment_data.get("cf_payment_id")

        if order_id:
            pay = Payment.objects.filter(gateway="cashfree", gateway_order_id=order_id).first()
            if pay:
                try:
                    settle_cashfree_payment(pay.booking_id, order_id=order_id, cf_payment_id=cf_payment_id, signature=signature or "")
                except (SeatError, cashfree.GatewayError) as e:
                    log.warning("Cashfree webhook for %s not settled: %s", order_id, e)
                    if isinstance(e, cashfree.GatewayError):
                        return HttpResponse("retry", status=503)

    elif event_type in ("PAYMENT_FAILED_WEBHOOK", "PAYMENT_USER_DROPPED_WEBHOOK", "payment.failed"):
        payment_data = data.get("payment", {})
        order_data = data.get("order", {})
        order_id = order_data.get("order_id") or payment_data.get("order_id")
        if order_id:
            Payment.objects.filter(gateway="cashfree", gateway_order_id=order_id, status=Payment.Status.CREATED).update(
                status=Payment.Status.FAILED
            )

    elif event_type in ("REFUND_STATUS_WEBHOOK", "refund.processed", "refund.failed"):
        refund_data = data.get("refund", {})
        cf_refund_id = str(refund_data.get("cf_refund_id") or "")
        refund_id = str(refund_data.get("refund_id") or "")
        ref_status = (refund_data.get("refund_status") or "").upper()

        refund = Refund.objects.filter(
            models.Q(gateway_refund_id=cf_refund_id) | models.Q(gateway_refund_id=refund_id)
        ).first() if (cf_refund_id or refund_id) else None

        if refund and refund.status not in (Refund.Status.PROCESSED, Refund.Status.FAILED):
            if ref_status in ("SUCCESS", "PROCESSED"):
                refund.status, refund.processed_at = Refund.Status.PROCESSED, timezone.now()
            elif ref_status in ("FAILED", "CANCELLED"):
                refund.status = Refund.Status.FAILED
            refund.save(update_fields=["status", "processed_at"])

    return HttpResponse("ok")
