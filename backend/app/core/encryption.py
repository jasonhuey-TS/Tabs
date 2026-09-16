"""
Lightweight Fernet encryption for secrets stored in the DB.
Keyed from SECRET_KEY so secrets are tied to the deployment.
"""
import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import settings


def _fernet() -> Fernet:
    # Derive a 32-byte key from SECRET_KEY using SHA-256
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return a URL-safe base64 token."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token back to the original string."""
    return _fernet().decrypt(token.encode()).decode()
