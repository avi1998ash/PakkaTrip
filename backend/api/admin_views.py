"""Admin endpoints — /api/admin/…"""
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from bookings.models import Booking
from bookings.services import SeatError, cancel_booking
from catalog.models import Package
from core.demo_seed import seed
from core.models import PlatformSetting, audit
from operators.models import Operator, OperatorBankAccount

from .permissions import IsAdminRole
from .serializers import (API_STATUS, UNPAID, OperatorIn, PackageIn, SettingsIn, booking_out, booking_qs, operator_out,
                          package_detail_out, package_out)

EARNED = [Booking.Status.CONFIRMED, Booking.Status.COMPLETED]


def err(msg, code=400):
    return Response({"detail": msg}, status=code)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def dashboard(request):
    bk = Booking.objects.exclude(status__in=UNPAID)
    earned = bk.filter(status__in=EARNED).aggregate(gmv=Sum("base_amount"), fees=Sum("convenience_fee"), pax=Sum("seats"))
    s = PlatformSetting.get_all()
    return Response({
        "total_bookings": bk.count(),
        "travellers": earned["pax"] or 0,
        "pending": bk.filter(status__in=API_STATUS["pending"]).count(),
        "cancelled": bk.filter(status__in=API_STATUS["cancelled"]).count(),
        "gmv": earned["gmv"] or 0, "fees": earned["fees"] or 0,
        "fee_rate": s["fee_rate_pct"], "fee_min": s["fee_min_inr"],
        "verified_operators": Operator.objects.filter(status=Operator.Status.VERIFIED).count(),
        "total_operators": Operator.objects.count(),
        "unverified_operators": Operator.objects.filter(status=Operator.Status.PENDING).count(),
        "live_packages": Package.objects.filter(status=Package.Status.APPROVED).count(),
        "pending_packages": Package.objects.filter(status=Package.Status.PENDING_REVIEW).count(),
        "recent": [booking_out(b) for b in booking_qs()[:6]],
    })


@api_view(["GET"])
@permission_classes([IsAdminRole])
def nav_counts(request):
    return Response({
        "operators": Operator.objects.filter(status=Operator.Status.PENDING).count(),
        "packages": Package.objects.filter(status=Package.Status.PENDING_REVIEW).count(),
        "bookings": Booking.objects.filter(status__in=API_STATUS["pending"]).count(),
        "payouts": OperatorBankAccount.objects.filter(status=OperatorBankAccount.Status.PENDING).count(),
    })


# ---------------------------------------------------------------- operators

@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def operators(request):
    if request.method == "POST":
        ser = OperatorIn(data=request.data)
        ser.is_valid(raise_exception=True)
        op = ser.save()
        audit(request.user, "operator.created", op)
        op.n_packages = 0
        return Response(operator_out(op), status=201)
    qs = Operator.objects.select_related("city").annotate(n_packages=Count("packages", filter=Q(packages__deleted_at__isnull=True))).order_by("-created_at", "-id")
    return Response([operator_out(o) for o in qs])


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def operator_detail(request, pk):
    op = get_object_or_404(Operator, pk=pk)
    if request.method == "DELETE":
        if op.bookings.exists():
            # Bookings must keep pointing at a real operator, so suspend instead of deleting.
            with transaction.atomic():
                op.status = Operator.Status.SUSPENDED
                op.save(update_fields=["status", "updated_at"])
                op.packages.update(status=Package.Status.UNLISTED)
                owner = op.owner
                if owner:
                    owner.is_active = False
                    owner.save(update_fields=["is_active"])
            audit(request.user, "operator.suspended", op)
            return Response({"result": "suspended", "detail": f"{op.business_name} has booking history, so they were suspended and their packages unlisted instead of deleted."})
        with transaction.atomic():
            owner_ids = list(op.members.values_list("user_id", flat=True))
            for p in Package.all_objects.filter(operator=op):
                p.departures.all().delete()
                p.delete()
            op.delete()
            from accounts.models import User
            User.objects.filter(pk__in=owner_ids).delete()
        return Response({"result": "deleted"})
    ser = OperatorIn(op, data=request.data)
    ser.is_valid(raise_exception=True)
    op = ser.save()
    audit(request.user, "operator.updated", op)
    op.n_packages = op.packages.count()
    return Response(operator_out(op))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def operator_verify(request, pk):
    op = get_object_or_404(Operator, pk=pk)
    verified = bool(request.data.get("verified"))
    op.status = Operator.Status.VERIFIED if verified else Operator.Status.PENDING
    op.verified_at, op.verified_by = (timezone.now(), request.user) if verified else (None, None)
    op.save()
    if op.owner and not op.owner.is_active:
        op.owner.is_active = True
        op.owner.save(update_fields=["is_active"])
    audit(request.user, "operator.verified" if verified else "operator.unverified", op)
    op.n_packages = op.packages.count()
    return Response(operator_out(op))


# ---------------------------------------------------------------- packages

def _package_qs():
    today = timezone.localdate()
    return (Package.objects.select_related("operator__city", "from_city", "to_city").prefetch_related("images", "facilities", "itinerary")
            .annotate(n_upcoming=Count("departures", filter=Q(departures__departure_date__gte=today)))
            .order_by("-created_at", "-id"))


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def packages(request):
    if request.method == "POST":
        ser = PackageIn(data=request.data)
        ser.is_valid(raise_exception=True)
        op = Operator.objects.filter(pk=ser.validated_data.get("operator_id")).first()
        if not op:
            return err("Choose an operator.")
        p = ser.apply(Package(status=Package.Status.PENDING_REVIEW), op)
        audit(request.user, "package.created", p)
        return Response(package_out(_package_qs().get(pk=p.pk)), status=201)
    return Response([package_out(p) for p in _package_qs()])


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def package_detail(request, pk):
    """GET returns photos and facilities for review; PATCH edits the basics only."""
    p = get_object_or_404(Package, pk=pk)
    if request.method == "GET":
        return Response(package_detail_out(_package_qs().get(pk=p.pk)))
    if request.method == "DELETE":
        if p.bookings.exists():
            p.deleted_at, p.status = timezone.now(), Package.Status.UNLISTED   # keep history for existing bookings
            p.save(update_fields=["deleted_at", "status", "updated_at"])
        else:
            with transaction.atomic():
                p.departures.all().delete()
                p.delete()
        return Response({"result": "deleted"})
    ser = PackageIn(data=request.data)
    ser.is_valid(raise_exception=True)
    op = Operator.objects.filter(pk=ser.validated_data.get("operator_id") or p.operator_id).first()
    ser.apply(p, op)
    audit(request.user, "package.updated", p)
    return Response(package_out(_package_qs().get(pk=p.pk)))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def package_action(request, pk, action):
    p = get_object_or_404(Package.objects.select_related("operator"), pk=pk)
    if action == "approve":
        if PlatformSetting.get_all()["require_verified_operator"] and not p.operator.is_verified:
            return err("Verify the operator before approving their package")
        p.status, p.approved_by, p.approved_at, p.rejection_reason = Package.Status.APPROVED, request.user, timezone.now(), ""
    elif action == "reject":
        p.status, p.rejection_reason = Package.Status.REJECTED, str(request.data.get("reason", ""))
    elif action == "unlist":
        p.status = Package.Status.PENDING_REVIEW
    else:
        return err("Unknown action", 404)
    p.save()
    audit(request.user, f"package.{action}", p)
    return Response(package_out(_package_qs().get(pk=p.pk)))


# ---------------------------------------------------------------- bookings

def filter_bookings(qs, request):
    st = request.query_params.get("status", "all")
    if st in API_STATUS:
        qs = qs.filter(status__in=API_STATUS[st])
    q = request.query_params.get("q", "").strip()
    if q:
        qs = qs.filter(Q(booking_code__icontains=q) | Q(lead_name__icontains=q) | Q(lead_phone__icontains=q)
                       | Q(package__title__icontains=q) | Q(operator__business_name__icontains=q))
    return qs


@api_view(["GET"])
@permission_classes([IsAdminRole])
def bookings(request):
    return Response([booking_out(b) for b in filter_bookings(booking_qs(), request)])


@api_view(["GET"])
@permission_classes([IsAdminRole])
def booking_detail(request, code):
    return Response(booking_out(get_object_or_404(booking_qs(), booking_code=code), detail=True))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def booking_cancel(request, code):
    b = get_object_or_404(Booking, booking_code=code)
    try:
        cancel_booking(b.pk, actor=Booking.Actor.ADMIN, reason=str(request.data.get("reason", "")), user=request.user)
    except SeatError as e:
        return err(str(e))
    return Response(booking_out(booking_qs().get(pk=b.pk), detail=True))


# ---------------------------------------------------------------- settings

@api_view(["GET", "PUT"])
@permission_classes([IsAdminRole])
def platform_settings(request):
    if request.method == "PUT":
        ser = SettingsIn(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        PlatformSetting.put("fee_rate_pct", float(d["fee_rate"]), request.user)
        PlatformSetting.put("fee_min_inr", d["fee_min"], request.user)
        PlatformSetting.put("require_verified_operator", d["require_verified"], request.user)
        if "payout_mode" in d:
            PlatformSetting.put("payout_mode", d["payout_mode"], request.user)
    s = PlatformSetting.get_all()
    return Response({"fee_rate": s["fee_rate_pct"], "fee_min": s["fee_min_inr"], "require_verified": s["require_verified_operator"],
                     "payout_mode": s["payout_mode"],
                     "can_reset": settings.DEBUG})


@api_view(["POST"])
@permission_classes([IsAdminRole])
def reset_demo(request):
    if not settings.DEBUG:
        return err("Demo reset is only available in development.", 403)
    return Response({"detail": seed(reset=True)})
