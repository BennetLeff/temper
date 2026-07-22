"""Fail-closed board/netlist identity preflight (plan 2026-07-15-001, unit U4).

Re-exported from temper_io_types (Rust / pyo3).
"""

from temper_io_types import BoardIdentityError, preflight_identity

__all__ = [
    "BoardIdentityError",
    "preflight_identity",
]

# OLD: Wraps the Rust ``temper_design_bundle_python.preflight_identity`` boundary
# OLD: (unit U3) so pipeline entry points call one function and get one clear
# OLD: exception type. Verifies, before any placement or routing begins, that:
# OLD:
# OLD: - a board under ``pcb/benchmarks/`` (a quarantined fixture) can never be used
# OLD:   as a production input, regardless of ref overlap;
# OLD: - any other board's footprint reference designators overlap the real
# OLD:   netlist's component references above a safe default threshold.
# OLD:
# OLD: Both checks are derived from the files at call time -- nothing here is a
# OLD: hand-declared count, consistent with ``identity.rs``.
# OLD:
# OLD: from __future__ import annotations
# OLD:
# OLD: from pathlib import Path
# OLD:
# OLD:
# OLD: class BoardIdentityError(ValueError):
# OLD:     """The board fails the identity/role preflight and must not be used.
# OLD:
# OLD:     Raised for both classes of failure the Rust boundary distinguishes: a
# OLD:     quarantined-fixture board used as a production input (role violation),
# OLD:     or a production-role board whose footprint refs don't sufficiently
# OLD:     overlap the netlist (identity mismatch). Never downgraded to a warning --
# OLD:     see plan 2026-07-15-001, requirement R3.
# OLD:     """
# OLD:
# OLD:
# OLD: def preflight_identity(
# OLD:     pcb_path: Path | str,
# OLD:     netlist_path: Path | str,
# OLD:     *,
# OLD:     min_overlap: float = 0.95,
# OLD:     bring_up: bool = False,
# OLD: ) -> None:
# OLD:     """Raise ``BoardIdentityError`` if ``pcb_path`` fails the identity gate.
# OLD:
# OLD:     Args:
# OLD:         pcb_path: Path to the ``.kicad_pcb`` board being loaded. Its path
# OLD:             alone determines role -- any component under a ``benchmarks``
# OLD:             directory is treated as a quarantined fixture and rejected
# OLD:             outright, regardless of ref overlap.
# OLD:         netlist_path: Path to the atopile netlist export (``.net``) the
# OLD:             board is checked against.
# OLD:         min_overlap: Minimum fraction of netlist refs that must also appear
# OLD:             on the board. Safe default; do not lower per-board.
# OLD:         bring_up: Explicit opt-in for boards under active bring-up, where a
# OLD:             partially-populated board is expected to fall below
# OLD:             ``min_overlap``. Off by default -- never inferred.
# OLD:
# OLD:     Raises:
# OLD:         BoardIdentityError: The board is fixture-role, or its ref overlap
# OLD:             with the netlist is below ``min_overlap`` and ``bring_up`` is
# OLD:             not set.
# OLD:     """
# OLD:     import temper_design_bundle_python as _tdb
# OLD:
# OLD:     pcb_path = Path(pcb_path)
# OLD:     netlist_path = Path(netlist_path)
# OLD:     pcb_bytes = pcb_path.read_bytes()
# OLD:     netlist_bytes = netlist_path.read_bytes()
# OLD:     try:
# OLD:         _tdb.preflight_identity(
# OLD:             str(pcb_path),
# OLD:             pcb_bytes,
# OLD:             netlist_bytes,
# OLD:             min_overlap,
# OLD:             bring_up,
# OLD:         )
# OLD:     except ValueError as exc:
# OLD:         raise BoardIdentityError(str(exc)) from exc
