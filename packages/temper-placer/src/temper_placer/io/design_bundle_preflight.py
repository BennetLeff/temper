"""Fail-closed board/netlist identity preflight (plan 2026-07-15-001, unit U4).

Wraps the Rust ``temper_design_bundle_python.preflight_identity`` boundary
(unit U3) so pipeline entry points call one function and get one clear
exception type. Verifies, before any placement or routing begins, that:

- a board under ``pcb/benchmarks/`` (a quarantined fixture) can never be used
  as a production input, regardless of ref overlap;
- any other board's footprint reference designators overlap the real
  netlist's component references above a safe default threshold.

Both checks are derived from the files at call time -- nothing here is a
hand-declared count, consistent with ``identity.rs``.
"""

from __future__ import annotations

from pathlib import Path


class BoardIdentityError(ValueError):
    """The board fails the identity/role preflight and must not be used.

    Raised for both classes of failure the Rust boundary distinguishes: a
    quarantined-fixture board used as a production input (role violation),
    or a production-role board whose footprint refs don't sufficiently
    overlap the netlist (identity mismatch). Never downgraded to a warning --
    see plan 2026-07-15-001, requirement R3.
    """


def preflight_identity(
    pcb_path: Path | str,
    netlist_path: Path | str,
    *,
    min_overlap: float = 0.95,
    bring_up: bool = False,
) -> None:
    """Raise ``BoardIdentityError`` if ``pcb_path`` fails the identity gate.

    Args:
        pcb_path: Path to the ``.kicad_pcb`` board being loaded. Its path
            alone determines role -- any component under a ``benchmarks``
            directory is treated as a quarantined fixture and rejected
            outright, regardless of ref overlap.
        netlist_path: Path to the atopile netlist export (``.net``) the
            board is checked against.
        min_overlap: Minimum fraction of netlist refs that must also appear
            on the board. Safe default; do not lower per-board.
        bring_up: Explicit opt-in for boards under active bring-up, where a
            partially-populated board is expected to fall below
            ``min_overlap``. Off by default -- never inferred.

    Raises:
        BoardIdentityError: The board is fixture-role, or its ref overlap
            with the netlist is below ``min_overlap`` and ``bring_up`` is
            not set.
    """
    import temper_design_bundle_python as _tdb

    pcb_path = Path(pcb_path)
    netlist_path = Path(netlist_path)
    pcb_bytes = pcb_path.read_bytes()
    netlist_bytes = netlist_path.read_bytes()
    try:
        _tdb.preflight_identity(
            str(pcb_path),
            pcb_bytes,
            netlist_bytes,
            min_overlap,
            bring_up,
        )
    except ValueError as exc:
        raise BoardIdentityError(str(exc)) from exc
