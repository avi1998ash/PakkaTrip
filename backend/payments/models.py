from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """A payment attempt with the gateway. Status changes only from verified gateway webhooks."""

    class Status(models.TextChoices):
        CREATED = "created"
        AUTHORIZED = "authorized"
        CAPTURED = "captured"
        FAILED = "failed"
        REFUNDED = "refunded"
        PARTIALLY_REFUNDED = "partially_refunded"

    class Method(models.TextChoices):
        UPI = "upi"
        CARD = "card"
        NETBANKING = "netbanking"
        WALLET = "wallet"
        CASH = "cash"

    booking = models.ForeignKey("bookings.Booking", on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=20, default="razorpay")
    gateway_order_id = models.CharField(max_length=64, unique=True)
    gateway_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    method = models.CharField(max_length=12, choices=Method.choices, blank=True, default="")
    method_detail = models.CharField(max_length=60, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive")]


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        PROCESSED = "processed"
        FAILED = "failed"

    booking = models.ForeignKey("bookings.Booking", on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    refund_pct = models.DecimalField(max_digits=5, decimal_places=2)
    fee_refunded = models.BooleanField(default=False)
    initiated_by = models.CharField(max_length=10)
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "refunds"
        constraints = [models.CheckConstraint(condition=models.Q(amount__gte=0), name="refund_amount_non_negative")]
