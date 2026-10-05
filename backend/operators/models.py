from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone


def private_storage():
    """Identity documents live outside MEDIA_ROOT, so they are never served at a public URL."""
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


class Operator(models.Model):
    """A tour operator business that lists packages."""

    class Status(models.TextChoices):
        PENDING = "pending"          # application waiting for admin review; packages stay hidden
        VERIFIED = "verified"        # approved by an admin: packages can go live
        SUSPENDED = "suspended"
        REJECTED = "rejected"        # application sent back with a reason; the operator can fix and resubmit

    class Source(models.TextChoices):
        ADMIN = "admin"              # added by a PakkaTrip admin
        SIGNUP = "signup"            # applied through /partner/signup

    class Tier(models.TextChoices):
        """Verification level shown to travellers. Kept up to date by operators.verification.refresh_tier."""
        NONE = "", "None"
        BRONZE = "bronze", "Bronze"  # PAN + bank + phone OTP
        SILVER = "silver", "Silver"  # PAN + bank + Aadhaar
        GOLD = "gold", "Gold"        # GST + PAN + bank + Udyam

    business_name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    owner_name = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=15)
    contact_email = models.EmailField()
    city = models.ForeignKey("catalog.City", on_delete=models.PROTECT, related_name="operators")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    rejection_reason = models.CharField(max_length=200, blank=True, default="")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.ADMIN)
    phone_verified_at = models.DateTimeField(null=True, blank=True)   # contact_phone confirmed by OTP
    tier = models.CharField(max_length=10, choices=Tier.choices, default=Tier.NONE, blank=True, db_index=True)
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



class OperatorDocument(models.Model):
    """A verification document an operator submits and an admin checks: GST, Udyam (MSME) or Aadhaar.

    PAN and bank account are checked together on OperatorBankAccount. For Aadhaar only the last 4 digits
    are kept, plus a masked copy (first 8 digits hidden) that is encrypted before it is written to disk.
    The full Aadhaar number is never asked for or stored.
    """

    class Kind(models.TextChoices):
        GST = "gst", "GST"
        UDYAM = "udyam", "Udyam"
        AADHAAR = "aadhaar", "Aadhaar"

    class Status(models.TextChoices):
        PENDING = "pending"
        VERIFIED = "verified"
        REJECTED = "rejected"

    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    number = models.CharField(max_length=20)            # GSTIN, Udyam number, or the last 4 Aadhaar digits
    file = models.FileField(upload_to="operator-docs/", storage=private_storage, blank=True)   # Fernet-encrypted bytes
    file_type = models.CharField(max_length=40, blank=True, default="")                      # content type before encryption
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    rejection_reason = models.CharField(max_length=200, blank=True, default="")
    submitted_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "operator_documents"
        constraints = [models.UniqueConstraint(fields=["operator", "kind"], name="one_document_per_kind")]


class PhoneOtp(models.Model):
    """A one-time code sent by SMS. Only a hash of the code is stored."""

    class Purpose(models.TextChoices):
        PARTNER_SIGNUP = "partner_signup"
        OPERATOR_PHONE = "operator_phone"

    phone = models.CharField(max_length=15, db_index=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "phone_otps"
