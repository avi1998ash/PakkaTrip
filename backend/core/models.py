from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models

DEFAULT_SETTINGS = {
    "fee_rate_pct": 2.5,            # convenience fee charged to travellers on online bookings
    "fee_min_inr": 49,
    "require_verified_operator": True,
}


class PlatformSetting(models.Model):
    """Admin-editable settings stored as key/value."""
    key = models.CharField(max_length=60, primary_key=True)
    value = models.JSONField()
    description = models.TextField(blank=True, default="")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_settings"

    @classmethod
    def get_all(cls):
        stored = dict(cls.objects.values_list("key", "value"))
        return {k: stored.get(k, v) for k, v in DEFAULT_SETTINGS.items()}

    @classmethod
    def put(cls, key, value, user=None):
        cls.objects.update_or_create(key=key, defaults={"value": value, "updated_by": user})


def fee_for(amount, conf=None):
    """Convenience fee in whole rupees: rate% of the amount, never below the minimum."""
    conf = conf or PlatformSetting.get_all()
    rate = Decimal(str(conf["fee_rate_pct"]))
    fee = (Decimal(amount) * rate / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(Decimal(str(conf["fee_min_inr"])), fee)


class CancellationRule(models.Model):
    """Customer cancellation refund policy (% of package amount by days before departure)."""
    min_days_before = models.PositiveSmallIntegerField()
    refund_pct = models.DecimalField(max_digits=5, decimal_places=2)
    label = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField()

    class Meta:
        db_table = "cancellation_rules"
        ordering = ["-min_days_before"]
        constraints = [
            models.UniqueConstraint(fields=["min_days_before", "effective_from"], name="uniq_rule_per_day"),
            models.CheckConstraint(condition=models.Q(refund_pct__gte=0, refund_pct__lte=100), name="refund_pct_0_100"),
        ]


class AuditLog(models.Model):
    """Append-only record of who changed what."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=60)
    entity_type = models.CharField(max_length=40)
    entity_id = models.BigIntegerField()
    changes = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        indexes = [models.Index(fields=["entity_type", "entity_id"])]


def audit(user, action, obj, **changes):
    AuditLog.objects.create(actor=user if user and user.is_authenticated else None, action=action,
                            entity_type=obj._meta.db_table, entity_id=obj.pk, changes=changes or None)
