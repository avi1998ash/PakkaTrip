from django.conf import settings
from django.db import connection, models
from django.db.models import F, Q
from django.utils import timezone


def next_booking_code():
    """PT24001, PT24002, … from a PostgreSQL sequence (created in migration 0002)."""
    with connection.cursor() as cur:
        cur.execute("SELECT nextval('booking_code_seq')")
        return f"PT{cur.fetchone()[0]}"


class Booking(models.Model):
    """One purchase of seats on one departure."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment"
        PENDING_CONFIRMATION = "pending_confirmation"   # seats on hold, awaiting operator/payment
        CONFIRMED = "confirmed"
        COMPLETED = "completed"
        CANCELLED = "cancelled"
        EXPIRED = "expired"

    class Source(models.TextChoices):
        ONLINE = "online"
        OFFLINE = "offline"

    class Actor(models.TextChoices):
        CUSTOMER = "customer"
        OPERATOR = "operator"
        ADMIN = "admin"
        SYSTEM = "system"

    booking_code = models.CharField(max_length=12, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    departure = models.ForeignKey("inventory.Departure", on_delete=models.PROTECT, related_name="bookings")
    package = models.ForeignKey("catalog.Package", on_delete=models.PROTECT, related_name="bookings")
    operator = models.ForeignKey("operators.Operator", on_delete=models.PROTECT, related_name="bookings")
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.ONLINE)
    lead_name = models.CharField(max_length=100)
    lead_phone = models.CharField(max_length=15, db_index=True)
    lead_email = models.EmailField(blank=True, default="")
    seats = models.PositiveSmallIntegerField()
    price_per_person = models.DecimalField(max_digits=10, decimal_places=2)    # snapshot at booking time
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)         # goes to the operator
    fee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # snapshot of fee %
    convenience_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=22, choices=Status.choices, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=10, choices=Actor.choices, blank=True, default="")
    cancellation_reason = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    # Secret for guests (no account) to open their own ticket: /ticket/<code>?key=<guest_token>
    guest_token = models.CharField(max_length=43, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)   # "booked on"
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["operator", "-created_at"]),
            models.Index(fields=["departure", "status"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(seats__gte=1, seats__lte=80), name="booking_seats_range"),
            models.CheckConstraint(condition=Q(total_amount=F("base_amount") + F("convenience_fee")), name="total_is_base_plus_fee"),
        ]

    @property
    def travel_date(self):
        return self.departure.departure_date

    def __str__(self):
        return self.booking_code


class BookingTraveller(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="travellers")
    full_name = models.CharField(max_length=100)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True, default="")
    is_lead = models.BooleanField(default=False)

    class Meta:
        db_table = "booking_travellers"
        constraints = [models.UniqueConstraint(fields=["booking"], condition=Q(is_lead=True), name="one_lead_per_booking")]
