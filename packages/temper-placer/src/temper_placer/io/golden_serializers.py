"""
Golden fixture serialization functions for pipeline stage boundaries.

Re-exported from temper_io_types (Rust / pyo3).
"""

from temper_io_types import (
    CURRENT_FORMAT_VERSION,
    SERIALIZER_REGISTRY,
    serialize_boardstate_to_dsn,
    serialize_boardstate_to_ses,
    serialize_connectivity_to_json,
    serialize_violations_to_json,
)

__all__ = [
    "CURRENT_FORMAT_VERSION",
    "serialize_boardstate_to_dsn",
    "serialize_boardstate_to_ses",
    "serialize_violations_to_json",
    "serialize_connectivity_to_json",
    "SERIALIZER_REGISTRY",
]
