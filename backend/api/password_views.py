"""Forgot / reset password — /api/public/auth/password/…  (travellers, operators and admins alike)

The emailed link carries Django's password-reset token: nothing is stored, it expires after
PASSWORD_RESET_TIMEOUT, and it stops working once the password changes (so each link works once).
"""
import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from accounts.models import User
from core import mailer
from core.models import audit

from .public_views import PUBLIC, SensitiveThrottle, err

log = logging.getLogger(__name__)

SENT = "If an account exists for that email, we've sent a link to reset the password. Check your inbox (and spam folder)."
RESEND_SECONDS = 60   # at most one reset email per address per minute


def min_length(user):
    return 6 if user.role == User.Role.TRAVELLER else 8   # same rules as signup


def reset_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f"{settings.SITE_URL}/reset-password?uid={uid}&token={default_token_generator.make_token(user)}"


def send_reset_email(user, link):
    brand = settings.SITE_INFO["brand"]
    hours = settings.PASSWORD_RESET_TIMEOUT // 3600
    text = (f"Hi {user.full_name.split()[0] if user.full_name else 'there'},\n\n"
            f"Someone (hopefully you) asked to reset the password for your {brand} account ({user.email}).\n\n"
            f"Set a new password here:\n{link}\n\n"
            f"The link works once and expires in {hours} hour{'' if hours == 1 else 's'}. If you didn't ask for this, ignore this email; "
            f"your password stays the same.\n\n"
            f"— {brand} ({settings.SITE_INFO['domain']})")
    mailer.send_email(user.email, f"Reset your {brand} password", text)


@api_view(["POST"])
@permission_classes(PUBLIC)
@throttle_classes([SensitiveThrottle])
def forgot(request):
    """Always the same answer, so the form can't be used to find out who has an account."""
    email = str(request.data.get("email", "")).strip().lower()
    if "@" not in email or len(email) > 254:
        return err("Enter the email address you log in with.")
    if not mailer.enabled() and not settings.DEBUG:
        return err(f"Email sending isn't set up on this server yet. Please contact {settings.SITE_INFO['brand']} support.", 503)
    out = {"detail": SENT}
    user = User.objects.filter(email=email, is_active=True).first()
    if user and cache.add(f"pwreset:{email}", 1, RESEND_SECONDS):
        link = reset_link(user)
        try:
            send_reset_email(user, link)
        except mailer.MailError as e:
            log.warning("Password reset email to %s not sent: %s", email, e)
        if mailer.can_show_code():   # development without SMTP: no email goes out, so show the link
            out["dev_link"] = link
    return Response(out)


@api_view(["POST"])
@permission_classes(PUBLIC)
@throttle_classes([SensitiveThrottle])
def reset(request):
    try:
        pk = force_str(urlsafe_base64_decode(str(request.data.get("uid", ""))))
        user = User.objects.get(pk=pk, is_active=True)
    except (ValueError, TypeError, OverflowError, User.DoesNotExist):
        user = None
    if not user or not default_token_generator.check_token(user, str(request.data.get("token", ""))):
        return err("This reset link is invalid or has expired. Ask for a new one.")
    password = str(request.data.get("password", ""))
    n = min_length(user)
    if not n <= len(password) <= 64:
        return err(f"Use {n} to 64 characters for the password.")
    user.set_password(password)
    user.save(update_fields=["password", "updated_at"])
    audit(user, "user.password_reset", user)
    return Response({"ok": True, "role": user.role, "email": user.email})
