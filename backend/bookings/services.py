"""Seat and booking operations.

Every change to a departure's seat counters goes through this module. Each function locks the
departure row (SELECT ... FOR UPDATE) inside a transaction, so two requests for the last seat
can't both succeed; the no_overbooking CHECK constraint is the final safety net.
"""
from datetime import timedelta
from decimal import Decimal

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
        Refund.objects.create(booking=b, payment=payment, amount=amount, refund_pct=pct, fee_refunded=fee_back,
                              initiated_by=actor, reason=reason, status=Refund.Status.PENDING)
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
def create_online_booking(*, departure_id, seats, lead_name, lead_phone, lead_email, co_travellers, payment_method,
                          payment_detail, user=None):
    """Traveller checkout: re-check seats under a row lock, then book and record the (demo) payment."""
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
        total_amount=q["total"], status=Booking.Status.CONFIRMED, confirmed_at=timezone.now(),
        guest_token=secrets.token_urlsafe(32))
    BookingTraveller.objects.create(booking=b, full_name=lead_name, is_lead=True)
    for name in co_travellers:
        BookingTraveller.objects.create(booking=b, full_name=name)
    Departure.objects.filter(pk=dep.pk).update(booked_seats=F("booked_seats") + seats)
    # Demo gateway: a real integration creates the order first and captures it from a verified webhook.
    Payment.objects.create(booking=b, gateway="demo", gateway_order_id=f"order_{b.booking_code}_{secrets.token_hex(4)}",
                           gateway_payment_id=f"pay_{b.booking_code}_{secrets.token_hex(4)}", method=payment_method,
                           method_detail=payment_detail[:60], amount=b.total_amount, status=Payment.Status.CAPTURED, paid_at=timezone.now())
    audit(user if user and user.is_authenticated else None, "booking.online_created", b, seats=seats)
    return b


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
