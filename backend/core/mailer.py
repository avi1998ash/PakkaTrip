"""Email over SMTP (Gmail at launch): one-time codes, password-reset links and booking confirmations.

Settings (backend/.env): EMAIL_HOST_USER and EMAIL_HOST_PASSWORD (a Gmail App Password, not the account password),
plus EMAIL_HOST / EMAIL_PORT / EMAIL_USE_TLS. Gmail allows about 500 emails a day from a personal account.

Without EMAIL_HOST_USER: development (DEBUG on) prints the email to the server log and shows the code on screen;
with DEBUG off nothing can be sent.
"""
import logging
import smtplib

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail

log = logging.getLogger(__name__)


class MailError(Exception):
    """Shown to the user as-is."""


def enabled():
    return bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)


def otp_on():
    """The admin switch (Admin → Settings). While off, nobody is asked for an email code."""
    from core.models import PlatformSetting
    return bool(PlatformSetting.get_all()["email_otp_enabled"])


def can_show_code():
    """In development with no SMTP login, the code is returned to the browser, since no email goes out."""
    return not enabled() and settings.DEBUG


def send_otp_email(email, code):
    brand = settings.SITE_INFO["brand"]
    if not enabled() and not settings.DEBUG:
        raise MailError(f"Email sending isn't set up on this server yet. Please contact {brand} support.")
    minutes = settings.OTP_TTL_MINUTES
    body = (f"Your {brand} verification code is {code}.\n\n"
            f"It expires in {minutes} minutes. If you didn't ask for it, ignore this email; nobody can use it without access to your inbox.\n\n"
            f"— {brand} ({settings.SITE_INFO['domain']})")
    try:
        send_mail(f"{code} is your {brand} verification code", body, settings.DEFAULT_FROM_EMAIL, [email])
    except (smtplib.SMTPException, OSError) as e:
        log.error("Email OTP to %s failed: %s", email, e)
        raise MailError("We couldn't send the email. Check the address and try again in a minute.") from e


def send_email(to, subject, text, html=None):
    """One email (plain text, plus an HTML version if given). Raises MailError if it can't be sent."""
    if not enabled() and not settings.DEBUG:
        raise MailError(f"Email sending isn't set up on this server yet. Please contact {settings.SITE_INFO['brand']} support.")
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
    if html:
        msg.attach_alternative(html, "text/html")
    try:
        msg.send()
    except (smtplib.SMTPException, OSError) as e:
        log.error("Email '%s' to %s failed: %s", subject, to, e)
        raise MailError("We couldn't send the email. Check the address and try again in a minute.") from e
