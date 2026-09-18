"""Password hashing port.

The application only sees `hash`/`verify`; the concrete scheme (argon2id via
argon2-cffi) is an implementation detail. No hand-rolled hashing anywhere.
"""

from typing import Protocol

from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


class PasswordHasher(Protocol):
    def hash(self, raw: str) -> str: ...

    def verify(self, raw: str, encoded: str) -> bool: ...


class Argon2PasswordHasher:
    """argon2id with library defaults; hashes are salted and self-describing."""

    def __init__(self) -> None:
        self._hasher = Argon2Hasher()

    def hash(self, raw: str) -> str:
        return self._hasher.hash(raw)

    def verify(self, raw: str, encoded: str) -> bool:
        try:
            self._hasher.verify(encoded, raw)
        except (VerifyMismatchError, InvalidHashError):
            return False
        return True
