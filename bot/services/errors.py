"""Domain errors raised by services. Handlers translate ``code`` into Arabic text via ``texts.error``."""
from __future__ import annotations


class DomainError(Exception):
    def __init__(self, code: str, **params) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


class PermissionDenied(DomainError):
    def __init__(self) -> None:
        super().__init__("forbidden")
