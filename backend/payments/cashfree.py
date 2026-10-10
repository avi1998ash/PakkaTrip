"""Cashfree Payment Gateway client (PG v3 API) using only Python standard library.

Credentials and environment configured via settings:
  CASHFREE_APP_ID
  CASHFREE_SECRET_KEY
  CASHFREE_ENV (TEST / PROD)
  CASHFREE_API_VERSION (default: 2023-08-01)
"""
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings

SANDBOX_API = "https://sandbox.cashfree.com/pg"
PRODUCTION_API = "https://api.cashfree.com/pg"


class GatewayError(Exception):
    """Cashfree rejected the request or couldn't be reached; safe to show message."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def enabled():
    return bool(getattr(settings, "CASHFREE_APP_ID", "") and getattr(settings, "CASHFREE_SECRET_KEY", ""))


def api_url():
    env = getattr(settings, "CASHFREE_ENV", "TEST").upper()
    return SANDBOX_API if env == "TEST" else PRODUCTION_API


def to_amount(amount):
    """Convert amount to float with 2 decimal places as expected by Cashfree."""
    return float(Decimal(str(amount)).quantize(Decimal("0.01")))


def _call(method, path, body=None, headers=None):
    if not enabled():
        raise GatewayError("Cashfree payments are not configured.")
    base = api_url()
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {
        "x-client-id": settings.CASHFREE_APP_ID,
        "x-client-secret": settings.CASHFREE_SECRET_KEY,
        "x-api-version": getattr(settings, "CASHFREE_API_VERSION", "2023-08-01"),
        "Content-Type": "application/json",
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = None
        try:
            err_data = json.load(e)
            detail = err_data.get("message") or err_data.get("error", {}).get("description")
        except Exception:
            pass
        raise GatewayError(detail or f"Cashfree payment gateway error ({e.code}).", retryable=e.code >= 500) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GatewayError("Couldn't reach Cashfree payment gateway. Please try again.", retryable=True) from e


def create_order(amount, order_id, customer_name, customer_email, customer_phone, return_url=None, notes=None):
    """Create an order with Cashfree and return the response including payment_session_id."""
    clean_phone = "".join(c for c in str(customer_phone) if c.isdigit())[-10:]
    if len(clean_phone) < 10:
        clean_phone = "9999999999"

    payload = {
        "order_id": order_id,
        "order_amount": to_amount(amount),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": f"cust_{clean_phone}",
            "customer_name": (customer_name or "Traveller")[:100],
            "customer_email": (customer_email or "traveller@pakkatrip.com")[:100],
            "customer_phone": clean_phone,
        },
        "order_meta": {
            "return_url": return_url,
        },
        "order_note": (notes or {}).get("booking", f"PakkaTrip Booking {order_id}")[:200],
    }
    return _call("POST", "/orders", payload)


def fetch_order(order_id):
    """Fetch order status and details by order_id."""
    return _call("GET", f"/orders/{order_id}")


def fetch_order_payments(order_id):
    """Fetch list of all payment attempts for an order."""
    return _call("GET", f"/orders/{order_id}/payments")


def fetch_payment(order_id, cf_payment_id):
    """Fetch specific payment attempt by cf_payment_id."""
    return _call("GET", f"/orders/{order_id}/payments/{cf_payment_id}")


def create_refund(order_id, amount, refund_id, note=None, speed="STANDARD"):
    """Initiate a refund for an order."""
    payload = {
        "refund_amount": to_amount(amount),
        "refund_id": refund_id,
        "refund_note": (note or f"Refund for {order_id}")[:200],
        "refund_speed": speed,
    }
    return _call("POST", f"/orders/{order_id}/refunds", payload)


def fetch_refund(order_id, refund_id):
    """Fetch refund status by refund_id."""
    return _call("GET", f"/orders/{order_id}/refunds/{refund_id}")


def verify_webhook_signature(timestamp, raw_body, signature):
    """Verify Cashfree PG v3 webhook signature: base64(HMAC-SHA256(secret, timestamp + body))."""
    secret = getattr(settings, "CASHFREE_WEBHOOK_SECRET", "") or getattr(settings, "CASHFREE_SECRET_KEY", "")
    if not (secret and timestamp and raw_body and signature):
        return False
    body_str = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else str(raw_body)
    data = f"{timestamp}{body_str}".encode("utf-8")
    computed = base64.b64encode(hmac.new(secret.encode("utf-8"), data, hashlib.sha256).digest()).decode("utf-8")
    return hmac.compare_digest(computed, str(signature).strip())


def method_label(p):
    """Cashfree payment entity -> (method, short label for the ticket)."""
    method_data = p.get("payment_method") or {}
    group = (p.get("payment_group") or "").lower()

    if "upi" in method_data or group == "upi":
        upi_info = method_data.get("upi") or {}
        vpa = upi_info.get("upi_id") or "UPI"
        return "upi", str(vpa)[:60]

    if "card" in method_data or group == "card":
        card_info = method_data.get("card") or {}
        network = card_info.get("card_network") or card_info.get("card_type") or "Card"
        last4 = card_info.get("card_number") or ""
        last4_str = last4[-4:] if len(last4) >= 4 else "••••"
        return "card", f"{network} ending {last4_str}"[:60]

    if "netbanking" in method_data or group == "netbanking":
        nb = method_data.get("netbanking") or {}
        bank = nb.get("netbanking_bank_name") or "Netbanking"
        return "netbanking", str(bank)[:60]

    if "app" in method_data or group == "wallet":
        app_info = method_data.get("app") or {}
        provider = app_info.get("provider") or "Wallet"
        return "wallet", str(provider)[:60]

    return group[:12] if group else "online", ""
