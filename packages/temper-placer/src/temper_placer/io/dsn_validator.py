from __future__ import annotations

import logging

from temper_placer.io.dsn_schema import DSNSchemaHasher

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


class DSNVersionValidator:
    """Validate DSN schema version before processing."""

    @staticmethod
    def validate(dsn_text: str, expected_hash: str) -> None:
        received = DSNSchemaHasher.extract_hash(dsn_text)
        if received != expected_hash:
            raise DSNVersionMismatchError(expected_hash, received)

    @staticmethod
    def validate_or_warn(dsn_text: str, expected_hash: str) -> bool:
        received = DSNSchemaHasher.extract_hash(dsn_text)
        if received != expected_hash:
            logger.warning(
                "DSN schema version mismatch: expected sha256:%s, got sha256:%s",
                expected_hash,
                received if received else "MISSING",
            )
            return False
        return True
