"""
Password hashing utilities.

Uses `bcrypt` — a slow-by-design hashing algorithm with a built-in
random salt per password. "Slow by design" matters here: a fast hash
(like plain SHA-256) makes brute-forcing millions of guesses per
second trivial for an attacker who steals the database. bcrypt is
deliberately expensive to compute, which makes large-scale guessing
impractical while still being fast enough for a single login check.

Nothing in this module ever touches a plaintext password after
hashing it — the plaintext is discarded as soon as `hash_password()`
returns.
"""

import bcrypt

# Number of hashing rounds. Higher = slower = more resistant to
# brute-force, but also slower for legitimate logins. 12 is a common,
# well-tested default as of 2026.
_BCRYPT_ROUNDS = 12


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password for storage.

    Returns a string safe to store in the `password_hash` column.
    The salt is embedded in the returned hash itself, so nothing else
    needs to be stored alongside it.
    """
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Check a plaintext password attempt against a stored hash.

    Returns True only if they match. Never raises on a malformed
    hash — treats that as "does not match" so a corrupted or
    unexpected value in the database can't crash a login attempt.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
