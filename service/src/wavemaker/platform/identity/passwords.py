"""Hashing passwords, and comparing them without leaking how wrong they were.

Argon2id, with the library's own defaults. Tuning them by hand is how a project ends up with
parameters chosen once, for a machine it no longer runs on.

`verify` answers False rather than raising on a bad password, because a caller that has to
tell "wrong password" from "corrupt hash" by catching different exceptions is a caller that
will catch neither.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify(password: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
