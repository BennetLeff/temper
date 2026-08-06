"""
Real-board placement fixture for REQ-SAFE-01 integration tests.

This file is now a thin binding of the production loader
``temper_placer.io.real_board.load_real_board_placement`` (issue #617 second
half: the loader was hoisted out of the test tree so the CLI optimize path
can construct the validator's placement/voltage_domains too). It exists only
to bind the test environment's default repo paths and preserve the
no-argument ``load_real_board_placement()`` API every test and evidence
script in this repo calls.

All derivation logic -- the domain sub-classification, the copper-aware
proximity reporting, the stats shape, the ``RealBoardUnavailable`` contract
-- lives in the production module; see its docstring for the full rationale
(``docs/evidence/2026-07-27-domain-classification-coverage.md`` for the
measured derivation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from temper_placer.io.real_board import (  # noqa: F401  (re-exported)
    MAX_IEC_MARGIN_MM,
    RealBoardUnavailable,
)
from temper_placer.io.real_board import (
    load_real_board_placement as _load_real_board_placement,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_NETLIST_PATH = _REPO_ROOT / "elec" / "build" / "default.net"
_MANIFEST_PATH = _REPO_ROOT / "elec" / "domain_manifest.yaml"


def load_real_board_placement() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The production loader bound to this repo's real board (no-arg API).

    Returns:
        (placement, voltage_domains, stats) -- see
        ``temper_placer.io.real_board.load_real_board_placement``.

    Raises:
        RealBoardUnavailable: if ``pcb/temper.kicad_pcb``, the compiled
            netlist (``elec/build/default.net`` -- run ``make netlist``
            first), or ``elec/domain_manifest.yaml`` is missing. Callers
            should ``pytest.skip`` on this, not treat it as a passing or
            failing check.
    """
    return _load_real_board_placement(_PCB_PATH, _MANIFEST_PATH, _NETLIST_PATH)
