"""SPECCTRA DSN export — delegation shim over the Rust emitter.

Wave-4 Phase-3 candidate 6. The emitter itself lives in
``temper-io-types`` (``src/dsn_exporter.rs``); this module keeps ``DSNExporter``'s
public API byte-for-byte compatible and forwards every export call.

Two kernels stay on this side of the boundary, deliberately. Both would have
been *behaviour changes* rather than ports, which is the same judgement PR #688
made about ``yaml.safe_load``:

1. ``np.argmax`` still derives rotation indices from a 2-D logits/one-hot array.
   Reimplementing argmax in Rust means re-deciding numpy's dtype promotion and
   its tie-break rule on an array the crate cannot see without a numpy-interop
   dependency the phase plan explicitly declines to assume. Calling the same
   ``np.argmax`` the pre-migration code called makes the step identical by
   identity, not by argument.
2. ``pin_world_position`` still computes pad world geometry for the
   non-deterministic net ordering. It is the repo's single source of truth for
   rotation-and-side-aware pad placement and it is ``sin``/``cos`` on
   ``math.pi``; libm and Rust's intrinsics are not bit-identical across
   platforms for transcendentals, so porting it would inject a divergence into
   a *sort key*, where fixture differentials are least likely to catch it. The
   ordering logic built on those coordinates IS ported.

``compute_dsn_schema_hash`` is likewise called here rather than reimplemented:
it was already a Rust delegation shim (``temper-dsn``) before this migration,
and ``io/dsn_validator.py`` fails closed on that hash — a second implementation
of it would be exactly the drift the validator exists to catch.

Recorded deviation: a ``positions`` array with fewer rows than there are
components now raises ``IndexError`` at construction rather than at
``export_placement``, because the shim materializes the array once up front.
The exception type and message are numpy's, unchanged.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, TypeAlias

import numpy as np
from temper_io_types import DSNExporterCore

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.io.dsn import DSNExpression, dsn_list

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

    # TraceData moved to _kicad_types (Rust-backed) in the de-kiutils
    # migration; kicad_parser no longer carries it.
    from temper_placer.io._kicad_types import TraceData

__all__ = ["DSNExporter"]


def _natural_sort_key(s: str) -> list:
    """Sort key that ensures natural numeric ordering (e.g., 'pin10' > 'pin2')."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", s)]


class DSNExporter:
    """Exporter for KiCad PCB to SPECCTRA DSN format."""

    def __init__(
        self,
        board: Board,
        netlist: Netlist,
        positions: Array | None = None,
        rotations: Array | None = None,
        deterministic: bool = True,
    ):
        self.board = board
        self.netlist = netlist
        self.positions = positions
        self.deterministic = deterministic

        # Convert rotations to indices (0-3) if provided as logits/one-hot
        if rotations is not None:
            if rotations.ndim == 2:
                self.rotation_indices: Array | None = np.argmax(rotations, axis=1)
            else:
                self.rotation_indices = rotations
        else:
            self.rotation_indices = None

        n = len(netlist.components)

        rot_indices = (
            None
            if self.rotation_indices is None
            else [int(self.rotation_indices[i]) for i in range(n)]
        )
        pos = (
            None
            if positions is None
            else [(float(positions[i, 0]), float(positions[i, 1])) for i in range(n)]
        )

        # Only the non-deterministic net ordering reads pad world geometry, so
        # only that path pays for computing it.
        pin_world = None
        if not deterministic:
            pin_world = [
                [pin_world_position(pin, comp) for pin in comp.pins]
                for comp in netlist.components
            ]

        self._core = DSNExporterCore(
            board,
            netlist,
            positions=pos,
            rotation_indices=rot_indices,
            deterministic=deterministic,
            pin_world_positions=pin_world,
        )

    @property
    def _center_offsets(self) -> list[tuple[float, float]]:
        """Offset from footprint origin to bounding box center, per component."""
        return self._core.center_offsets

    def _compute_center_offsets(self) -> list[tuple[float, float]]:
        return self._core.center_offsets

    def _natural_sort_key(self, s: str) -> tuple:
        """Natural sort key: splits into text and number parts for sorting."""
        return tuple(_natural_sort_key(s))

    def export_structure(self, all_layers_signal: bool = True) -> DSNExpression:
        """Export the structure section (layers, boundaries, keepouts)."""
        return self._core.export_structure(all_layers_signal)

    def export_library(self) -> DSNExpression:
        """Export the library section (footprints and padstacks)."""
        return self._core.export_library()

    def export_placement(self) -> DSNExpression:
        """Export the placement section (component instances)."""
        return self._core.export_placement()

    def export_network(
        self,
        use_net_classes: bool = True,
        exclude_nets: set[str] | None = None,
    ) -> DSNExpression:
        """Export the network section (nets, pins, and net classes)."""
        return self._core.export_network(
            use_net_classes,
            None if exclude_nets is None else sorted(exclude_nets),
        )

    def export_wiring(self, traces: list[TraceData]) -> DSNExpression:
        """Export the wiring section (existing traces)."""
        return self._core.export_wiring(traces)

    def export_pcb(
        self,
        pcb_name: str = "temper",
        traces: list[TraceData] | None = None,
        exclude_nets: set[str] | None = None,
    ) -> DSNExpression:
        """Export the full PCB design."""
        schema_hash = None
        if self.deterministic:
            from temper_placer.io.dsn_schema import compute_dsn_schema_hash

            schema_hash = compute_dsn_schema_hash(self.board, self.netlist)

        return self._core.export_pcb(
            pcb_name,
            traces,
            None if exclude_nets is None else sorted(exclude_nets),
            schema_hash,
        )


# Re-exported so `from temper_placer.io.dsn_exporter import dsn_list` keeps
# working for the callers and tests that reached through this module.
__all__ += ["DSNExpression", "dsn_list"]
