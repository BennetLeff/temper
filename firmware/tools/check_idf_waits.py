#!/usr/bin/env python3
"""Gate: ESP-IDF SPI bus-lock calls must wait with portMAX_DELAY.

ESP-IDF 5.3 (the CI image, espressif/idf:release-v5.3) returns ESP_ERR_INVALID_ARG from
spi_device_acquire_bus, spi_device_polling_start and spi_bus_lock_acquire_start for any other wait
(spi_master.c: "acquire finite time not supported now."; spi_bus_lock.c: "timeout other than
portMAX_DELAY not supported"). Such a call fails on every attempt on hardware, while host tests, which
stub the transport, pass. Found 2026-11-25: the MCP3202 read asked for 2 ms, so every RMS-channel read
failed and latched N21_FAULT_RMS_CHANNEL.

Usage: python3 firmware/tools/check_idf_waits.py   (exit 1 and one line per offending call)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FIRMWARE = Path(__file__).resolve().parent.parent
# function -> index of its wait argument
CALLS = {"spi_device_acquire_bus": 1, "spi_device_polling_start": 2, "spi_bus_lock_acquire_start": 1}
SKIP_DIRS = {"build", "managed_components", "unity"}
_scanned = 0


def _strip_comments(src: str) -> str:
    """Blank out comments and string literals, keeping offsets and newlines."""
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
        elif src[i] in "\"'":
            q, j = src[i], i + 1
            while j < n and src[j] != q:
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
        else:
            out.append(src[i])
            i += 1
            continue
        out.append(re.sub(r"[^\n]", " ", src[i:j]))
        i = j
    return "".join(out)


def _args(src: str, open_paren: int) -> list[str] | None:
    """Top-level arguments of the call whose '(' is at open_paren."""
    depth, start, args = 0, open_paren + 1, []
    for k in range(open_paren, len(src)):
        c = src[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append(src[start:k].strip())
                return args
        elif c == "," and depth == 1:
            args.append(src[start:k].strip())
            start = k + 1
    return None


def check_source(name: str, src: str) -> list[str]:
    code = _strip_comments(src)
    problems = []
    for fn, idx in CALLS.items():
        for m in re.finditer(r"\b" + fn + r"\s*\(", code):
            args = _args(code, m.end() - 1)
            if args is None or len(args) <= idx:
                problems.append(f"{name}:{code.count(chr(10), 0, m.start()) + 1}: cannot parse {fn}()")
                continue
            wait = args[idx]
            if re.fullmatch(r"(TickType_t\s+)?\w+", wait) and wait.split()[0] == "TickType_t":
                continue  # a declaration: `TickType_t wait`
            if wait != "portMAX_DELAY":
                line = code.count("\n", 0, m.start()) + 1
                problems.append(f"{name}:{line}: {fn}() waits `{wait}`; ESP-IDF 5.3 accepts only portMAX_DELAY "
                                f"(any other value returns ESP_ERR_INVALID_ARG every time)")
    return problems


def check_tree(root: Path = FIRMWARE) -> list[str]:
    global _scanned
    _scanned, problems = 0, []
    for p in sorted(root.rglob("*")):
        if p.suffix not in (".c", ".h") or SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        _scanned += 1
        problems += check_source(str(p.relative_to(root.parent)), p.read_text(errors="replace"))
    return problems


def files_scanned() -> int:
    return _scanned


def main() -> int:
    problems = check_tree()
    for line in problems:
        print(line)
    print(f"idf waits: {'PASS' if not problems else 'FAIL'} ({files_scanned()} files)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
