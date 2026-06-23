from __future__ import annotations

import re

NON_SEMANTIC_PATTERNS = [
    re.compile(r"^;exported-at:"),
    re.compile(r"^;tool-version:"),
    re.compile(r"^;machine:"),
    re.compile(r"^;path:"),
]


class DSNNormalizer:
    """Post-processing pass to strip non-semantic noise from DSN output."""

    @staticmethod
    def normalize(dsn_text: str) -> str:
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

    @staticmethod
    def is_normalized(dsn_text: str) -> bool:
        for line in dsn_text.split("\n"):
            if any(p.match(line) for p in NON_SEMANTIC_PATTERNS):
                return False
        if not dsn_text.endswith("\n"):
            return False
        if dsn_text.endswith("\n\n"):
            return False
        for ch in dsn_text:
            if ord(ch) < 0x20 and ch not in ("\n", "\r", "\t"):
                return False
        return True

    @staticmethod
    def strip_control_chars(dsn_text: str) -> str:
        return "".join(ch for ch in dsn_text if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)
