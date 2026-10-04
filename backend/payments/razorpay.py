"""Minimal Razorpay client (Orders, Payments, Refunds) using only the standard library.

Keys come from settings (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET in backend/.env). Amounts sent to
Razorpay are in paise. Signatures are HMAC-SHA256 as documented by Razorpay:
  checkout:  hmac(key_secret, "<order_id>|<payment_id>")
  webhook:   hmac(webhook_secret, raw request body)
"""
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings

API = "https://api.razorpay.com"
IFSC_API = "https://ifsc.razorpay.com"


class GatewayError(Exception):
    """Razorpay rejected the request or couldn't be reached; the message is safe to show.

    `retryable` is True when the outcome is unknown (network error, timeout, 5xx) — retry with the same
    idempotency key; False when Razorpay definitely refused the request.
    """

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def enabled():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def to_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def _call(method, path, body=None, headers=None, version="v1"):
    if not enabled():
        raise GatewayError("Online payments are not configured.")
    auth = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    req = urllib.request.Request(f"{API}/{version}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("error", {}).get("description")
        except ValueError:
            detail = None
        raise GatewayError(detail or f"Payment gateway error ({e.code}).", retryable=e.code >= 500) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GatewayError("Couldn't reach the payment gateway. Please try again.", retryable=True) from e


def create_order(amount, receipt, notes=None):
    return _call("POST", "/orders", {"amount": to_paise(amount), "currency": "INR", "receipt": receipt, "notes": notes or {}})


def fetch_payment(payment_id):
    return _call("GET", f"/payments/{payment_id}")


def capture_payment(payment_id, amount):
    return _call("POST", f"/payments/{payment_id}/capture", {"amount": to_paise(amount), "currency": "INR"})


def refund_payment(payment_id, amount, notes=None):
    return _call("POST", f"/payments/{payment_id}/refund", {"amount": to_paise(amount), "speed": "normal", "notes": notes or {}})


# ---------------------------------------------------------------- bank lookup (public, no keys)

def ifsc_lookup(ifsc):
    """Bank and branch for an IFSC from Razorpay's public IFSC API; None if the code doesn't exist."""
    try:
        with urllib.request.urlopen(f"{IFSC_API}/{urllib.request.quote(ifsc)}", timeout=10) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise GatewayError("Couldn't check the IFSC code right now. Please try again.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GatewayError("Couldn't check the IFSC code right now. Please try again.") from e
    return {"bank": d.get("BANK", ""), "branch": d.get("BRANCH", ""), "city": d.get("CITY", ""), "imps": bool(d.get("IMPS")),
            "neft": bool(d.get("NEFT"))}


# ---------------------------------------------------------------- RazorpayX (payouts)

def create_contact(name, email, phone, reference_id):
    return _call("POST", "/contacts", {"name": name, "email": email, "contact": phone, "type": "vendor", "reference_id": reference_id})


def create_fund_account(contact_id, holder_name, ifsc, account_number):
    return _call("POST", "/fund_accounts", {"contact_id": contact_id, "account_type": "bank_account",
                                            "bank_account": {"name": holder_name, "ifsc": ifsc, "account_number": account_number}})


def create_payout(fund_account_id, amount, reference_id, idempotency_key, narration="PakkaTrip payout"):
    if not settings.RAZORPAYX_ACCOUNT_NUMBER:
        raise GatewayError("RazorpayX account number isn't set (RAZORPAYX_ACCOUNT_NUMBER in backend/.env).")
    return _call("POST", "/payouts", {
        "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER, "fund_account_id": fund_account_id, "amount": to_paise(amount),
        "currency": "INR", "mode": settings.RAZORPAYX_PAYOUT_MODE, "purpose": "payout", "queue_if_low_balance": True,
        "reference_id": reference_id, "narration": narration[:30],
    }, headers={"X-Payout-Idempotency": idempotency_key})


def fetch_payout(payout_id):
    return _call("GET", f"/payouts/{payout_id}")


# ---------------------------------------------------------------- Route (automatic split)
# Route must be enabled on the Razorpay account. Field names follow Razorpay's Route v2 (linked accounts) API;
# re-check the business category values against Razorpay's docs when Route is switched on.
ROUTE_CATEGORY, ROUTE_SUBCATEGORY = "tours_and_travel", "travel_agency"


def create_linked_account(*, email, phone, business_name, business_type, contact_name, reference_id, address):
    return _call("POST", "/accounts", {
        "email": email, "phone": phone, "type": "route", "reference_id": reference_id, "legal_business_name": business_name,
        "business_type": business_type, "contact_name": contact_name,
        "profile": {"category": ROUTE_CATEGORY, "subcategory": ROUTE_SUBCATEGORY, "addresses": {"registered": address}},
    }, version="v2")


def create_stakeholder(account_id, name, email, pan):
    return _call("POST", f"/accounts/{account_id}/stakeholders", {"name": name, "email": email, "kyc": {"pan": pan}}, version="v2")


def request_route_product(account_id):
    return _call("POST", f"/accounts/{account_id}/products", {"product_name": "route", "tnc_accepted": True}, version="v2")


def set_route_settlement(account_id, product_id, holder_name, ifsc, account_number):
    return _call("PATCH", f"/accounts/{account_id}/products/{product_id}", {
        "settlements": {"account_number": account_number, "ifsc_code": ifsc, "beneficiary_name": holder_name}, "tnc_accepted": True,
    }, version="v2")


def create_transfer(payment_id, account_id, amount, notes=None):
    """Send part of a captured payment to a linked account, held until we release it."""
    res = _call("POST", f"/payments/{payment_id}/transfers", {"transfers": [
        {"account": account_id, "amount": to_paise(amount), "currency": "INR", "notes": notes or {}, "on_hold": True}]})
    return res["items"][0]


def release_transfer(transfer_id):
    return _call("PATCH", f"/transfers/{transfer_id}", {"on_hold": False})


def reverse_transfer(transfer_id, amount):
    return _call("POST", f"/transfers/{transfer_id}/reversals", {"amount": to_paise(amount)})


def _hmac(secret, msg):
    return hmac.new(secret.encode(), msg if isinstance(msg, bytes) else msg.encode(), hashlib.sha256).hexdigest()


def verify_checkout_signature(order_id, payment_id, signature):
    if not (enabled() and order_id and payment_id and signature):
        return False
    return hmac.compare_digest(_hmac(settings.RAZORPAY_KEY_SECRET, f"{order_id}|{payment_id}"), str(signature))


def verify_webhook_signature(body, signature):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not (secret and signature):
        return False
    return hmac.compare_digest(_hmac(secret, body), str(signature))


def method_label(p):
    """Razorpay payment entity → (method, short label for the ticket). Never stores full card/account numbers."""
    m = p.get("method") or ""
    if m == "card" and p.get("card"):
        c = p["card"]
        return m, f"{c.get('network') or 'Card'} ending {c.get('last4') or '••••'}"
    if m == "upi":
        return m, (p.get("vpa") or (p.get("upi") or {}).get("vpa") or "UPI")[:60]
    if m == "netbanking":
        return m, p.get("bank") or ""
    if m == "wallet":
        return m, p.get("wallet") or ""
    return m[:12], ""
