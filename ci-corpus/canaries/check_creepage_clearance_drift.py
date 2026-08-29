"""Canary fixtures for check_creepage_clearance_drift.py (R42).

Each ``pristine_*``/``seed_*`` function takes the (possibly mutated)
``check_creepage_clearance_drift`` module and returns a normalized verdict
string: ``"clean"``, ``"violation"``, or ``"error"`` (a raised
``GateError``, caught here so the runner never has to know each gate's own
exception type).
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def _mk(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _mk_scan_roots(root: Path) -> None:
    for name in ("elec", "scripts", "packages", "configs"):
        (root / name).mkdir(parents=True, exist_ok=True)


def _agreeing_tree(root: Path) -> None:
    """Two declaration sites, same (metric, tier), same value -- clean."""
    _mk_scan_roots(root)
    _mk(
        root,
        "elec/src/constraints.ato",
        "module Constraints:\n"
        "    module HighVoltage:\n"
        "        creepage = 8.0mm   # IEC 60335-1 working insulation\n",
    )
    _mk(
        root,
        "scripts/derived_constant.py",
        "# working creepage figure, mirrors constraints.ato HighVoltage\n"
        "HV_CREEPAGE_MM = 8.0\n",
    )


def _mismatched_tree(root: Path) -> None:
    """Same shape, but the second site has drifted -- the PD2->PD3 defect
    this gate exists to catch (module docstring)."""
    _mk_scan_roots(root)
    _mk(
        root,
        "elec/src/constraints.ato",
        "module Constraints:\n"
        "    module HighVoltage:\n"
        "        creepage = 8.0mm   # IEC 60335-1 working insulation\n",
    )
    _mk(
        root,
        "scripts/derived_constant.py",
        "# working creepage figure, drifted from constraints.ato HighVoltage\n"
        "HV_CREEPAGE_MM = 10.0\n",
    )


def _empty_tree(root: Path) -> None:
    """Scan roots exist but hold zero declarations -- anti-vacuity case."""
    _mk_scan_roots(root)


def _state(gate_module, root: Path) -> str:
    try:
        state, *_ = gate_module.run(root)
        return state
    except gate_module.GateError:
        return "error"


def pristine_agree(gate_module) -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _agreeing_tree(root)
        return _state(gate_module, root)


def seed_mismatch(gate_module) -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _mismatched_tree(root)
        return _state(gate_module, root)


def seed_zero_declarations(gate_module) -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _empty_tree(root)
        return _state(gate_module, root)
