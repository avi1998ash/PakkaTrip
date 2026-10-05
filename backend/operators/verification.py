"""Operator verification: tiers, phone OTP and document checks.

Tiers (the highest one met wins; GST is never mandatory):
  Gold    GST + PAN + bank + Udyam
  Silver  PAN + bank + Aadhaar
  Bronze  PAN + bank + phone OTP
PAN and bank are one check: the operator's bank details (which include the PAN) verified by an admin.
GST, Udyam and Aadhaar are OperatorDocuments an admin verifies. The phone is verified by OTP.
An admin can only approve an operator at Bronze or above. Anything that changes a check calls refresh_tier().
"""
import hashlib
import hmac
import io
import re
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import localtime
from PIL import Image, UnidentifiedImageError

from core.crypto import decrypt, decrypt_bytes, encrypt_bytes
from core.models import audit
from core import mailer
from core.mailer import MailError, send_otp_email
from core.sms import SmsError, can_show_code, otp_on, send_otp_sms

from .models import EmailOtp, Operator, OperatorBankAccount, OperatorDocument, PhoneOtp

Kind = OperatorDocument.Kind
TIER_RULES = [  # (tier, checks needed), best first
    (Operator.Tier.GOLD, {"pan_bank", "gst", "udyam"}),
    (Operator.Tier.SILVER, {"pan_bank", "aadhaar"}),
    (Operator.Tier.BRONZE, {"pan_bank", "phone"}),
]


class VerificationError(Exception):
    """Shown to the user as-is."""


# ---------------------------------------------------------------- tiers

def passed_checks(op):
    checks = set(OperatorDocument.objects.filter(operator=op, status=OperatorDocument.Status.VERIFIED).values_list("kind", flat=True))
    if OperatorBankAccount.objects.filter(operator=op, status=OperatorBankAccount.Status.VERIFIED).exists():
        checks.add("pan_bank")
    if op.phone_verified_at:
        checks.add("phone")
    return checks


def tier_for(checks):
    return next((tier for tier, needed in TIER_RULES if needed <= checks), Operator.Tier.NONE)


def refresh_tier(op):
    tier = tier_for(passed_checks(op))
    if op.tier != tier:
        Operator.objects.filter(pk=op.pk).update(tier=tier)
        op.tier = tier
    return tier


# ---------------------------------------------------------------- number formats

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14):
    total = 0
    for i, c in enumerate(first14):
        prod = B36.index(c) * (2 if i % 2 else 1)
        total += prod // 36 + prod % 36
    return B36[(36 - total % 36) % 36]


def clean_gstin(value):
    v = re.sub(r"\s", "", str(value or "")).upper()
    if not GSTIN_RE.match(v) or not (1 <= int(v[:2]) <= 38 or v[:2] in ("97", "99")):
        raise VerificationError("GSTIN is 15 characters, like 07ABCDE1234F1Z5.")
    if gstin_check_char(v[:14]) != v[14]:
        raise VerificationError("That GSTIN isn't valid. Please check it against your GST certificate.")
    return v


def clean_udyam(value):
    v = re.sub(r"\s", "", str(value or "")).upper()
    if not UDYAM_RE.match(v):
        raise VerificationError("Udyam number looks like UDYAM-DL-01-0012345.")
    return v


def clean_aadhaar_last4(value):
    v = re.sub(r"\s", "", str(value or ""))
    if re.fullmatch(r"\d{12}", v):   # never keep a full Aadhaar number, not even by accident
        raise VerificationError("Enter only the last 4 digits of the Aadhaar number, not the full number.")
    if not re.fullmatch(r"\d{4}", v):
        raise VerificationError("Enter the last 4 digits of the Aadhaar number.")
    return v


# ---------------------------------------------------------------- Aadhaar copy

MAX_DOC_BYTES = 5 * 1024 * 1024


def clean_document_file(f):
    """A masked Aadhaar copy → (bytes, content type). Photos are re-encoded, which also strips EXIF data."""
    if not f:
        raise VerificationError("Upload a copy of your masked Aadhaar.")
    if f.size > MAX_DOC_BYTES:
        raise VerificationError("The file is larger than 5 MB.")
    if f.read(5) == b"%PDF-":
        f.seek(0)
        return f.read(), "application/pdf"
    f.seek(0)
    try:
        img = Image.open(f)
        img.verify()
        f.seek(0)
        img = Image.open(f)
        if img.format not in {"JPEG", "PNG", "WEBP"}:
            raise VerificationError("Upload a JPG, PNG or PDF file.")
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise VerificationError("Upload a JPG, PNG or PDF file.")
    if min(img.size) < 200:
        raise VerificationError("The image is too small to read. Upload a clearer copy.")
    img = img.convert("RGB")
    img.thumbnail((2000, 2000))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue(), "image/jpeg"


def read_document_file(doc):
    """Decrypted bytes of a stored copy (admin viewing only)."""
    with doc.file.open("rb") as f:
        return decrypt_bytes(f.read())


# ---------------------------------------------------------------- documents

@transaction.atomic
def submit_document(op, kind, number, file=None, user=None):
    """Operator adds or replaces a document. It goes back to admin review either way."""
    if kind == Kind.GST:
        number = clean_gstin(number)
    elif kind == Kind.UDYAM:
        number = clean_udyam(number)
    elif kind == Kind.AADHAAR:
        number = clean_aadhaar_last4(number)
    else:
        raise VerificationError("Unknown document.")
    if kind != Kind.AADHAAR and OperatorDocument.objects.filter(kind=kind, number=number).exclude(operator=op).exists():
        raise VerificationError(f"This {Kind(kind).label} number is already registered by another operator.")
    doc = OperatorDocument.objects.select_for_update().filter(operator=op, kind=kind).first() or OperatorDocument(operator=op, kind=kind)
    if kind == Kind.AADHAAR:
        data, content_type = clean_document_file(file)
        if doc.file:
            doc.file.delete(save=False)
        doc.file.save(f"{uuid.uuid4().hex}.enc", ContentFile(encrypt_bytes(data)), save=False)
        doc.file_type = content_type
    doc.number, doc.status, doc.rejection_reason = number, OperatorDocument.Status.PENDING, ""
    doc.submitted_at, doc.verified_at, doc.verified_by = timezone.now(), None, None
    doc.save()
    refresh_tier(op)
    audit(user, "document.submitted", doc, kind=kind)
    return doc


def review_document(doc, approve, user, reason=""):
    reason = re.sub(r"\s+", " ", reason or "").strip()
    if approve:
        doc.status, doc.rejection_reason, doc.verified_at, doc.verified_by = OperatorDocument.Status.VERIFIED, "", timezone.now(), user
    else:
        if len(reason) < 5:
            raise VerificationError("Tell the operator what's wrong so they can fix it.")
        doc.status, doc.rejection_reason, doc.verified_at, doc.verified_by = OperatorDocument.Status.REJECTED, reason[:200], None, None
    doc.save()
    refresh_tier(doc.operator)
    audit(user, "document.verified" if approve else "document.rejected", doc, kind=doc.kind, reason=reason or None)
    return doc


# ---------------------------------------------------------------- phone OTP

OTP_RESEND_SECONDS = 30
OTP_MAX_PER_HOUR = 5
OTP_MAX_ATTEMPTS = 5


def _otp_hash(phone, purpose, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{phone}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


# (model, field holding the number/address, what to call it, where the code went) for each channel
CHANNELS = {"sms": (PhoneOtp, "phone", "number", "SMS"), "email": (EmailOtp, "email", "email address", "email")}


def _issue(channel, target, purpose):
    model, field, noun, _ = CHANNELS[channel]
    now = timezone.now()
    recent = model.objects.filter(**{field: target}, created_at__gte=now - timedelta(hours=1))
    last = recent.order_by("-created_at").first()
    if last and (now - last.created_at).total_seconds() < OTP_RESEND_SECONDS:
        wait = OTP_RESEND_SECONDS - int((now - last.created_at).total_seconds())
        raise VerificationError(f"Please wait {wait} seconds before asking for another code.")
    if recent.count() >= OTP_MAX_PER_HOUR:
        raise VerificationError(f"Too many codes requested for this {noun}. Try again in an hour.")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    model.objects.create(**{field: target}, purpose=purpose, code_hash=_otp_hash(target, purpose, code),
                         expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES))
    return code


def send_otp(phone, purpose):
    """Text a 6-digit code. Returns the code only in development without MSG91 keys, otherwise None."""
    code = _issue("sms", phone, purpose)
    try:
        send_otp_sms(phone, code)
    except SmsError as e:
        raise VerificationError(str(e))
    return code if can_show_code() else None


def send_email_otp(email, purpose):
    """Email a 6-digit code. Returns the code only in development without an SMTP login, otherwise None."""
    code = _issue("email", email, purpose)
    try:
        send_otp_email(email, code)
    except MailError as e:
        raise VerificationError(str(e))
    return code if mailer.can_show_code() else None


def check_otp(phone, purpose, code, channel="sms"):
    model, field, _, sent_by = CHANNELS[channel]
    # The error is raised only after the transaction commits, so a wrong try is always counted.
    with transaction.atomic():
        otp = (model.objects.select_for_update().filter(**{field: phone}, purpose=purpose, used_at__isnull=True, expires_at__gt=timezone.now())
               .order_by("-created_at").first())
        if not otp:
            problem = "That code has expired. Ask for a new one."
        elif otp.attempts >= OTP_MAX_ATTEMPTS:
            problem = "Too many wrong tries. Ask for a new code."
        elif not hmac.compare_digest(otp.code_hash, _otp_hash(phone, purpose, str(code or "").strip())):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            problem = f"That code is wrong. Check the {sent_by} and try again."
        else:
            otp.used_at = timezone.now()
            otp.save(update_fields=["used_at"])
            problem = None
    if problem:
        raise VerificationError(problem)


def mark_phone_verified(op, user=None):
    op.phone_verified_at = timezone.now()
    op.save(update_fields=["phone_verified_at", "updated_at"])
    refresh_tier(op)
    audit(user, "operator.phone_verified", op)


# ---------------------------------------------------------------- output

def _when(dt):
    return localtime(dt) if dt else None


def document_out(doc):
    if not doc:
        return None
    return {"number": f"XXXX XXXX {doc.number}" if doc.kind == Kind.AADHAAR else doc.number, "status": doc.status,
            "rejection_reason": doc.rejection_reason, "submitted_at": _when(doc.submitted_at), "verified_at": _when(doc.verified_at),
            "has_file": bool(doc.file)}


def verification_out(op, for_admin=False):
    docs = {d.kind: d for d in OperatorDocument.objects.filter(operator=op)}
    acct = OperatorBankAccount.objects.filter(operator=op).first()
    checks = passed_checks(op)
    out = {
        "operator_id": op.id, "name": op.business_name, "status": op.status, "rejection_reason": op.rejection_reason,
        "source": op.source, "tier": op.tier or None,
        "checks": {k: k in checks for k in ("pan_bank", "phone", "gst", "udyam", "aadhaar")},
        "phone": {"number": op.contact_phone, "verified": bool(op.phone_verified_at), "verified_at": _when(op.phone_verified_at)},
        "bank": {"status": acct.status, "account": acct.masked_account, "pan": f"XXXXXX{acct.pan_last4}", "bank_name": acct.bank_name,
                 "rejection_reason": acct.rejection_reason} if acct else None,
        "documents": {k: document_out(docs.get(k)) for k in Kind.values},
        "sms_otp": otp_on(),
    }
    if for_admin:
        gst = docs.get(Kind.GST)
        # Characters 3–12 of a GSTIN are the business's PAN, which should match the PAN on its bank details.
        out["gst_pan_match"] = (gst.number[2:12] == decrypt(acct.pan_enc)) if gst and acct else None
        out["owner"], out["email"], out["city"] = op.owner_name, op.contact_email, op.city.name
        out["applied"] = _when(op.created_at)
    return out
