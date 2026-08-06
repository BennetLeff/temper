"""AI-Slop Pattern Linter — Post-route detection of machine-routing artifacts.

Detects four artifact classes on routed PCB files:
- Hairpin turns: track segments reversing direction within a close distance.
- Zigzag patterns: 3+ consecutive alternating direction changes.
- Isolated vias: vias with only one connected track segment (stubs).
- Single-net detours: nets where path_length / direct_distance exceeds a
  threshold.

Each lint function returns a list of findings (dicts with location, type,
severity, and description).  Gate: ``lint_all`` returns 0 artifacts.

Based on R5 of the human-like-routing-quality plan.

Wave 4 Phase B (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
every public function below delegates to its matching cluster-F lint kernel
in ``temper_quality_oracle`` (PR #750). Each kernel's ``source`` parameter
accepts either a scenario dict or anything path-like (``str`` or
``__fspath__``) and, for a path, re-parses through the same
``temper_placer.io.kicad_parser.parse_kicad_pcb`` this module's own
``_parse_pcb`` called -- so passing ``routed_pcb_path`` straight through is a
like-for-like substitution, not a widened contract. The former private
scalar/ordering helpers (``_parse_pcb``, ``_load_traces_by_net``,
``_order_traces``, ``_vector``, ``_angle_between``, ``_distance_mm``) had no
callers outside this file's own now-replaced bodies and were removed rather
than left dead; their five one-to-one kernel counterparts stay ledgered in
``.unwired-kernel-inventory`` with that reason.
"""

from __future__ import annotations

from pathlib import Path

import temper_quality_oracle as _rs


def lint_hairpin_turns(routed_pcb_path: Path) -> list[dict]:
    """Find track segments that reverse direction by >=160deg.

    Parses the routed PCB, groups traces by net, orders them into
    connected paths, and checks the turn angle at each junction.
    """
    return _rs.slop_lint_hairpin_turns_py(routed_pcb_path)


def lint_zigzag_patterns(routed_pcb_path: Path) -> list[dict]:
    """Find 3+ consecutive alternating direction changes.

    Excludes hairpin reversals (>=160 deg) from the alternation count.
    """
    return _rs.slop_lint_zigzag_patterns_py(routed_pcb_path)


def lint_isolated_vias(routed_pcb_path: Path) -> list[dict]:
    """Find vias with only one connected track segment (stubs)."""
    return _rs.slop_lint_isolated_vias_py(routed_pcb_path)


def lint_single_net_detours(routed_pcb_path: Path, max_ratio: float = 1.5) -> list[dict]:
    """Find nets where path_length / direct_distance > max_ratio."""
    return _rs.slop_lint_single_net_detours_py(routed_pcb_path, max_ratio)


def lint_all(routed_pcb_path: Path) -> list[dict]:
    """Run all slop linters, return combined list of artifacts."""
    return _rs.slop_lint_all_py(routed_pcb_path)
