"""Input validation (DRF serializers) and output shaping (plain functions) for the portal API."""
import re

from django.db import transaction
from django.utils.timezone import localtime
from rest_framework import serializers

from accounts.models import User
from bookings.models import Booking
from bookings.services import seat_stats
from catalog.models import City, Package, unique_slug
from operators.models import Operator, OperatorMember

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
ADMIN_EMAIL = "admin@pakkatrip.com"

# Booking status names the UI uses (same as the prototype)
UI_STATUS = {"pending_confirmation": "pending", "pending_payment": "pending", "confirmed": "confirmed",
             "completed": "completed", "cancelled": "cancelled", "expired": "cancelled"}
API_STATUS = {"pending": ["pending_confirmation", "pending_payment"], "confirmed": ["confirmed"],
              "completed": ["completed"], "cancelled": ["cancelled", "expired"]}
UI_PKG_STATUS = {"pending_review": "pending", "draft": "pending", "approved": "approved", "rejected": "rejected", "unlisted": "pending"}


def validate_phone(value):
    if not PHONE_RE.match(value or ""):
        raise serializers.ValidationError("Enter a 10-digit Indian mobile number.")
    return value


# ---------------------------------------------------------------- output

def operator_out(op):
    owner = op.owner
    return {
        "id": op.id, "name": op.business_name, "owner": op.owner_name, "city": op.city.name, "phone": op.contact_phone,
        "email": owner.email if owner else op.contact_email, "verified": op.is_verified, "status": op.status,
        "joined": localtime(op.created_at).date(), "packages": getattr(op, "n_packages", None),
        "rating": float(op.rating_avg), "reviews": op.rating_count,
    }


def package_out(p):
    imgs = list(p.images.all())   # prefetched
    cover = next((i for i in imgs if i.is_cover), imgs[0] if imgs else None)
    return {
        "cover_url": cover.image.url if cover else None, "image_count": len(imgs),
        "id": p.id, "title": p.title, "operator_id": p.operator_id, "operator_name": p.operator.business_name,
        "operator_verified": p.operator.is_verified, "from_city": p.from_city.name, "to_city": p.to_city.name,
        "nights": p.nights, "price": p.price_per_person, "default_seats": p.default_seats,
        "status": UI_PKG_STATUS[p.status], "raw_status": p.status, "upcoming_departures": getattr(p, "n_upcoming", None),
        "rating": float(p.rating_avg), "reviews": p.rating_count,
    }


def package_detail_out(p):
    from catalog.media import facilities_out, images_out, itinerary_out
    return {**package_out(p), "images": images_out(p), "facilities": facilities_out(p), "itinerary": itinerary_out(p),
            "pickup_point": p.pickup_point,
            "rejection_reason": p.rejection_reason, "operator_city": p.operator.city.name}


def booking_out(b, detail=False):
    refund = sum((r.amount for r in b.refunds.all()), start=0) if b.status == Booking.Status.CANCELLED else None
    out = {
        "id": b.booking_code, "customer": b.lead_name, "phone": b.lead_phone, "email": b.lead_email,
        "package_id": b.package_id, "pkg_title": b.package.title, "route": f"{b.package.from_city.name} → {b.package.to_city.name}",
        "operator_name": b.operator.business_name, "travellers": b.seats, "travel_date": b.departure.departure_date,
        "booked_on": localtime(b.created_at).date(), "amount": b.base_amount, "fee": b.convenience_fee, "total": b.total_amount,
        "status": UI_STATUS[b.status], "source": b.source,
        "cancelled_on": localtime(b.cancelled_at).date() if b.cancelled_at else None, "cancelled_by": b.cancelled_by, "refund": refund,
    }
    if detail:
        pay = next(iter(b.payments.all()), None)
        out["payment"] = f"{pay.get_method_display()} · {pay.method_detail}".strip(" ·") if pay else None
        out["co_travellers"] = [t.full_name for t in b.travellers.all() if not t.is_lead]
    return out


def booking_qs():
    return (Booking.objects.select_related("package__from_city", "package__to_city", "operator", "departure")
            .prefetch_related("refunds", "payments", "travellers"))


def departure_out(d):
    return {"id": d.id, "package_id": d.package_id, "package_title": d.package.title, "date": d.departure_date,
            "blocked": d.status != "open", **seat_stats(d)}


def review_out(r):
    return {"id": r.id, "booking_id": r.booking.booking_code, "customer": r.reviewer_name, "rating": r.rating, "text": r.comment,
            "date": localtime(r.created_at).date(), "reply": r.operator_reply, "package_title": r.package.title}


# ---------------------------------------------------------------- input

class OperatorIn(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    owner = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=80)
    phone = serializers.CharField(validators=[validate_phone])
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, max_length=40, required=False, allow_blank=True)
    verified = serializers.BooleanField(default=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if value == ADMIN_EMAIL:
            raise serializers.ValidationError("That email belongs to the admin account.")
        owner = self.instance.owner if self.instance else None
        if User.objects.filter(email=value).exclude(pk=owner.pk if owner else None).exists():
            raise serializers.ValidationError("Another account already uses this email.")
        return value

    def validate(self, data):
        if not self.instance and not data.get("password"):
            raise serializers.ValidationError({"password": "Set a login password for the new operator."})
        return data

    @transaction.atomic
    def create(self, data):
        user = User.objects.create_user(data["email"], data["password"], full_name=data["owner"], role=User.Role.OPERATOR)
        op = Operator.objects.create(
            business_name=data["name"], slug=unique_slug(Operator, data["name"]), owner_name=data["owner"],
            contact_phone=data["phone"], contact_email=data["email"], city=City.by_name(data["city"]),
            status=Operator.Status.VERIFIED if data["verified"] else Operator.Status.PENDING)
        OperatorMember.objects.create(operator=op, user=user, member_role=OperatorMember.Role.OWNER)
        return op

    @transaction.atomic
    def update(self, op, data):
        op.business_name, op.owner_name, op.contact_phone, op.contact_email = data["name"], data["owner"], data["phone"], data["email"]
        op.city = City.by_name(data["city"])
        if data["verified"] != op.is_verified:
            op.status = Operator.Status.VERIFIED if data["verified"] else Operator.Status.PENDING
        op.save()
        owner = op.owner
        if owner:
            owner.email, owner.full_name = data["email"], data["owner"]
            if data.get("password"):
                owner.set_password(data["password"])
            owner.save()
        return op


class PackageIn(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    operator_id = serializers.IntegerField(required=False)
    from_city = serializers.CharField(max_length=80)
    to_city = serializers.CharField(max_length=80)
    nights = serializers.IntegerField(min_value=0, max_value=15)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1)
    default_seats = serializers.IntegerField(min_value=1, max_value=80)
    pickup_point = serializers.CharField(max_length=160, required=False, allow_blank=True)

    def apply(self, pkg, operator):
        d = self.validated_data
        if "pickup_point" in d:
            pkg.pickup_point = d["pickup_point"].strip()
        pkg.title, pkg.nights, pkg.price_per_person, pkg.default_seats = d["title"].strip(), d["nights"], d["price"], d["default_seats"]
        pkg.from_city, pkg.to_city = City.by_name(d["from_city"]), City.by_name(d["to_city"])
        pkg.operator = operator
        if not pkg.slug:
            pkg.slug = unique_slug(Package, pkg.title)
        pkg.save()
        return pkg


class DepartureIn(serializers.Serializer):
    package_id = serializers.IntegerField()
    date = serializers.DateField()
    total_seats = serializers.IntegerField(min_value=1, max_value=80)


class OfflineBookingIn(serializers.Serializer):
    customer = serializers.CharField(max_length=50)
    phone = serializers.CharField(validators=[validate_phone])
    travellers = serializers.IntegerField(min_value=1, max_value=80)
    status = serializers.ChoiceField(choices=["confirmed", "pending"])


class SettingsIn(serializers.Serializer):
    fee_rate = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0, max_value=20)
    fee_min = serializers.IntegerField(min_value=0, max_value=999)
    require_verified = serializers.BooleanField()
