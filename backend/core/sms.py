"""SMS one-time codes through MSG91, using only the standard library.

Settings (backend/.env): MSG91_AUTH_KEY and MSG91_OTP_TEMPLATE_ID — a DLT-approved OTP template set up in
the MSG91 dashboard. We generate the code ourselves (only its hash is stored) and pass it to MSG91's
Send OTP API, which puts it into the template.

Without MSG91_AUTH_KEY: development (DEBUG on) prints the code to the server log and shows it on screen;
with DEBUG off nothing can be sent.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)
OTP_API = "https://control.msg91.com/api/v5/otp"


class SmsError(Exception):
    """Shown to the user as-is."""


def enabled():
    return bool(settings.MSG91_AUTH_KEY and settings.MSG91_OTP_TEMPLATE_ID)


def otp_on():
    """The admin switch (Admin → Settings). While off, nobody is asked for an SMS code."""
    from core.models import PlatformSetting
    return bool(PlatformSetting.get_all()["sms_otp_enabled"])


def can_show_code():
    """In development with no MSG91 keys, the code is returned to the browser, since no SMS goes out."""
    return not enabled() and settings.DEBUG


def send_otp_sms(phone, code):
    """phone: 10-digit Indian mobile number."""
    if not enabled():
        if not settings.DEBUG:
            raise SmsError("SMS sending isn't set up on this server yet. Please contact PakkaTrip support.")
        log.warning("MSG91 not configured; OTP for %s is %s", phone, code)
        return
    query = urllib.parse.urlencode({
        "template_id": settings.MSG91_OTP_TEMPLATE_ID, "mobile": f"91{phone}", "otp": code,
        "otp_length": len(code), "otp_expiry": settings.OTP_TTL_MINUTES,
    })
    req = urllib.request.Request(f"{OTP_API}?{query}", method="POST", data=json.dumps({"OTP": code}).encode(),
                                 headers={"authkey": settings.MSG91_AUTH_KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        log.error("MSG91 HTTP %s for %s", e.code, phone)
        raise SmsError("We couldn't send the SMS. Please try again in a minute.") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        log.error("MSG91 unreachable: %s", e)
        raise SmsError("We couldn't send the SMS. Please try again in a minute.") from e
    if res.get("type") != "success":
        log.error("MSG91 refused OTP for %s: %s", phone, res.get("message"))
        raise SmsError("We couldn't send the SMS. Please check the number and try again.")
