from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Departure(models.Model):
    """One dated run of a package with its own seat count — the core of seat inventory.

    booked_seats = confirmed + completed seats; held_seats = seats on hold for pending bookings.
    Both counters change only inside a transaction that locks this row (see inventory/services.py),
    and the CHECK constraint below makes the database itself refuse an overbooking.
    """

    class Status(models.TextChoices):
        OPEN = "open"
        BLOCKED = "blocked"
        CANCELLED = "cancelled"

    package = models.ForeignKey("catalog.Package", on_delete=models.PROTECT, related_name="departures")
    departure_date = models.DateField()
    total_seats = models.PositiveSmallIntegerField()
    booked_seats = models.PositiveSmallIntegerField(default=0)
    held_seats = models.PositiveSmallIntegerField(default=0)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    blocked_reason = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "departures"
        ordering = ["departure_date"]
        indexes = [models.Index(fields=["departure_date", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["package", "departure_date"], name="one_departure_per_day"),
            models.CheckConstraint(condition=Q(total_seats__gte=1, total_seats__lte=80), name="total_seats_1_80"),
            models.CheckConstraint(condition=Q(booked_seats__lte=F("total_seats") - F("held_seats")), name="no_overbooking"),
        ]

    @property
    def available_seats(self):
        return max(0, self.total_seats - self.booked_seats - self.held_seats)

    def __str__(self):
        return f"{self.package} · {self.departure_date}"
