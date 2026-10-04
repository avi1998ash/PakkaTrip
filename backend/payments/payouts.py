"""Operator settlements: bank details, RazorpayX payouts and Razorpay Route transfers.

What an operator earns from an online booking ("share") is its base fare — the convenience fee stays
with PakkaTrip. If the traveller cancels, the operator keeps the part that wasn't refunded; if the
operator or admin cancels, the operator gets nothing. Offline bookings are paid to the operator directly.

payout_mode (Admin → Settings):
  payouts  The share becomes due when the trip completes (or, for a traveller cancellation, once the
           departure date passes). An admin sends it by RazorpayX payout; each booking records its payout.
  route    The share is transferred to the operator's Route linked account as soon as the payment is
           captured, held until the trip completes, and reversed before any refund. Bookings whose
           transfer couldn't be made fall back to the payouts list.
"""
import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from bookings.models import Booking
from core.crypto import decrypt, encrypt
from core.models import PlatformSetting, audit
from operators.models import Operator, OperatorBankAccount

from . import razorpay
from .models import Payment, Payout, Transfer

log = logging.getLogger(__name__)


class PayoutError(Exception):
    """A settlement action that can't go ahead; the message is shown to the user as-is."""


def payout_mode():
    return PlatformSetting.get_all()["payout_mode"]


# ---------------------------------------------------------------- bank details

def save_bank_account(operator, d, user=None):
    """Operator adds or changes bank details. Any change needs an admin to verify it again."""
    ifsc = d["ifsc"].upper()
    try:
        bank = razorpay.ifsc_lookup(ifsc)
    except razorpay.GatewayError as e:
        raise PayoutError(str(e))
    if not bank:
        raise PayoutError("That IFSC code doesn't exist. Check it on your cheque book or passbook.")
    acct = getattr(operator, "bank_account", None) or OperatorBankAccount(operator=operator)
    acct.holder_name, acct.ifsc, acct.bank_name, acct.branch = d["holder_name"].strip(), ifsc, bank["bank"], bank["branch"]
    acct.account_number_enc, acct.account_last4 = encrypt(d["account_number"]), d["account_number"][-4:]
    acct.pan_enc, acct.pan_last4 = encrypt(d["pan"].upper()), d["pan"][-4:].upper()
    acct.account_type, acct.business_type = d["account_type"], d["business_type"]
    acct.address_line, acct.address_city, acct.address_state, acct.pincode = (
        d["address_line"].strip(), d["address_city"].strip(), d["address_state"].strip(), d["pincode"])
    acct.status, acct.rejection_reason, acct.verified_at, acct.verified_by = OperatorBankAccount.Status.PENDING, "", None, None
    acct.razorpayx_fund_account_id = ""   # a new fund account is made for the new details on verification
    acct.save()
    audit(user, "bank_account.saved", acct, last4=acct.account_last4, ifsc=ifsc)
    return acct


def verify_bank_account(acct, user=None):
    """Admin approves the details: create the Razorpay objects the current payout mode needs."""
    number, op = decrypt(acct.account_number_enc), acct.operator
    try:
        if payout_mode() == "route":
            if not acct.route_account_id:
                la = razorpay.create_linked_account(
                    email=op.contact_email, phone=op.contact_phone, business_name=op.business_name, business_type=acct.business_type,
                    contact_name=acct.holder_name, reference_id=f"operator-{op.pk}",
                    address={"street1": acct.address_line[:100], "street2": acct.address_line[100:] or acct.address_city,
                             "city": acct.address_city, "state": acct.address_state, "postal_code": acct.pincode, "country": "IN"})
                acct.route_account_id = la["id"]
                razorpay.create_stakeholder(acct.route_account_id, acct.holder_name, op.contact_email, decrypt(acct.pan_enc))
            if not acct.route_product_id:
                acct.route_product_id = razorpay.request_route_product(acct.route_account_id)["id"]
            razorpay.set_route_settlement(acct.route_account_id, acct.route_product_id, acct.holder_name, acct.ifsc, number)
        else:
            if not acct.razorpayx_contact_id:
                acct.razorpayx_contact_id = razorpay.create_contact(op.business_name, op.contact_email, op.contact_phone, f"operator-{op.pk}")["id"]
            acct.razorpayx_fund_account_id = razorpay.create_fund_account(acct.razorpayx_contact_id, acct.holder_name, acct.ifsc, number)["id"]
    except razorpay.GatewayError as e:
        acct.save()   # keep any ids already created so a retry doesn't duplicate them
        raise PayoutError(f"Razorpay didn't accept these bank details: {e}")
    acct.status, acct.rejection_reason, acct.verified_at, acct.verified_by = OperatorBankAccount.Status.VERIFIED, "", timezone.now(), user
    acct.save()
    audit(user, "bank_account.verified", acct, mode=payout_mode())
    return acct


def reject_bank_account(acct, reason, user=None):
    acct.status, acct.rejection_reason = OperatorBankAccount.Status.REJECTED, reason[:200]
    acct.save(update_fields=["status", "rejection_reason", "updated_at"])
    audit(user, "bank_account.rejected", acct, reason=reason)
    return acct


# ---------------------------------------------------------------- what's owed

def operator_share(b):
    if b.status in (Booking.Status.CONFIRMED, Booking.Status.COMPLETED):
        return b.base_amount
    if b.status == Booking.Status.CANCELLED and b.cancelled_by == Booking.Actor.CUSTOMER:
        return max(Decimal(0), b.base_amount - sum((r.amount for r in b.refunds.all()), Decimal(0)))
    return Decimal(0)


def _unsettled(operator):
    """Online bookings whose share hasn't gone out by payout or by a working Route transfer."""
    return (Booking.objects.filter(operator=operator, source=Booking.Source.ONLINE, payout__isnull=True)
            .filter(Q(transfer__isnull=True) | Q(transfer__status=Transfer.Status.FAILED))
            .prefetch_related("refunds"))


def due_bookings(operator):
    """(booking, share) pairs that can be paid out now: trip completed, or cancelled by the traveller after the date passed."""
    today = timezone.localdate()
    qs = _unsettled(operator).filter(
        Q(status=Booking.Status.COMPLETED)
        | Q(status=Booking.Status.CANCELLED, cancelled_by=Booking.Actor.CUSTOMER, departure__departure_date__lt=today))
    return [(b, s) for b in qs.order_by("departure__departure_date", "id") if (s := operator_share(b)) > 0]


def upcoming_amount(operator):
    """Shares of confirmed trips that haven't run yet (due after they complete)."""
    return sum((b.base_amount for b in _unsettled(operator).filter(status=Booking.Status.CONFIRMED)), Decimal(0))


# ---------------------------------------------------------------- RazorpayX payouts

def create_operator_payout(operator, user=None):
    """Pay everything that's due to one operator in a single bank transfer."""
    acct = OperatorBankAccount.objects.filter(operator=operator).first()
    if not acct or acct.status != OperatorBankAccount.Status.VERIFIED:
        raise PayoutError(f"{operator.business_name} has no verified bank account.")
    if not settings.RAZORPAYX_ACCOUNT_NUMBER:
        raise PayoutError("Set RAZORPAYX_ACCOUNT_NUMBER in backend/.env (RazorpayX Dashboard → My Account) before sending payouts.")
    if not acct.razorpayx_fund_account_id:
        raise PayoutError("This bank account isn't set up for RazorpayX payouts yet — verify it again with payout mode set to Payouts.")
    with transaction.atomic():
        Operator.objects.select_for_update().get(pk=operator.pk)   # one payout at a time per operator
        items = due_bookings(operator)
        total = sum((s for _, s in items), Decimal(0))
        if total <= 0:
            raise PayoutError("Nothing is due to this operator right now.")
        p = Payout.objects.create(operator=operator, amount=total, account_last4=acct.account_last4, idempotency_key=uuid.uuid4().hex,
                                  mode=settings.RAZORPAYX_PAYOUT_MODE, initiated_by=user)
        Booking.objects.filter(pk__in=[b.pk for b, _ in items]).update(payout=p)
        audit(user, "payout.created", p, amount=str(total), bookings=len(items))
    return _send_payout(p, acct.razorpayx_fund_account_id)


def _send_payout(p, fund_account_id):
    try:
        res = razorpay.create_payout(fund_account_id, p.amount, reference_id=f"payout-{p.pk}", idempotency_key=p.idempotency_key)
    except razorpay.GatewayError as e:
        if e.retryable:   # outcome unknown: payment_jobs retries with the same idempotency key, so it can't pay twice
            p.failure_reason = f"{e} (will retry)"[:200]
            p.save(update_fields=["failure_reason", "updated_at"])
            return p
        apply_payout(p, {"status": Payout.Status.FAILED, "status_details": {"description": str(e)}})
        raise PayoutError(f"Payout failed: {e}")
    return apply_payout(p, res)


@transaction.atomic
def apply_payout(p, res):
    """Copy Razorpay's payout state onto ours. Failed or reversed payouts free their bookings to be paid again."""
    p = Payout.objects.select_for_update().get(pk=p.pk)
    p.gateway_payout_id = res.get("id") or p.gateway_payout_id
    p.status = res.get("status") or p.status
    p.utr = res.get("utr") or p.utr
    detail = (res.get("status_details") or {}).get("description") or res.get("failure_reason") or ""
    p.failure_reason = detail[:200] if p.status in Payout.FINAL_FAILED else ""
    if p.status == Payout.Status.PROCESSED and not p.processed_at:
        p.processed_at = timezone.now()
    p.save()
    if p.status in Payout.FINAL_FAILED:
        Booking.objects.filter(payout=p).update(payout=None)
    return p


def sync_payout(p):
    """Refresh a payout that isn't final yet (or send it, if the first attempt never reached Razorpay)."""
    if p.status in Payout.FINAL_FAILED or p.status == Payout.Status.PROCESSED:
        return p
    if not p.gateway_payout_id:
        acct = OperatorBankAccount.objects.filter(operator=p.operator).first()
        return _send_payout(p, acct.razorpayx_fund_account_id if acct else "")
    try:
        return apply_payout(p, razorpay.fetch_payout(p.gateway_payout_id))
    except razorpay.GatewayError as e:
        log.warning("Couldn't refresh payout %s: %s", p.pk, e)
        return p


# ---------------------------------------------------------------- Razorpay Route

def create_route_transfer(booking_id):
    """After a Route-mode booking is paid: move the operator's share to their linked account, on hold."""
    if payout_mode() != "route":
        return None
    b = Booking.objects.select_related("operator").get(pk=booking_id)
    acct = OperatorBankAccount.objects.filter(operator=b.operator, status=OperatorBankAccount.Status.VERIFIED).exclude(route_account_id="").first()
    pay = b.payments.filter(gateway="razorpay", status=Payment.Status.CAPTURED).first()
    if not acct or not pay or Transfer.objects.filter(booking=b).exists():
        return None   # no linked account yet: the booking stays in the payouts list instead
    try:
        t = razorpay.create_transfer(pay.gateway_payment_id, acct.route_account_id, b.base_amount, notes={"booking": b.booking_code})
    except razorpay.GatewayError as e:
        log.warning("Route transfer for %s failed: %s", b.booking_code, e)
        return None
    return Transfer.objects.create(booking=b, operator=b.operator, payment=pay, gateway_transfer_id=t["id"], amount=b.base_amount)


def release_completed_transfers():
    """Trips that have run: let Razorpay settle the held transfers to the operators. Returns how many."""
    n = 0
    for t in Transfer.objects.filter(status=Transfer.Status.ON_HOLD, booking__status=Booking.Status.COMPLETED):
        try:
            razorpay.release_transfer(t.gateway_transfer_id)
        except razorpay.GatewayError as e:
            log.warning("Couldn't release transfer %s: %s", t.gateway_transfer_id, e)
            continue
        t.status, t.released_at = Transfer.Status.RELEASED, timezone.now()
        t.save(update_fields=["status", "released_at"])
        n += 1
    return n


def reverse_for_refund(refund):
    """Before refunding a Route booking, pull the refunded part back from the operator's transfer."""
    t = Transfer.objects.filter(booking=refund.booking).exclude(status__in=[Transfer.Status.REVERSED, Transfer.Status.FAILED]).first()
    if not t:
        return
    amount = min(t.amount - t.reversed_amount, refund.amount)
    if amount <= 0:
        return
    try:
        razorpay.reverse_transfer(t.gateway_transfer_id, amount)
    except razorpay.GatewayError as e:   # the traveller is still refunded; recover the amount from the operator by hand
        audit(None, "transfer.reversal_failed", t, amount=str(amount), error=str(e))
        return
    t.reversed_amount += amount
    t.status = Transfer.Status.REVERSED if t.reversed_amount >= t.amount else Transfer.Status.PARTIALLY_REVERSED
    t.save(update_fields=["reversed_amount", "status"])
