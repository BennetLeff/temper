from __future__ import annotations

import logging

import temper_dsn as _td

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
    """Validate the DSN schema-version header against ``expected_hash``.

    ``temper_dsn``'s Rust implementation raises a plain ``ValueError`` on
    mismatch; this wraps it in ``DSNVersionMismatchError`` so callers get
    the typed, attribute-bearing exception this module has always
    contracted for (``.expected`` / ``.received``, used by
    ``validate_or_warn_dsn`` callers and downstream error handling).
    """
    try:
        _td.validate_dsn(dsn_text, expected_hash)
    except ValueError:
        received = _td.extract_schema_hash(dsn_text)
        raise DSNVersionMismatchError(expected_hash, received) from None


def validate_or_warn_dsn(dsn_text: str, expected_hash: str) -> bool:
    result = _td.validate_or_warn_dsn(dsn_text, expected_hash)
    if not result:
        received = _td.extract_schema_hash(dsn_text)
        logger.warning(
            "DSN schema version mismatch: expected sha256:%s, got sha256:%s",
            expected_hash,
            received if received else "MISSING",
        )
    return result
