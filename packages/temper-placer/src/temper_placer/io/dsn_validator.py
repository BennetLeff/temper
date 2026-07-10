from __future__ import annotations

import logging

from temper_placer.io.dsn_schema import extract_schema_hash

logger = logging.getLogger(__name__)


class DSNVersionMismatchError(Exception):
    """Raised when a DSN file's schema version doesn't match the expected hash."""

    def __init__(self, expected: str, received: str | None):
        self.expected = expected
        self.received = received
        msg = (
            f"DSN schema version mismatch: expected sha256:{expected}"
            f", got sha256:{received if received else 'MISSING'}"
            ". The upstream stage may have changed its output format."
        )
        super().__init__(msg)


def validate_dsn(dsn_text: str, expected_hash: str) -> None:
    """Raise DSNVersionMismatchError if the embedded hash doesn't match."""
    received = extract_schema_hash(dsn_text)
    if received != expected_hash:
        raise DSNVersionMismatchError(expected_hash, received)


def validate_or_warn_dsn(dsn_text: str, expected_hash: str) -> bool:
    """Return False on mismatch (no exception), logging a warning."""
    received = extract_schema_hash(dsn_text)
    if received != expected_hash:
        logger.warning(
            "DSN schema version mismatch: expected sha256:%s, got sha256:%s",
            expected_hash,
            received if received else "MISSING",
        )
        return False
    return True
