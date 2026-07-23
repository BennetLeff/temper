from __future__ import annotations

import temper_dsn as _td

# Re-exports — backed by temper-dsn Rust crate


def normalize_dsn(dsn_text: str) -> str:
    return _td.normalize_dsn(dsn_text)


def is_dsn_normalized(dsn_text: str) -> bool:
    return _td.is_dsn_normalized(dsn_text)


def strip_control_chars(dsn_text: str) -> str:
    return _td.strip_control_chars(dsn_text)
