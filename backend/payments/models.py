from django.conf import settings
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
        UPI = "upi", "UPI"
        CARD = "card", "Card"
        NETBANKING = "netbanking", "Netbanking"
        WALLET = "wallet", "Wallet"
        EMI = "emi", "EMI"
        PAYLATER = "paylater", "Pay later"
        CASH = "cash", "Cash"

    booking = models.ForeignKey("bookings.Booking", on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=20, default="razorpay")
    gateway_order_id = models.CharField(max_length=64, unique=True)
    gateway_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    gateway_signature = models.CharField(max_length=255, blank=True, default="")
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
    gateway_refund_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    failure_reason = models.CharField(max_length=200, blank=True, default="")
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


class Transfer(models.Model):
    """Razorpay Route: the operator's share of one paid booking, sent to their linked account.

    Created on hold when the payment is captured, released when the trip completes, and reversed
    (fully or partly) before a refund if the booking is cancelled.
    """

    class Status(models.TextChoices):
        ON_HOLD = "on_hold"
        RELEASED = "released"
        REVERSED = "reversed"
        PARTIALLY_REVERSED = "partially_reversed"
        FAILED = "failed"

    booking = models.OneToOneField("bookings.Booking", on_delete=models.PROTECT, related_name="transfer")
    operator = models.ForeignKey("operators.Operator", on_delete=models.PROTECT, related_name="transfers")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="transfers")
    gateway_transfer_id = models.CharField(max_length=40, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reversed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ON_HOLD)
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "transfers"


class Payout(models.Model):
    """RazorpayX: one bank transfer to an operator covering several bookings (Booking.payout)."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        PENDING = "pending"
        PROCESSING = "processing"
        PROCESSED = "processed"
        REVERSED = "reversed"
        FAILED = "failed"
        CANCELLED = "cancelled"
        REJECTED = "rejected"

    FINAL_FAILED = (Status.REVERSED, Status.FAILED, Status.CANCELLED, Status.REJECTED)

    operator = models.ForeignKey("operators.Operator", on_delete=models.PROTECT, related_name="payouts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    account_last4 = models.CharField(max_length=4)
    gateway_payout_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    mode = models.CharField(max_length=10, default="IMPS")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    utr = models.CharField(max_length=40, blank=True, default="")
    failure_reason = models.CharField(max_length=200, blank=True, default="")
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payouts"
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="payout_amount_positive")]
