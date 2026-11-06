"""Exceptions for the ptouch core."""
from __future__ import annotations


class PtouchError(Exception):
    """Base error."""


class TransportError(PtouchError):
    """Could not talk to the printer (not found, permission, timeout...)."""


class ProtocolError(PtouchError):
    """Unexpected data from, or invalid request for, the printer."""


class PrinterError(PtouchError):
    """The printer reported an error condition."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(", ".join(errors) or "unknown printer error")
