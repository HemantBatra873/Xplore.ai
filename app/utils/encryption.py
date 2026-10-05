import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def get_fernet_key(secret: str) -> bytes:
    """
    Derive a Fernet-compatible url-safe key from SECRET_KEY via SHA-256.
    """
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


fernet = Fernet(get_fernet_key(settings.SECRET_KEY))


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key."""
    if not api_key:
        return ""
    return fernet.encrypt(api_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key."""
    if not encrypted_key:
        return ""
    try:
        return fernet.decrypt(encrypted_key.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""
