from __future__ import annotations

import re

import temper_dsn as _td

NON_SEMANTIC_PATTERNS = [
    re.compile(r"^;exported-at:"),
    re.compile(r"^;tool-version:"),
    re.compile(r"^;machine:"),
    re.compile(r"^;path:"),
]


def normalize_dsn(dsn_text: str) -> str:
    return _td.normalize_dsn(dsn_text)


def is_dsn_normalized(dsn_text: str) -> bool:
    return _td.is_dsn_normalized(dsn_text)


def strip_control_chars(dsn_text: str) -> str:
    return _td.strip_control_chars(dsn_text)
