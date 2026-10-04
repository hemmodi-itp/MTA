"""
secrets_box.py — AES-256-GCM for small secrets (live-app test credentials) shared with the web app.

Format (base64url, no padding):  iv(12 bytes) || ciphertext || tag(16 bytes)
Key: SHA-256 of AQP_SECRET_KEY — the same derivation as frontend/src/lib/api/server/secrets.ts,
so the web app encrypts on submit and only the evaluation service decrypts, at run time.
"""

import base64
import hashlib
import json
import os
from typing import Any, Optional


def _key() -> bytes:
    secret = os.environ.get("AQP_SECRET_KEY")
    if not secret:
        raise RuntimeError("AQP_SECRET_KEY is not set (repo-root .env and frontend/.env must share it)")
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_json(value: Any) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = os.urandom(12)
    ct = AESGCM(_key()).encrypt(iv, json.dumps(value).encode("utf-8"), None)  # ct includes the 16-byte tag
    return base64.urlsafe_b64encode(iv + ct).decode("ascii").rstrip("=")


def decrypt_json(token: Optional[str]) -> Optional[Any]:
    if not token:
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    return json.loads(AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8"))
