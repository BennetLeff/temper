"""Canary fixtures for check_evidence_provenance.py (R42).

``check_file()`` operates on one file path in isolation (no repo-wide scan
needed), so the fixtures are a single markdown file each -- one with a
well-formed ``provenance: commit=<sha> dirty=<bool>`` stamp, one with none
at all (the exact incident class this gate exists to catch: a doc that
claims no traceable origin).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

VALID_SHA = "a" * 40


def _state(gate_module, text: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "evidence.md"
        f.write_text(text, encoding="utf-8")
        result = gate_module.check_file(f)
        return "clean" if result.ok else "violation"


def pristine_stamped(gate_module) -> str:
    text = (
        "# Evidence doc\n\n"
        f"provenance: commit={VALID_SHA} dirty=false\n\n"
        "Some findings.\n"
    )
    return _state(gate_module, text)


def seed_no_stamp(gate_module) -> str:
    """No provenance line at all -- an unstamped evidence doc, exactly
    the traceability gap this gate exists to close."""
    text = "# Evidence doc\n\nSome findings, no provenance line.\n"
    return _state(gate_module, text)
