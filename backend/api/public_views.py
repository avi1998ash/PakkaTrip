"""Traveller-site endpoints — /api/public/…

Browsing needs no login. Bookings can be made as a guest or a signed-in traveller; a guest opens
their own ticket with the booking's secret key (returned once at checkout, or via "find booking").
"""
import secrets
from collections import defaultdict

from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.timezone import localtime
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from bookings.models import Booking
from bookings.services import (LatePaymentError, SeatError, abandon_payment, cancel_booking, create_online_booking,
                               customer_refund_quote, hold_expires_at, price_quote, release_expired_holds, seat_stats,
                               settle_online_payment)
from catalog.media import facilities_out, images_out
from catalog.models import Package
from core.models import CancellationRule, PlatformSetting
from inventory.models import Departure
from operators.models import Operator
from payments import razorpay
from payments.models import Payment
from reviews.models import Review, refresh_ratings

from .serializers import UNPAID, validate_phone

PUBLIC = [AllowAny]
DEFAULT_EXCLUSIONS = ["Personal expenses and tips", "Entry tickets and adventure activities not listed",
                      "Anything not mentioned under inclusions", "GST on optional add-ons"]


class SensitiveThrottle(AnonRateThrottle):
    rate = "20/min"


def err(msg, code=400):
    return Response({"detail": msg}, status=code)


def live_packages():
    return (Package.objects.filter(status=Package.Status.APPROVED, operator__status=Operator.Status.VERIFIED)
            .select_related("operator__city", "from_city", "to_city").prefetch_related("images", "facilities"))


def tomorrow():
    return timezone.localdate() + timezone.timedelta(days=1)


def inclusion_keys(fac):
    """Facility sections → the small icon list on package cards (same keys as the prototype)."""
    keys = []
    if fac["transport"]:
        keys.append("transport")
    stays = fac["accommodation"]
    if any(s != "Camp / tent" for s in stays):
        keys.append("hotel")
    if "Camp / tent" in stays:
        keys.append("camp")
    if fac["meals"]:
        keys.append("meals")
    if fac["places"]:
        keys.append("sightseeing")
    if "Trip captain" in fac["other"]:
        keys.append("guide")
    if fac["activities"]:
        keys.append("activity")
    return keys


def cover_url(p):
    imgs = list(p.images.all())
    c = next((i for i in imgs if i.is_cover), imgs[0] if imgs else None)
    return c.image.url if c else None


def card_out(p, best, popularity):
    fac = facilities_out(p)
    return {
        "id": p.id, "title": p.title, "from_city": p.from_city.name, "to_city": p.to_city.name, "nights": p.nights,
        "price": p.price_per_person, "cover_url": cover_url(p), "operator": p.operator.business_name,
        "verified": p.operator.is_verified, "tier": p.operator.tier or None, "rating": float(p.rating_avg), "reviews": p.rating_count,
        "inc": inclusion_keys(fac), "popularity": popularity,
        "best": {"id": best.id, "date": best.departure_date, **seat_stats(best)} if best else None,
    }


def best_departures(pkgs, from_date, pax):
    """First open departure on/after from_date with at least `pax` seats, per package."""
    start = max(from_date or tomorrow(), tomorrow())
    deps = Departure.objects.filter(package__in=pkgs, departure_date__gte=start, status=Departure.Status.OPEN).order_by("departure_date")
    best = {}
    for d in deps:
        if d.package_id not in best and d.available_seats >= pax:
            best[d.package_id] = d
    return best


def popularity_map(pkgs):
    rows = Booking.objects.filter(package__in=pkgs).exclude(status__in=["cancelled", *UNPAID]).values("package").annotate(n=Count("id"))
    return {r["package"]: r["n"] for r in rows}


# ---------------------------------------------------------------- traveller accounts

def traveller_payload(user):
    return {"id": user.id, "email": user.email, "name": user.full_name, "phone": user.phone, "role": user.role, "operator": None}


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh), "user": traveller_payload(user)}


class SignupIn(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    phone = serializers.CharField(validators=[validate_phone])
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, max_length=64)

    def validate_email(self, v):
        v = v.strip().lower()
        if User.objects.filter(email=v).exists():
            raise serializers.ValidationError("An account with this email already exists. Log in instead.")
        return v

    def validate_phone(self, v):
        if User.objects.filter(phone=v).exists():
            raise serializers.ValidationError("An account with this mobile number already exists.")
        return v


@api_view(["POST"])
@permission_classes(PUBLIC)
@throttle_classes([SensitiveThrottle])
def signup(request):
    ser = SignupIn(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data
    user = User.objects.create_user(d["email"], d["password"], full_name=d["name"].strip(), phone=d["phone"], role=User.Role.TRAVELLER)
    return Response(tokens_for(user), status=201)


@api_view(["POST"])
@permission_classes(PUBLIC)
@throttle_classes([SensitiveThrottle])
def login(request):
    email = str(request.data.get("email", "")).strip().lower()
    user = authenticate(request, email=email, password=str(request.data.get("password", "")))
    if user and user.role != User.Role.TRAVELLER:
        return err("This is the traveller login. Operators and admins sign in on the Partner portal.", 403)
    if not user:
        return err("Invalid email or password", 401)
    return Response(tokens_for(user))


# ---------------------------------------------------------------- browsing

@api_view(["GET"])
@permission_classes(PUBLIC)
def home(request):
    pkgs = list(live_packages())
    pop = popularity_map(pkgs)
    best = best_departures(pkgs, None, 1)
    featured = sorted(pkgs, key=lambda p: -pop.get(p.id, 0))[:8]
    routes = defaultdict(list)
    for p in pkgs:
        routes[(p.from_city.name, p.to_city.name)].append(p)
    route_list = sorted(({"from": f, "to": t, "count": len(ps), "min_price": min(p.price_per_person for p in ps)}
                         for (f, t), ps in routes.items()), key=lambda r: (-r["count"], r["min_price"]))[:8]
    seen, testimonials = set(), []
    for r in Review.objects.filter(rating=5, is_published=True).select_related("package").order_by("-created_at"):
        if r.comment not in seen:
            seen.add(r.comment)
            testimonials.append({"customer": r.reviewer_name, "rating": r.rating, "text": r.comment, "date": localtime(r.created_at).date(), "package": r.package.title})
        if len(testimonials) == 6:
            break
    agg = Review.objects.filter(is_published=True).aggregate(n=Count("id"), s=Sum("rating"))
    verified = Operator.objects.filter(status=Operator.Status.VERIFIED)
    return Response({
        "featured": [card_out(p, best.get(p.id), pop.get(p.id, 0)) for p in featured],
        "routes": route_list, "testimonials": testimonials,
        "stats": {
            "trips_run": sum(o.trips_run_offline for o in verified),
            "travellers": Booking.objects.exclude(status__in=["cancelled", *UNPAID]).aggregate(s=Sum("seats"))["s"] or 0,
            "avg_rating": round(agg["s"] / agg["n"], 1) if agg["n"] else None,
            "verified_operators": verified.count(),
        },
        "cities": {"from": sorted({p.from_city.name for p in pkgs}), "to": sorted({p.to_city.name for p in pkgs})},
    })


@api_view(["GET"])
@permission_classes(PUBLIC)
def search(request):
    q = request.query_params
    pkgs = live_packages()
    frm, to = q.get("from", "").strip(), q.get("to", "").strip()
    if frm:
        pkgs = pkgs.filter(from_city__name__icontains=frm)
    if to:
        pkgs = pkgs.filter(Q(to_city__name__icontains=to) | Q(title__icontains=to))
    try:
        date = timezone.datetime.strptime(q.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        date = None
    pax = min(10, max(1, int(q.get("pax") or 1))) if str(q.get("pax") or "1").isdigit() else 1
    pkgs = list(pkgs)
    best = best_departures(pkgs, date, pax)
    pop = popularity_map(pkgs)
    return Response([card_out(p, best.get(p.id), pop.get(p.id, 0)) for p in pkgs])


@api_view(["GET"])
@permission_classes(PUBLIC)
def package_detail(request, pk):
    release_expired_holds()
    p = get_object_or_404(live_packages().prefetch_related("itinerary"), pk=pk)
    today = timezone.localdate()
    deps = p.departures.filter(departure_date__gt=today).order_by("departure_date")[:12]
    reviews = list(p.reviews.filter(is_published=True).order_by("-created_at"))
    op = p.operator
    fac = facilities_out(p)
    days = p.nights + 1
    itinerary = [{"day": d.day_number, "title": d.title, "text": d.description} for d in p.itinerary.all()] or [
        {"day": i + 1, "title": f"{p.from_city.name} → {p.to_city.name}" if i == 0 else f"{p.to_city.name} → {p.from_city.name}" if i == days - 1 else f"Explore {p.to_city.name}",
         "text": "The operator shares exact timings after booking."} for i in range(days)]
    return Response({
        "id": p.id, "title": p.title, "from_city": p.from_city.name, "to_city": p.to_city.name,
        "nights": p.nights, "price": p.price_per_person, "pickup_point": p.pickup_point,
        "rating": float(p.rating_avg), "reviews_count": p.rating_count,
        "images": images_out(p), "facilities": fac, "inc": inclusion_keys(fac), "itinerary": itinerary, "exclusions": DEFAULT_EXCLUSIONS,
        "operator": {"name": op.business_name, "city": op.city.name, "verified": op.is_verified, "tier": op.tier or None,
                     "joined": localtime(op.created_at).date(),
                     "rating": float(op.rating_avg), "reviews": op.rating_count,
                     "live_packages": op.packages.filter(status=Package.Status.APPROVED).count(),
                     "trips_run": op.trips_run_offline + Departure.objects.filter(package__operator=op, departure_date__lt=today).count()},
        "departures": [{"id": d.id, "date": d.departure_date, "blocked": d.status != "open", **seat_stats(d)} for d in deps],
        "reviews": [{"customer": r.reviewer_name, "rating": r.rating, "text": r.comment, "date": localtime(r.created_at).date(),
                     "reply": r.operator_reply} for r in reviews[:6]],
        "distribution": {s: sum(1 for r in reviews if r.rating == s) for s in (5, 4, 3, 2, 1)},
        "policy": policy_out(),
    })


def policy_out():
    return [{"min_days": r.min_days_before, "pct": float(r.refund_pct), "label": r.label}
            for r in CancellationRule.objects.filter(is_active=True, effective_from__lte=timezone.localdate()).order_by("-min_days_before")]


@api_view(["GET"])
@permission_classes(PUBLIC)
def config(request):
    s = PlatformSetting.get_all()
    pkgs = live_packages().values_list("from_city__name", "to_city__name")
    return Response({"fee_rate": s["fee_rate_pct"], "fee_min": s["fee_min_inr"], "policy": policy_out(),
                     "payments_test_mode": settings.RAZORPAY_KEY_ID.startswith("rzp_test_"),
                     "sms_otp_enabled": s["sms_otp_enabled"], "email_otp_enabled": s["email_otp_enabled"], "site": settings.SITE_INFO,
                     "cities": {"from": sorted({f for f, _ in pkgs}), "to": sorted({t for _, t in pkgs})}})


# ---------------------------------------------------------------- booking

def _seats(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise SeatError("Choose the number of seats.")
    if not 1 <= n <= 10:
        raise SeatError("You can book 1 to 10 seats at a time.")
    return n


@api_view(["POST"])
@permission_classes(PUBLIC)
def quote(request):
    release_expired_holds()
    try:
        dep = get_object_or_404(Departure.objects.select_related("package"), pk=request.data.get("departure_id"),
                                package__status=Package.Status.APPROVED)
        seats = _seats(request.data.get("seats"))
    except SeatError as e:
        return err(str(e))
    st = seat_stats(dep)
    return Response({**price_quote(dep, seats), "available": st["available"], "state": st["state"], "date": dep.departure_date})


class BookingIn(serializers.Serializer):
    departure_id = serializers.IntegerField()
    seats = serializers.IntegerField(min_value=1, max_value=10)
    name = serializers.CharField(max_length=100)
    phone = serializers.CharField(validators=[validate_phone])
    email = serializers.EmailField()
    co_travellers = serializers.ListField(child=serializers.CharField(max_length=100, allow_blank=True), required=False, default=list)


@api_view(["POST"])
@permission_classes(PUBLIC)
def create_booking(request):
    """Hold the seats and open a Razorpay order. The booking is confirmed by /pay/verify/ (or the webhook)."""
    if not razorpay.enabled():
        return err("Online payments aren't set up yet. Please try again later.", 503)
    ser = BookingIn(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data
    co = [c.strip() for c in d["co_travellers"] if c.strip()][: d["seats"] - 1]
    release_expired_holds(d["departure_id"])
    try:
        b = create_online_booking(departure_id=d["departure_id"], seats=d["seats"], lead_name=d["name"].strip(), lead_phone=d["phone"],
                                  lead_email=d["email"].lower(), co_travellers=co,
                                  user=request.user if getattr(request.user, "role", None) == User.Role.TRAVELLER else None)
    except Departure.DoesNotExist:
        return err("This departure no longer exists.", 404)
    except SeatError as e:
        return err(str(e))
    try:
        order = razorpay.create_order(b.total_amount, receipt=b.booking_code, notes={"booking": b.booking_code})
    except razorpay.GatewayError as e:
        abandon_payment(b.pk, reason="Payment order could not be created")
        return err(f"{e} No money was charged.", 502)
    Payment.objects.create(booking=b, gateway="razorpay", gateway_order_id=order["id"], amount=b.total_amount)
    return Response({
        "code": b.booking_code, "key": b.guest_token, "total": b.total_amount, "hold_expires_at": hold_expires_at(b),
        "razorpay": {
            "key": settings.RAZORPAY_KEY_ID, "order_id": order["id"], "amount": order["amount"], "currency": order["currency"],
            "name": "PakkaTrip", "description": f"{b.package.title} · {b.departure.departure_date:%d %b %Y} · {b.seats} seat(s)",
            "prefill": {"name": b.lead_name, "email": b.lead_email, "contact": b.lead_phone},
            "notes": {"booking": b.booking_code},
        },
    }, status=201)


@api_view(["POST"])
@permission_classes(PUBLIC)
def payment_verify(request, code):
    """Razorpay checkout's success callback: check the signature, then confirm the booking."""
    b = owned_booking(request, code, unpaid=True)
    if not b:
        return err("Booking not found.", 404)
    order_id = str(request.data.get("razorpay_order_id", ""))
    payment_id = str(request.data.get("razorpay_payment_id", ""))
    if not razorpay.verify_checkout_signature(order_id, payment_id, request.data.get("razorpay_signature")) \
            or not b.payments.filter(gateway_order_id=order_id).exists():
        return err("We couldn't verify this payment. If money was deducted, it will be refunded automatically.")
    try:
        settle_online_payment(b.pk, order_id=order_id, payment_id=payment_id)
    except LatePaymentError as e:
        return err(str(e), 409)
    except SeatError as e:
        return err(str(e))
    except razorpay.GatewayError:
        return err("Payment received, but we couldn't reach the gateway to confirm it. Your booking will update in a few "
                   "minutes — check My Bookings.", 502)
    return Response(ticket_out(_booking(b.booking_code), key=True))


@api_view(["POST"])
@permission_classes(PUBLIC)
def payment_abandon(request, code):
    """Traveller closed checkout without paying: put the held seats back on sale."""
    b = owned_booking(request, code, unpaid=True)
    if not b:
        return err("Booking not found.", 404)
    abandon_payment(b.pk)
    return Response({"ok": True})


def _booking(code):
    return (Booking.objects.select_related("package__from_city", "package__to_city", "operator", "departure")
            .prefetch_related("travellers", "payments", "refunds").get(booking_code=code))


def owned_booking(request, code, unpaid=False):
    """The booking if the requester owns it (signed-in owner, or guest with the secret key), else None.

    Checkouts that were never paid (pending_payment / expired) only count when `unpaid` is set.
    """
    try:
        b = _booking(str(code).upper())
    except Booking.DoesNotExist:
        return None
    if not unpaid and b.status in UNPAID:
        return None
    user = request.user
    if user.is_authenticated and b.user_id == user.id:
        return b
    key = request.query_params.get("key") or request.data.get("key")
    if key and b.guest_token and secrets.compare_digest(str(key), b.guest_token):
        return b
    return None


def ticket_out(b, key=False):
    today = timezone.localdate()
    pay = next((x for x in b.payments.all() if x.paid_at), None)
    cancellable = b.status in (Booking.Status.CONFIRMED, Booking.Status.PENDING_CONFIRMATION) and b.departure.departure_date > today
    trip_over = b.status == Booking.Status.COMPLETED or (b.status == Booking.Status.CONFIRMED and b.departure.departure_date < today)
    out = {
        "code": b.booking_code, "package_id": b.package_id, "title": b.package.title,
        "from_city": b.package.from_city.name, "to_city": b.package.to_city.name, "nights": b.package.nights,
        "travel_date": b.departure.departure_date, "booked_on": localtime(b.created_at).date(), "seats": b.seats,
        "lead_name": b.lead_name, "phone": b.lead_phone, "email": b.lead_email,
        "co_travellers": [t.full_name for t in b.travellers.all() if not t.is_lead],
        "amount": b.base_amount, "fee": b.convenience_fee, "total": b.total_amount,
        "status": b.status, "display": "cancelled" if b.status in ("cancelled", "expired") else "completed" if trip_over else "upcoming",
        "operator": b.operator.business_name, "operator_phone": b.operator.contact_phone, "pickup_point": b.package.pickup_point,
        "payment": f"{pay.get_method_display()}{' · ' + pay.method_detail if pay.method_detail else ''}" if pay else None,
        "cancelled_on": localtime(b.cancelled_at).date() if b.cancelled_at else None, "cancelled_by": b.cancelled_by,
        "refund": sum((r.amount for r in b.refunds.all()), start=0) if b.status == Booking.Status.CANCELLED else None,
        "can_cancel": cancellable, "refund_quote": customer_refund_quote(b) if cancellable else None,
        "can_review": trip_over and not Review.objects.filter(booking=b).exists(),
        "reviewed": Review.objects.filter(booking=b).exists(),
    }
    if key:
        out["key"] = b.guest_token
    return out


@api_view(["GET"])
@permission_classes(PUBLIC)
def booking_detail(request, code):
    b = owned_booking(request, code)
    if not b:
        return err("Ticket not found.", 404)
    return Response(ticket_out(b, key=True))


@api_view(["POST"])
@permission_classes(PUBLIC)
def booking_cancel(request, code):
    b = owned_booking(request, code)
    if not b:
        return err("Ticket not found.", 404)
    try:
        cancel_booking(b.pk, actor=Booking.Actor.CUSTOMER, reason="Cancelled by traveller",
                       user=request.user if request.user.is_authenticated else None)
    except SeatError as e:
        return err(str(e))
    return Response(ticket_out(_booking(b.booking_code), key=True))


@api_view(["POST"])
@permission_classes(PUBLIC)
def booking_review(request, code):
    b = owned_booking(request, code)
    if not b:
        return err("Ticket not found.", 404)
    t = ticket_out(b)
    if not t["can_review"]:
        return err("You can review a trip once, after it's completed.")
    try:
        rating = int(request.data.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    text = str(request.data.get("text", "")).strip()
    if not 1 <= rating <= 5 or len(text) < 10:
        return err("Give a rating and at least a sentence about the trip.")
    Review.objects.create(booking=b, user=b.user, package=b.package, operator=b.operator, reviewer_name=b.lead_name,
                          rating=rating, comment=text[:1000])
    refresh_ratings(b.package, b.operator)
    return Response(ticket_out(_booking(b.booking_code), key=True))


@api_view(["POST"])
@permission_classes(PUBLIC)
@throttle_classes([SensitiveThrottle])
def booking_find(request):
    """Guest lost the link: booking ID + the mobile number used → the ticket key."""
    code = str(request.data.get("code", "")).strip().upper()
    phone = str(request.data.get("phone", "")).strip()
    b = Booking.objects.filter(booking_code=code, lead_phone=phone, source=Booking.Source.ONLINE).exclude(status__in=UNPAID).first()
    if not b or not b.guest_token:
        return err("No booking found with that ID and mobile number.", 404)
    return Response({"code": b.booking_code, "key": b.guest_token})


@api_view(["POST"])
@permission_classes(PUBLIC)
def bookings_lookup(request):
    """My Bookings: the signed-in traveller's bookings plus guest bookings saved on this device."""
    items = request.data.get("items") or []
    found = {}
    user = request.user
    if user.is_authenticated:
        for b in Booking.objects.filter(user=user).exclude(status__in=UNPAID).values_list("booking_code", flat=True):
            found[b] = _booking(b)
    for it in items[:50]:
        code, key = str(it.get("code", "")).upper(), str(it.get("key", ""))
        if code in found:
            continue
        b = Booking.objects.filter(booking_code=code).exclude(status__in=UNPAID).only("guest_token").first()
        if b and b.guest_token and key and secrets.compare_digest(key, b.guest_token):
            found[code] = _booking(code)
    return Response(sorted((ticket_out(b, key=True) for b in found.values()), key=lambda t: (str(t["booked_on"]), t["code"]), reverse=True))

