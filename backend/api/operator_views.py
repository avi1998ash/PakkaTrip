"""Operator endpoints — /api/operator/…  Every query is scoped to request.operator."""
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from bookings.models import Booking
from bookings.services import (SeatError, cancel_booking, confirm_booking, create_departure, create_offline_booking,
                               set_total_seats)
from catalog.media import (MediaError, clean_facilities, clean_itinerary, parse_json, save_facilities, save_images,
                           save_itinerary)
from catalog.models import STANDARD_FACILITIES, Package
from core.models import audit
from inventory.models import Departure
from reviews.models import Review

from .admin_views import err, filter_bookings
from .permissions import IsOperatorRole
from .serializers import (API_STATUS, DepartureIn, OfflineBookingIn, PackageIn, booking_out, booking_qs, departure_out,
                          package_detail_out, package_out, review_out)

EARNED = [Booking.Status.CONFIRMED, Booking.Status.COMPLETED]
PENDING = API_STATUS["pending"]


def my_packages(request):
    return Package.objects.filter(operator=request.operator)


def my_departures(request):
    return Departure.objects.select_related("package").filter(package__operator=request.operator, package__deleted_at__isnull=True)


def my_bookings(request):
    return booking_qs().filter(operator=request.operator)


@api_view(["GET"])
@permission_classes([IsOperatorRole])
def nav_counts(request):
    return Response({
        "op-bookings": Booking.objects.filter(operator=request.operator, status__in=PENDING).count(),
        "reviews": Review.objects.filter(operator=request.operator, operator_reply="").count(),
    })


@api_view(["GET"])
@permission_classes([IsOperatorRole])
def dashboard(request):
    today = timezone.localdate()
    upcoming = list(my_departures(request).filter(departure_date__gte=today).order_by("departure_date"))
    open_deps = [d for d in upcoming if d.status == Departure.Status.OPEN]
    bk = Booking.objects.filter(operator=request.operator)
    pending = bk.filter(status__in=PENDING).aggregate(n=Count("id"), seats=Sum("seats"))
    rv = Review.objects.filter(operator=request.operator).aggregate(avg=Avg("rating"), n=Count("id"))
    return Response({
        "upcoming_departures": len(open_deps), "blocked_departures": len(upcoming) - len(open_deps),
        "live_packages": my_packages(request).filter(status=Package.Status.APPROVED).count(),
        "seats_filled": sum(d.booked_seats + d.held_seats for d in open_deps),
        "capacity": sum(d.total_seats for d in open_deps),
        "pending_requests": pending["n"], "pending_seats": pending["seats"] or 0,
        "earnings": bk.filter(status__in=EARNED).aggregate(s=Sum("base_amount"))["s"] or 0,
        "rating": round(rv["avg"], 1) if rv["avg"] else None, "reviews": rv["n"],
        "next_departures": [departure_out(d) for d in upcoming[:5]],
        "recent": [booking_out(b) for b in my_bookings(request)[:5]],
    })


# ---------------------------------------------------------------- packages

def my_package_qs(request):
    today = timezone.localdate()
    return (my_packages(request).select_related("operator__city", "from_city", "to_city").prefetch_related("images", "facilities", "itinerary")
            .annotate(n_upcoming=Count("departures", filter=Q(departures__departure_date__gte=today)))
            .order_by("-created_at", "-id"))


def save_package(request, pkg):
    """Basics + photos + facilities in one transaction (multipart form from the package editor)."""
    ser = PackageIn(data=request.data)
    ser.is_valid(raise_exception=True)
    try:
        facilities = clean_facilities(parse_json(request.data.get("facilities"), {}))
        order = parse_json(request.data.get("images"), [])
        itinerary = clean_itinerary(parse_json(request.data.get("itinerary"), []), ser.validated_data["nights"])
        with transaction.atomic():
            pkg = ser.apply(pkg, request.operator)
            save_images(pkg, order, request.data.get("cover", ""), request.FILES.getlist("new_images"))
            save_facilities(pkg, facilities)
            save_itinerary(pkg, itinerary)
    except MediaError as e:
        return None, err(str(e))
    return pkg, None


@api_view(["GET", "POST"])
@permission_classes([IsOperatorRole])
def packages(request):
    if request.method == "POST":
        pkg, error = save_package(request, Package(status=Package.Status.PENDING_REVIEW))
        if error:
            return error
        audit(request.user, "package.submitted", pkg)
        return Response(package_detail_out(my_package_qs(request).get(pk=pkg.pk)), status=201)
    return Response([package_out(p) for p in my_package_qs(request)])


@api_view(["GET", "PATCH"])
@permission_classes([IsOperatorRole])
def package_detail(request, pk):
    pkg = get_object_or_404(my_packages(request), pk=pk)
    if request.method == "PATCH":
        pkg, error = save_package(request, pkg)
        if error:
            return error
        audit(request.user, "package.updated", pkg)
    return Response(package_detail_out(my_package_qs(request).get(pk=pk)))


@api_view(["GET"])
@permission_classes([IsOperatorRole])
def facility_options(request):
    return Response(STANDARD_FACILITIES)


# ---------------------------------------------------------------- seat inventory

@api_view(["GET", "POST"])
@permission_classes([IsOperatorRole])
def departures(request):
    if request.method == "POST":
        ser = DepartureIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        pkg = get_object_or_404(my_packages(request), pk=d["package_id"])
        try:
            dep = create_departure(package=pkg, date=d["date"], total_seats=d["total_seats"], user=request.user)
        except SeatError as e:
            return err(str(e))
        return Response(departure_out(dep), status=201)
    today = timezone.localdate()
    qs = my_departures(request)
    pkg = request.query_params.get("package")
    if pkg and pkg != "all":
        qs = qs.filter(package_id=pkg)
    if request.query_params.get("when") == "past":
        qs = qs.filter(departure_date__lt=today).order_by("-departure_date")
    else:
        qs = qs.filter(departure_date__gte=today).order_by("departure_date")
    return Response([departure_out(d) for d in qs])


@api_view(["PATCH", "DELETE"])
@permission_classes([IsOperatorRole])
def departure_detail(request, pk):
    dep = get_object_or_404(my_departures(request), pk=pk)
    if request.method == "DELETE":
        if dep.bookings.exists():
            return err("This date has booking history. Block it instead of deleting it.")
        dep.delete()
        return Response({"result": "deleted"})
    try:
        total = int(request.data.get("total_seats"))
        if not 1 <= total <= 80:
            raise ValueError
    except (TypeError, ValueError):
        return err("Total seats must be between 1 and 80.")
    try:
        dep = set_total_seats(dep.pk, total, user=request.user)
    except SeatError as e:
        return err(str(e))
    return Response(departure_out(dep))


@api_view(["POST"])
@permission_classes([IsOperatorRole])
def departure_block(request, pk, action):
    dep = get_object_or_404(my_departures(request), pk=pk)
    if action not in ("block", "unblock"):
        return err("Unknown action", 404)
    if dep.departure_date < timezone.localdate():
        return err("This departure has already left.")
    dep.status = Departure.Status.BLOCKED if action == "block" else Departure.Status.OPEN
    dep.blocked_reason = str(request.data.get("reason", "")) if action == "block" else ""
    dep.save(update_fields=["status", "blocked_reason", "updated_at"])
    audit(request.user, f"departure.{action}ed", dep)
    return Response(departure_out(dep))


@api_view(["POST"])
@permission_classes([IsOperatorRole])
def departure_booking(request, pk):
    dep = get_object_or_404(my_departures(request), pk=pk)
    ser = OfflineBookingIn(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data
    try:
        b = create_offline_booking(operator=request.operator, departure_id=dep.pk, customer=d["customer"].strip(),
                                   phone=d["phone"], seats=d["travellers"], paid=d["status"] == "confirmed", user=request.user)
    except SeatError as e:
        return err(str(e))
    return Response(booking_out(booking_qs().get(pk=b.pk)), status=201)


# ---------------------------------------------------------------- bookings

@api_view(["GET"])
@permission_classes([IsOperatorRole])
def bookings(request):
    return Response([booking_out(b) for b in filter_bookings(my_bookings(request), request)])


@api_view(["GET"])
@permission_classes([IsOperatorRole])
def booking_detail(request, code):
    return Response(booking_out(get_object_or_404(my_bookings(request), booking_code=code), detail=True))


@api_view(["POST"])
@permission_classes([IsOperatorRole])
def booking_action(request, code, action):
    b = get_object_or_404(Booking, booking_code=code, operator=request.operator)
    try:
        if action == "confirm":
            confirm_booking(b.pk, user=request.user)
        elif action == "cancel":
            cancel_booking(b.pk, actor=Booking.Actor.OPERATOR, reason=str(request.data.get("reason", "")), user=request.user)
        else:
            return err("Unknown action", 404)
    except SeatError as e:
        return err(str(e))
    return Response(booking_out(booking_qs().get(pk=b.pk), detail=True))


# ---------------------------------------------------------------- earnings & reviews

@api_view(["GET"])
@permission_classes([IsOperatorRole])
def earnings(request):
    bk = Booking.objects.filter(operator=request.operator)
    agg = lambda qs: qs.aggregate(n=Count("id"), amount=Sum("base_amount"))  # noqa: E731
    done, up = agg(bk.filter(status=Booking.Status.COMPLETED)), agg(bk.filter(status=Booking.Status.CONFIRMED))
    pend, lost = agg(bk.filter(status__in=PENDING)), agg(bk.filter(status__in=API_STATUS["cancelled"]))
    rows = (Package.all_objects.filter(operator=request.operator)
            .annotate(trips=Count("bookings", filter=Q(bookings__status__in=EARNED)),
                      pax=Sum("bookings__seats", filter=Q(bookings__status__in=EARNED)),
                      done=Sum("bookings__base_amount", filter=Q(bookings__status=Booking.Status.COMPLETED)),
                      up=Sum("bookings__base_amount", filter=Q(bookings__status=Booking.Status.CONFIRMED)))
            .filter(trips__gt=0))
    by_pkg = sorted(({"title": p.title, "price": p.price_per_person, "trips": p.trips, "pax": p.pax or 0,
                      "done": p.done or 0, "up": p.up or 0} for p in rows), key=lambda r: -(r["done"] + r["up"]))
    return Response({
        "earned": done["amount"] or 0, "earned_count": done["n"], "upcoming": up["amount"] or 0,
        "pending": pend["amount"] or 0, "pending_count": pend["n"],
        "cancelled_count": lost["n"], "cancelled_amount": lost["amount"] or 0, "by_package": by_pkg,
    })


@api_view(["GET"])
@permission_classes([IsOperatorRole])
def reviews(request):
    qs = Review.objects.select_related("package", "booking").filter(operator=request.operator)
    all_rv = list(qs)
    f = request.query_params.get("filter", "all")
    shown = [r for r in all_rv if f == "all" or (f == "unreplied" and not r.operator_reply) or (f == "low" and r.rating <= 3)]
    n = len(all_rv)
    return Response({
        "avg": round(sum(r.rating for r in all_rv) / n, 1) if n else None, "count": n,
        "distribution": {s: sum(1 for r in all_rv if r.rating == s) for s in (5, 4, 3, 2, 1)},
        "items": [review_out(r) for r in shown],
    })


@api_view(["POST"])
@permission_classes([IsOperatorRole])
def review_reply(request, pk):
    r = get_object_or_404(Review, pk=pk, operator=request.operator)
    r.operator_reply = str(request.data.get("reply", "")).strip()[:400]
    r.replied_at = timezone.now() if r.operator_reply else None
    r.save(update_fields=["operator_reply", "replied_at", "updated_at"])
    return Response(review_out(r))

