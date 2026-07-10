from __future__ import annotations

import re

NON_SEMANTIC_PATTERNS = [
    re.compile(r"^;exported-at:"),
    re.compile(r"^;tool-version:"),
    re.compile(r"^;machine:"),
    re.compile(r"^;path:"),
]


def normalize_dsn(dsn_text: str) -> str:
    lines = dsn_text.split("\n")
    filtered = []
    for line in lines:
        if any(p.match(line) for p in NON_SEMANTIC_PATTERNS):
            continue
        filtered.append(line.rstrip())
    while filtered and filtered[-1] == "":
        filtered.pop()
    filtered.append("")
    return "\n".join(filtered)


def is_dsn_normalized(dsn_text: str) -> bool:
    for line in dsn_text.split("\n"):
        if any(p.match(line) for p in NON_SEMANTIC_PATTERNS):
            return False
    if not dsn_text.endswith("\n"):
        return False
    if dsn_text.endswith("\n\n"):
        return False
    return all(not (ord(ch) < 32 and ch not in ("\n", "\r", "\t")) for ch in dsn_text)


def strip_control_chars(dsn_text: str) -> str:
    return "".join(ch for ch in dsn_text if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)
