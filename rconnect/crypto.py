"""Generic field encryption for rconnect's own storage (NOT the mRemoteNG
import format in importers/mremoteng.py, which deliberately matches
mRemoteNG's own on-disk scheme for compatibility).

Same primitives (PBKDF2 + AES-GCM, salt doubling as AAD) because they're
solid and already in use elsewhere in this codebase, but with our own
iteration count — mRemoteNG's hardcoded 1000 rounds of PBKDF2-SHA1 is
weak by modern standards (OWASP recommends 600k+ for PBKDF2-SHA1 or
~210k for SHA256); we aren't constrained by needing to match another
application's file format here, so there's no reason to inherit that
weakness.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 200_000
_SENTINEL_PLAINTEXT = b"rconnect-master-password-ok"


class WrongPassphraseError(Exception):
    pass


def encrypt_field(plaintext: str, passphrase: str, iterations: int = ITERATIONS) -> str:
    salt = os.urandom(16)
    nonce = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), salt)
    return base64.b64encode(salt + nonce + ct).decode("ascii")


def decrypt_field(enc_b64: str, passphrase: str, iterations: int = ITERATIONS) -> str:
    raw = base64.b64decode(enc_b64)
    salt, nonce, ct_and_tag = raw[:16], raw[16:32], raw[32:]
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)
    try:
        pt = AESGCM(key).decrypt(nonce, ct_and_tag, salt)
    except InvalidTag as exc:
        raise WrongPassphraseError("wrong master password") from exc
    return pt.decode("utf-8")


def make_sentinel(passphrase: str, iterations: int = ITERATIONS) -> str:
    """An encrypted known-plaintext value, stored alongside the data, used
    to verify a master password at load time without needing any real
    connection's password to be present (same trick mRemoteNG's own
    `Protected` attribute uses).
    """
    return encrypt_field(_SENTINEL_PLAINTEXT.decode("utf-8"), passphrase, iterations)


def verify_sentinel(sentinel_b64: str, passphrase: str, iterations: int = ITERATIONS) -> bool:
    try:
        return decrypt_field(sentinel_b64, passphrase, iterations) == _SENTINEL_PLAINTEXT.decode("utf-8")
    except WrongPassphraseError:
        return False
