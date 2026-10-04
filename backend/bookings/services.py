"""Seat and booking operations.

Every change to a departure's seat counters goes through this module. Each function locks the
departure row (SELECT ... FOR UPDATE) inside a transaction, so two requests for the last seat
can't both succeed; the no_overbooking CHECK constraint is the final safety net.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Package
from core.models import audit
from inventory.models import Departure
from payments.models import Payment, Refund

from .models import Booking, next_booking_code


class SeatError(Exception):
    """A seat request that can't be met; the message is shown to the user as-is."""


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def today():
    return timezone.localdate()


def seat_stats(dep):
    total, booked, held = dep.total_seats, dep.booked_seats, dep.held_seats
    available = max(0, total - booked - held)
    departed = dep.departure_date < today()
    if departed:
        state = "departed"
    elif dep.status != Departure.Status.OPEN:
        state = "blocked"
    elif available == 0:
        state = "soldout"
    elif available <= max(3, total * 0.15):
        state = "fast"
    else:
        state = "open"
    return {
        "total": total, "booked": booked, "pending": held, "available": available,
        "occupancy": round((booked + held) / total * 100) if total else 0,
        "departed": departed, "state": state,
    }


def _lock(departure_id):
    return Departure.objects.select_for_update().select_related("package").get(pk=departure_id)


def _assert_available(dep, seats):
    st = seat_stats(dep)
    if st["departed"]:
        raise SeatError("This departure date has already passed.")
    if dep.status != Departure.Status.OPEN:
        raise SeatError("This date is blocked. Unblock it before taking bookings.")
    if seats > st["available"]:
        raise SeatError(f"Sold out — all {st['total']} seats are booked or on hold." if st["available"] == 0
                        else f"Only {plural(st['available'], 'seat')} available, but {seats} requested. Overbooking is not allowed.")


@transaction.atomic
def create_offline_booking(*, operator, departure_id, customer, phone, seats, paid, user=None):
    """Operator records a phone/WhatsApp booking. No convenience fee on offline bookings."""
    dep = _lock(departure_id)
    if dep.package.operator_id != operator.id:
        raise SeatError("Not your departure.")
    _assert_available(dep, seats)
    price = dep.price_override or dep.package.price_per_person
    base = price * seats
    status = Booking.Status.CONFIRMED if paid else Booking.Status.PENDING_CONFIRMATION
    booking = Booking.objects.create(
        booking_code=next_booking_code(), departure=dep, package=dep.package, operator=operator,
        source=Booking.Source.OFFLINE, lead_name=customer, lead_phone=phone, seats=seats,
        price_per_person=price, base_amount=base, fee_rate=0, convenience_fee=0, total_amount=base,
        status=status, confirmed_at=timezone.now() if paid else None,
    )
    counter = "booked_seats" if paid else "held_seats"
    Departure.objects.filter(pk=dep.pk).update(**{counter: F(counter) + seats})
    audit(user, "booking.offline_created", booking, seats=seats, status=status)
    return booking


@transaction.atomic
def confirm_booking(booking_id, user=None):
    """Pending → confirmed: held seats become booked seats."""
    b = Booking.objects.select_for_update().get(pk=booking_id)
    if b.status != Booking.Status.PENDING_CONFIRMATION:
        raise SeatError("Only pending bookings can be confirmed.")
    _lock(b.departure_id)
    Departure.objects.filter(pk=b.departure_id).update(held_seats=F("held_seats") - b.seats, booked_seats=F("booked_seats") + b.seats)
    b.status, b.confirmed_at = Booking.Status.CONFIRMED, timezone.now()
    b.save(update_fields=["status", "confirmed_at", "updated_at"])
    audit(user, "booking.confirmed", b)
    return b


def customer_refund_quote(b, on=None):
    """What a traveller gets back if they cancel now: policy % of the package amount; the fee is kept."""
    from core.models import CancellationRule
    on = on or today()
    days = (b.departure.departure_date - on).days
    rules = CancellationRule.objects.filter(is_active=True, effective_from__lte=timezone.localtime(b.created_at).date()).order_by("-min_days_before")
    rule = next((r for r in rules if days >= r.min_days_before), None)
    pct = rule.refund_pct if rule else Decimal(0)
    return {"days": days, "pct": pct, "label": rule.label if rule else "No refund",
            "amount": (b.base_amount * pct / 100).quantize(Decimal("1")), "fee": b.convenience_fee}


@transaction.atomic
def cancel_booking(booking_id, *, actor, reason="", user=None):
    """Release the seats and record the refund.

    Operator/admin cancellations refund everything including the fee; a customer's own
    cancellation follows the cancellation policy (see customer_refund_quote).
    """
    b = Booking.objects.select_for_update().select_related("departure").get(pk=booking_id)
    if b.status not in (Booking.Status.PENDING_CONFIRMATION, Booking.Status.CONFIRMED):
        raise SeatError("Only pending or confirmed bookings can be cancelled.")
    if actor == Booking.Actor.CUSTOMER and b.departure.departure_date <= today():
        raise SeatError("This trip has already started and can't be cancelled.")
    _lock(b.departure_id)
    counter = "held_seats" if b.status == Booking.Status.PENDING_CONFIRMATION else "booked_seats"
    Departure.objects.filter(pk=b.departure_id).update(**{counter: F(counter) - b.seats})
    b.status, b.cancelled_at, b.cancelled_by, b.cancellation_reason = Booking.Status.CANCELLED, timezone.now(), actor, reason
    b.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancellation_reason", "updated_at"])
    payment = b.payments.filter(status=Payment.Status.CAPTURED).first()
    if payment:
        if actor == Booking.Actor.CUSTOMER:
            q = customer_refund_quote(b)
            amount, pct, fee_back = q["amount"], q["pct"], False
        else:
            amount, pct, fee_back = b.total_amount, Decimal(100), True
        r = Refund.objects.create(booking=b, payment=payment, amount=amount, refund_pct=pct, fee_refunded=fee_back,
                                  initiated_by=actor, reason=reason, status=Refund.Status.PENDING)
        transaction.on_commit(lambda: process_refund(r.pk))   # money moves only once the cancellation is saved
        payment.status = Payment.Status.REFUNDED if amount >= payment.amount else Payment.Status.PARTIALLY_REFUNDED
        payment.save(update_fields=["status", "updated_at"])
    audit(user, "booking.cancelled", b, by=actor)
    return b


def price_quote(dep, seats):
    from core.models import PlatformSetting, fee_for
    conf = PlatformSetting.get_all()
    price = dep.price_override or dep.package.price_per_person
    base = price * seats
    fee = fee_for(base, conf)
    return {"price": price, "seats": seats, "base": base, "fee": fee, "total": base + fee,
            "fee_rate": conf["fee_rate_pct"], "fee_min": conf["fee_min_inr"]}


@transaction.atomic
def create_online_booking(*, departure_id, seats, lead_name, lead_phone, lead_email, co_travellers, user=None):
    """Traveller checkout, step 1: re-check seats under a row lock and hold them while the traveller pays.

    The booking starts as pending_payment with its seats in held_seats; confirm_online_payment turns it
    into a confirmed booking, and release_expired_holds frees the seats if payment never arrives.
    """
    import secrets
    from bookings.models import BookingTraveller
    dep = _lock(departure_id)
    if dep.package.status != Package.Status.APPROVED or dep.package.deleted_at or not dep.package.operator.is_verified:
        raise SeatError("This trip is no longer available for booking.")
    if dep.departure_date <= today():
        raise SeatError("Bookings close the day before departure.")
    _assert_available(dep, seats)
    q = price_quote(dep, seats)
    b = Booking.objects.create(
        booking_code=next_booking_code(), user=user if user and user.is_authenticated else None,
        departure=dep, package=dep.package, operator=dep.package.operator, source=Booking.Source.ONLINE,
        lead_name=lead_name, lead_phone=lead_phone, lead_email=lead_email, seats=seats,
        price_per_person=q["price"], base_amount=q["base"], fee_rate=Decimal(str(q["fee_rate"])), convenience_fee=q["fee"],
        total_amount=q["total"], status=Booking.Status.PENDING_PAYMENT, guest_token=secrets.token_urlsafe(32))
    BookingTraveller.objects.create(booking=b, full_name=lead_name, is_lead=True)
    for name in co_travellers:
        BookingTraveller.objects.create(booking=b, full_name=name)
    Departure.objects.filter(pk=dep.pk).update(held_seats=F("held_seats") + seats)
    audit(user if user and user.is_authenticated else None, "booking.online_held", b, seats=seats)
    return b


# ---------------------------------------------------------------- online payment (Razorpay)

class LatePaymentError(SeatError):
    """Money arrived after the seat hold lapsed and the seats are gone; the payment is refunded in full."""


def hold_expires_at(b):
    return b.created_at + timedelta(minutes=settings.PAYMENT_HOLD_MINUTES)


def _expire(b, reason):
    """Locked pending_payment booking → expired; its held seats go back on sale."""
    Departure.objects.filter(pk=b.departure_id).update(held_seats=F("held_seats") - b.seats)
    b.status, b.cancelled_at, b.cancelled_by, b.cancellation_reason = Booking.Status.EXPIRED, timezone.now(), Booking.Actor.SYSTEM, reason
    b.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancellation_reason", "updated_at"])
    b.payments.filter(status=Payment.Status.CREATED).update(status=Payment.Status.FAILED)
    audit(None, "booking.hold_expired", b, reason=reason)


def release_expired_holds(departure_id=None):
    """Free seats held by checkouts that weren't paid within PAYMENT_HOLD_MINUTES. Returns how many."""
    cutoff = timezone.now() - timedelta(minutes=settings.PAYMENT_HOLD_MINUTES)
    qs = Booking.objects.filter(status=Booking.Status.PENDING_PAYMENT, created_at__lt=cutoff)
    if departure_id:
        qs = qs.filter(departure_id=departure_id)
    n = 0
    for pk in qs.values_list("pk", flat=True):
        with transaction.atomic():
            b = Booking.objects.select_for_update().get(pk=pk)
            if b.status == Booking.Status.PENDING_PAYMENT:
                _lock(b.departure_id)
                _expire(b, "Payment not completed in time")
                n += 1
    return n


@transaction.atomic
def abandon_payment(booking_id, reason="Payment cancelled by traveller"):
    """Traveller closed checkout (or the order couldn't be created): release the hold right away."""
    b = Booking.objects.select_for_update().get(pk=booking_id)
    if b.status == Booking.Status.PENDING_PAYMENT:
        _lock(b.departure_id)
        _expire(b, reason)
    return b


@transaction.atomic
def confirm_online_payment(booking_id, *, order_id, payment_id, method="", detail=""):
    """A captured, verified payment → confirmed booking. Safe to call twice (checkout callback + webhook)."""
    b = Booking.objects.select_for_update().get(pk=booking_id)
    pay = Payment.objects.select_for_update().get(booking=b, gateway_order_id=order_id)
    if pay.status == Payment.Status.CAPTURED and b.status in (Booking.Status.CONFIRMED, Booking.Status.COMPLETED):
        return b
    if b.status == Booking.Status.PENDING_PAYMENT:
        _lock(b.departure_id)
        Departure.objects.filter(pk=b.departure_id).update(held_seats=F("held_seats") - b.seats, booked_seats=F("booked_seats") + b.seats)
    elif b.status == Booking.Status.EXPIRED:
        # Paid after the hold lapsed: take the seats again if they're still free, else refund.
        dep = _lock(b.departure_id)
        st = seat_stats(dep)
        if st["departed"] or dep.status != Departure.Status.OPEN or st["available"] < b.seats:
            raise LatePaymentError("Your payment arrived after the seat hold expired and the seats were taken. "
                                   "A full refund has been started.")
        Departure.objects.filter(pk=b.departure_id).update(booked_seats=F("booked_seats") + b.seats)
        b.cancelled_at, b.cancelled_by, b.cancellation_reason = None, "", ""
    else:
        raise SeatError("This booking can no longer take a payment.")
    b.status, b.confirmed_at = Booking.Status.CONFIRMED, timezone.now()
    b.save(update_fields=["status", "confirmed_at", "cancelled_at", "cancelled_by", "cancellation_reason", "updated_at"])
    pay.status, pay.gateway_payment_id, pay.method, pay.method_detail, pay.paid_at = (
        Payment.Status.CAPTURED, payment_id, method[:12], detail[:60], timezone.now())
    pay.save(update_fields=["status", "gateway_payment_id", "method", "method_detail", "paid_at", "updated_at"])
    audit(None, "booking.paid", b, payment=payment_id)
    from payments.payouts import create_route_transfer
    transaction.on_commit(lambda: create_route_transfer(b.pk))   # Route mode only; no-op otherwise
    return b


@transaction.atomic
def refund_late_payment(booking_id, *, order_id, payment_id, method="", detail=""):
    """Record a payment we can't honour and refund all of it, including the fee."""
    b = Booking.objects.select_for_update().get(pk=booking_id)
    pay = Payment.objects.select_for_update().get(booking=b, gateway_order_id=order_id)
    if pay.status != Payment.Status.FAILED and pay.status != Payment.Status.CREATED:
        return b
    pay.status, pay.gateway_payment_id, pay.method, pay.method_detail, pay.paid_at = (
        Payment.Status.REFUNDED, payment_id, method[:12], detail[:60], timezone.now())
    pay.save(update_fields=["status", "gateway_payment_id", "method", "method_detail", "paid_at", "updated_at"])
    r = Refund.objects.create(booking=b, payment=pay, amount=pay.amount, refund_pct=Decimal(100), fee_refunded=True,
                              initiated_by=Booking.Actor.SYSTEM, reason="Paid after seat hold expired; seats no longer available")
    transaction.on_commit(lambda: process_refund(r.pk))
    audit(None, "booking.late_payment_refunded", b, payment=payment_id)
    return b


def settle_online_payment(booking_id, *, order_id, payment_id):
    """Check a Razorpay payment with the gateway (capturing it if only authorised) and confirm the booking.

    Raises GatewayError if Razorpay can't be reached, SeatError if the payment isn't usable, and
    LatePaymentError (after starting a full refund) if the seats were lost while the traveller paid.
    """
    from payments import razorpay
    b = Booking.objects.get(pk=booking_id)
    p = razorpay.fetch_payment(payment_id)
    if p.get("order_id") != order_id or int(p.get("amount", 0)) != razorpay.to_paise(b.total_amount):
        raise SeatError("This payment doesn't match the booking.")
    if p.get("status") == "authorized":
        try:
            p = razorpay.capture_payment(payment_id, b.total_amount)
        except razorpay.GatewayError:
            p = razorpay.fetch_payment(payment_id)   # the webhook may have captured it already
    if p.get("status") != "captured":
        raise SeatError("The payment didn't go through. No money was taken — please try again.")
    method, detail = razorpay.method_label(p)
    try:
        return confirm_online_payment(b.pk, order_id=order_id, payment_id=payment_id, method=method, detail=detail)
    except LatePaymentError:
        refund_late_payment(b.pk, order_id=order_id, payment_id=payment_id, method=method, detail=detail)
        raise


def process_refund(refund_id):
    """Send a pending refund to Razorpay. Demo-gateway refunds stay as records only.

    Failures leave the refund pending with a reason; `manage.py payment_jobs` retries them.
    """
    from payments import razorpay
    r = Refund.objects.select_related("payment", "booking").get(pk=refund_id)
    if r.status != Refund.Status.PENDING or r.payment.gateway != "razorpay":
        return r
    if r.amount <= 0:
        r.status, r.processed_at = Refund.Status.PROCESSED, timezone.now()
        r.save(update_fields=["status", "processed_at"])
        return r
    from payments.payouts import reverse_for_refund
    reverse_for_refund(r)   # Route: take the refunded part back from the operator's transfer first
    try:
        res = razorpay.refund_payment(r.payment.gateway_payment_id, r.amount, notes={"booking": r.booking.booking_code})
    except razorpay.GatewayError as e:
        r.failure_reason = str(e)[:200]
        r.save(update_fields=["failure_reason"])
        return r
    r.gateway_refund_id, r.failure_reason = res["id"], ""
    r.status = Refund.Status.PROCESSED if res.get("status") == "processed" else Refund.Status.PROCESSING
    r.processed_at = timezone.now() if r.status == Refund.Status.PROCESSED else None
    r.save(update_fields=["gateway_refund_id", "failure_reason", "status", "processed_at"])
    return r


def refund_amount(b):
    r = b.refunds.first() if hasattr(b, "refunds") else None
    return r.amount if r else (Decimal(0) if b.status == Booking.Status.CANCELLED else None)


@transaction.atomic
def set_total_seats(departure_id, total, user=None):
    dep = _lock(departure_id)
    used = dep.booked_seats + dep.held_seats
    if total < used:
        raise SeatError(f"You already have {dep.booked_seats} booked and {dep.held_seats} pending seats on this date. "
                        f"Total seats can't go below {used}.")
    dep.total_seats = total
    dep.save(update_fields=["total_seats", "updated_at"])
    audit(user, "departure.seats_changed", dep, total=total)
    return dep


def create_departure(*, package, date, total_seats, user=None):
    if package.status in (Package.Status.REJECTED,):
        raise SeatError("You can't add dates to a rejected package.")
    if date < today():
        raise SeatError("Departure date cannot be in the past.")
    if Departure.objects.filter(package=package, departure_date=date).exists():
        raise SeatError(f"{package.title} already has a departure on {date:%d %b %Y}.")
    dep = Departure.objects.create(package=package, departure_date=date, total_seats=total_seats)
    audit(user, "departure.created", dep)
    return dep


@transaction.atomic
def mark_completed_trips():
    """Confirmed bookings whose trip has ended become completed (run nightly)."""
    n = 0
    for b in Booking.objects.select_related("departure", "package").filter(status=Booking.Status.CONFIRMED,
                                                                          departure__departure_date__lt=today()):
        if b.departure.departure_date + timedelta(days=b.package.nights) < today():
            b.status = Booking.Status.COMPLETED
            b.save(update_fields=["status", "updated_at"])
            n += 1
    return n
