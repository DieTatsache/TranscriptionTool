"""Credential primitives: random tokens, token digests, password hashing and policy."""

import asyncio
import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

TOKEN_BYTES = 32  # 256 bits of entropy
MAX_PASSWORD_LENGTH = 128  # bounds hashing cost per request


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(expected: str, provided: str) -> bool:
    return hmac.compare_digest(expected.encode(), provided.encode())


class PasswordHasher:
    """Argon2id (OWASP's first choice). Hashing is slow by design, so it runs in a
    worker thread instead of blocking the event loop."""

    def __init__(self, *, time_cost: int, memory_cost_kib: int, parallelism: int) -> None:
        self._hasher = Argon2Hasher(
            time_cost=time_cost, memory_cost=memory_cost_kib, parallelism=parallelism
        )
        # Verified against when an account doesn't exist, so response time doesn't reveal it.
        self._dummy_hash = self._hasher.hash(new_token())

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str | None, password: str) -> bool:
        try:
            await asyncio.to_thread(
                self._hasher.verify, password_hash or self._dummy_hash, password
            )
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        return password_hash is not None

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


# Common base words; "Password2024!" style variants are caught by stripping the suffix.
_COMMON_WORDS = frozenset(
    {
        "password", "passwort", "passwd", "qwerty", "qwertz", "azerty", "letmein", "welcome",
        "willkommen", "admin", "administrator", "iloveyou", "sonora", "trainer", "monkey",
        "dragon", "football", "fussball", "baseball", "sunshine", "princess", "master",
        "hallo", "hello", "secret", "geheim", "changeme", "default", "login", "abc",
    }
)  # fmt: skip
_KEYBOARD_RUNS = (
    "0123456789012345678901234567890",
    "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz",
    "qwertyuiopasdfghjklzxcvbnmqwertyuiop",
    "qwertzuiopasdfghjklyxcvbnmqwertzuiop",
    "1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik9ol0p",
)
_SUFFIX_RE = re.compile(r"[\d\W_]+$")


def password_problem(password: str, *, min_length: int, email: str = "") -> str | None:
    """Returns a user-facing reason why ``password`` is not acceptable, or None.

    Follows NIST SP 800-63B: length over composition rules, plus rejecting predictable
    choices (common words, keyboard runs, repeated characters, the account's email).
    """
    if len(password) < min_length:
        return f"Password must be at least {min_length} characters long."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
    lowered = password.lower()
    if len(set(lowered)) < 5:
        return "Password is too simple; use more varied characters."
    if any(lowered in run or lowered in run[::-1] for run in _KEYBOARD_RUNS):
        return "Password is too easy to guess."
    stem = _SUFFIX_RE.sub("", lowered)
    if stem in _COMMON_WORDS or lowered in _COMMON_WORDS:
        return "Password is too common."
    local_part = email.split("@", 1)[0].lower()
    if len(local_part) >= 4 and local_part in lowered:
        return "Password must not contain your email address."
    return None
