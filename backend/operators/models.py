from django.conf import settings
from django.db import models
from django.utils import timezone


class Operator(models.Model):
    """A tour operator business that lists packages."""

    class Status(models.TextChoices):
        PENDING = "pending"          # shown as "Unverified"
        VERIFIED = "verified"        # green Bharosa badge
        SUSPENDED = "suspended"
        REJECTED = "rejected"

    business_name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    owner_name = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=15)
    contact_email = models.EmailField()
    city = models.ForeignKey("catalog.City", on_delete=models.PROTECT, related_name="operators")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    trips_run_offline = models.PositiveIntegerField(default=0)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operators"
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(commission_rate__gte=0, commission_rate__lte=100), name="commission_0_100")]

    @property
    def is_verified(self):
        return self.status == self.Status.VERIFIED

    @property
    def owner(self):
        m = self.members.select_related("user").filter(member_role=OperatorMember.Role.OWNER).first()
        return m.user if m else None

    def __str__(self):
        return self.business_name


class OperatorMember(models.Model):
    """Links a login (user) to the operator it works for."""

    class Role(models.TextChoices):
        OWNER = "owner"
        MANAGER = "manager"
        STAFF = "staff"

    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="members")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="operator_membership")
    member_role = models.CharField(max_length=10, choices=Role.choices, default=Role.STAFF)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "operator_members"
