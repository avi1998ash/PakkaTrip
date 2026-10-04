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


class OperatorBankAccount(models.Model):
    """Where an operator gets paid. The account number and PAN are stored encrypted (core.crypto)."""

    class Status(models.TextChoices):
        PENDING = "pending"        # entered or changed by the operator; payouts paused until an admin verifies
        VERIFIED = "verified"      # Razorpay objects created; payouts allowed
        REJECTED = "rejected"

    class AccountType(models.TextChoices):
        SAVINGS = "savings", "Savings"
        CURRENT = "current", "Current"

    class BusinessType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        PROPRIETORSHIP = "proprietorship", "Proprietorship"
        PARTNERSHIP = "partnership", "Partnership"
        LLP = "llp", "LLP"
        PRIVATE_LIMITED = "private_limited", "Private limited"

    operator = models.OneToOneField(Operator, on_delete=models.CASCADE, related_name="bank_account")
    holder_name = models.CharField(max_length=100)
    account_number_enc = models.TextField()
    account_last4 = models.CharField(max_length=4)
    ifsc = models.CharField(max_length=11)
    bank_name = models.CharField(max_length=100, blank=True, default="")
    branch = models.CharField(max_length=120, blank=True, default="")
    account_type = models.CharField(max_length=10, choices=AccountType.choices, default=AccountType.CURRENT)
    pan_enc = models.TextField()
    pan_last4 = models.CharField(max_length=4)
    business_type = models.CharField(max_length=20, choices=BusinessType.choices, default=BusinessType.PROPRIETORSHIP)
    address_line = models.CharField(max_length=200)
    address_city = models.CharField(max_length=60)
    address_state = models.CharField(max_length=60)
    pincode = models.CharField(max_length=6)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    rejection_reason = models.CharField(max_length=200, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # RazorpayX (payouts)
    razorpayx_contact_id = models.CharField(max_length=40, blank=True, default="")
    razorpayx_fund_account_id = models.CharField(max_length=40, blank=True, default="")
    # Razorpay Route (linked account)
    route_account_id = models.CharField(max_length=40, blank=True, default="")
    route_product_id = models.CharField(max_length=40, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operator_bank_accounts"

    @property
    def masked_account(self):
        return f"XXXX XXXX {self.account_last4}"

