"""Emails to travellers about their bookings."""
import logging

from django.conf import settings
from django.template.loader import render_to_string

from core import mailer
from core.models import audit

from .models import Booking

log = logging.getLogger(__name__)


def inr(amount):
    """₹1,23,456 (Indian digit grouping, no paise), like the website."""
    s = str(int(round(amount)))
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        head, groups = head[:-2], [head[-2:], *groups]
    return "₹" + ",".join([g for g in [head, *groups] if g] + [tail])


def ticket_url(b):
    return f"{settings.SITE_URL}/ticket/{b.booking_code}?key={b.guest_token}"


def send_booking_confirmation(booking_id):
    """Booking confirmed → email the lead traveller their ticket. Never raises: a failed email mustn't undo a paid booking."""
    try:
        b = (Booking.objects.select_related("package__from_city", "package__to_city", "operator", "departure")
             .prefetch_related("travellers").get(pk=booking_id))
        if not b.lead_email:
            return
        site = settings.SITE_INFO
        ctx = {
            "b": b, "site": site, "ticket_url": ticket_url(b), "first_name": b.lead_name.split()[0] if b.lead_name else "there",
            "travellers": [t.full_name for t in b.travellers.all()] or [b.lead_name],
            "date": f"{b.departure.departure_date:%a, %d %b %Y}",
            "nights": f"{b.package.nights} night{'' if b.package.nights == 1 else 's'}",
            "fare": inr(b.base_amount), "fee": inr(b.convenience_fee), "total": inr(b.total_amount),
            "refund_url": f"{settings.SITE_URL}/refund-policy", "support_url": f"{settings.SITE_URL}/contact",
        }
        subject = f"Booking confirmed: {b.package.title} on {b.departure.departure_date:%d %b} ({b.booking_code})"
        mailer.send_email(b.lead_email, subject, render_to_string("emails/booking_confirmed.txt", ctx),
                          render_to_string("emails/booking_confirmed.html", ctx))
        audit(None, "booking.confirmation_emailed", b, to=b.lead_email)
    except mailer.MailError as e:
        log.warning("Booking confirmation email for booking %s not sent: %s", booking_id, e)
    except Exception:   # noqa: BLE001 — log everything; the payment is already settled
        log.exception("Booking confirmation email for booking %s failed", booking_id)
