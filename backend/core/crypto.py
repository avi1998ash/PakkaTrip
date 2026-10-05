"""Encryption for sensitive data (bank account numbers, PAN, ID document copies) — Fernet (AES-128-CBC + HMAC).

The key is FIELD_ENCRYPTION_KEY from backend/.env (generate one with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
Never change it once real data is stored, or the stored values can't be read back.
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:   # development fallback only; production must set its own key
        key = base64.urlsafe_b64encode(hashlib.sha256(f"field-key:{settings.SECRET_KEY}".encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value):
    return _fernet().encrypt(str(value).encode()).decode() if value else ""


def decrypt(token):
    return _fernet().decrypt(token.encode()).decode() if token else ""


def encrypt_bytes(data):
    """For whole files (e.g. a masked Aadhaar copy): the stored file is unreadable without the key."""
    return _fernet().encrypt(data)


def decrypt_bytes(token):
    return _fernet().decrypt(token)
