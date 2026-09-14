"""Password hashing utilities using bcrypt directly.

We call the ``bcrypt`` library directly rather than going through
``passlib.CryptContext`` because passlib 1.7.4's backend auto-detection is
incompatible with bcrypt >= 4.1 (it raises at import time). bcrypt itself is
still the hashing algorithm, which is what the design requires.
"""
from __future__ import annotations

import bcrypt

# bcrypt hard-limits passwords to 72 bytes. We truncate before hashing so that
# longer passphrases don't raise and so verify() is deterministic.
_MAX_BYTES = 72


def _to_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_MAX_BYTES]


def hash_password(plain: str) -> str:
    """Return a bcrypt hash (modular-crypt format) for ``plain``."""
    digest = bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check ``plain`` against a stored bcrypt ``hashed`` value."""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
