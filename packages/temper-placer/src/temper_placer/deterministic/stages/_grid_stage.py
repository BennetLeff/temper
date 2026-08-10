"""The clearance-grid stage orchestration.

The stage orchestration is implemented in Rust (``temper-orchestration``'s
``ClearanceGridStage``, Phase D batch D3 of the Rust Orchestration Engine
plan 2026-08-09-001): the pad-collection loop, the per-net blocking pass,
the pre-route HV creepage-expansion pass, the U3 fence invocation and the
EXP-13 exclusion-zone blocking all run Rust-side, crossing the FFI once per
stage call. The leaf objects stay Python -- the ``ClearanceGrid`` data type
(``_grid_core.py``, whose cell-rasterisation compute is already in
temper-geometry's ``grid_raster.rs``) and the ``_grid_hv`` / ``_grid_fence``
helpers -- and are called by the Rust stage through the same Python modules.
This module keeps the public API (the ``ClearanceGridStage`` Stage subclass,
its constructor and ``name``) and delegates ``run`` across the FFI. The
differential oracle for the pre-migration implementation is pinned VERBATIM
in ``tests/deterministic/_grid_stage_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class ClearanceGridStage(Stage):
    def __init__(
        self,
        cell_size_mm: float = 0.5,
        layer_count: int = 2,
        pad_sizes: dict | None = None,
        max_clearance_mm: float = 2.5,
        net_class_clearances: dict[str, float] | None = None,
        net_classes: dict[str, str] | None = None,
        pth_mask_expansion_mm: float = 0.15,
        smd_mask_expansion_mm: float = 0.10,
        inner_layer_clearance_mm: float = 0.5,
        hv_exclusion_zones: list | None = None,
        default_trace_width_mm: float = 0.25,
    ):
        """Initialize clearance grid stage.

        Args:
            cell_size_mm: Grid cell size in mm
            layer_count: Number of copper layers
            pad_sizes: Optional dict of pad sizes
            max_clearance_mm: Maximum clearance to use for blocking (fallback if net class not found)
            net_class_clearances: Optional mapping of net class name to clearance in mm
            net_classes: Optional mapping of net name to net class name (for per-net clearance lookup)
            pth_mask_expansion_mm: Mask expansion for PTH pads (default: 0.15mm)
            smd_mask_expansion_mm: Mask expansion for SMD pads (default: 0.10mm)
            inner_layer_clearance_mm: Max clearance for inner layers (default: 0.5mm).
                Inner layers don't need creepage clearance since they're encapsulated
                in FR4. This prevents high-voltage PTH pads from blocking escape routes on
                inner layers with their full surface clearance (e.g., 6mm -> 0.5mm).
            hv_exclusion_zones: List of HVExclusionZone configs for signal avoidance.
                EXP-13: Zones where specified nets must not route (blocked on all layers).
            default_trace_width_mm: Default trace width to account for in blocking (Minkowski sum).
                Since A* treats the agent as a point, we must expand obstacles by the agent's radius.
        """
        self.cell_size_mm = cell_size_mm
        self.layer_count = layer_count
        self.pad_sizes = pad_sizes or {}
        self.max_clearance_mm = max_clearance_mm
        self.net_class_clearances = net_class_clearances or {}
        self.net_classes = net_classes or {}
        self.pth_mask_expansion_mm = pth_mask_expansion_mm
        self.smd_mask_expansion_mm = smd_mask_expansion_mm
        self.inner_layer_clearance_mm = inner_layer_clearance_mm
        self.hv_exclusion_zones = hv_exclusion_zones or []
        self.default_trace_width_mm = default_trace_width_mm

    @property
    def name(self) -> str:
        return "clearance_grid"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_clearance_grid_stage(
            state,
            self.cell_size_mm,
            self.layer_count,
            self.pad_sizes,
            self.max_clearance_mm,
            self.net_class_clearances,
            self.net_classes,
            self.pth_mask_expansion_mm,
            self.smd_mask_expansion_mm,
            self.inner_layer_clearance_mm,
            self.hv_exclusion_zones,
            self.default_trace_width_mm,
        )
