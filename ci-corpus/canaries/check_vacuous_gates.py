"""Canary fixtures for check_vacuous_gates.py (R42) -- the anti-vacuity
guard itself. This is the meta case the plan calls out explicitly: a gate
whose own job is catching vacuous checks must not itself pass a
"return True" mutant.
"""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

GUARDED_ALL_SOURCE = textwrap.dedent(
    """
    def check(items):
        if not items:
            raise ValueError("empty")
        return all(x.ok for x in items)
    """
)

UNGUARDED_ALL_SOURCE = textwrap.dedent(
    """
    def check(items):
        return all(x.ok for x in items)
    """
)


def _state(gate_module, source: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "candidate.py"
        f.write_text(source, encoding="utf-8")
        violations = gate_module.find_violations(f)
        return "violation" if violations else "clean"


def pristine_guarded(gate_module) -> str:
    return _state(gate_module, GUARDED_ALL_SOURCE)


def seed_unguarded_all(gate_module) -> str:
    """The real defect class this gate exists to catch: `all()` over a
    possibly-empty comprehension with no preceding non-empty guard."""
    return _state(gate_module, UNGUARDED_ALL_SOURCE)
