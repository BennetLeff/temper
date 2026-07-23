"""Multi-layer creepage-aware clearance grid stage.

Public API re-exports from internal modules:
  _grid_core   → ClearanceGrid
  _grid_hv     → ConfigError, effective_creepage, hv_pad_set,
                  INTERNAL_LAYER_CREEPAGE_FACTOR, OUTER_COPPER_LAYERS
  _grid_fence  → FenceViolation, check_clearance_grid_conservatism,
                  check_clearance_grid_perf_budget
  _grid_stage  → ClearanceGridStage
"""

from ._grid_core import ClearanceGrid
from ._grid_fence import (
    _EXPANSION_LOG,
    FenceViolation,
    check_clearance_grid_conservatism,
    check_clearance_grid_perf_budget,
)
from ._grid_hv import (
    INTERNAL_LAYER_CREEPAGE_FACTOR,
    OUTER_COPPER_LAYERS,
    ConfigError,
    _layer_index_to_name,
    effective_creepage,
    hv_pad_set,
)
from ._grid_stage import ClearanceGridStage

__all__ = [
    "ClearanceGrid",
    "ClearanceGridStage",
    "ConfigError",
    "_EXPANSION_LOG",
    "FenceViolation",
    "INTERNAL_LAYER_CREEPAGE_FACTOR",
    "OUTER_COPPER_LAYERS",
    "_layer_index_to_name",
    "check_clearance_grid_conservatism",
    "check_clearance_grid_perf_budget",
    "effective_creepage",
    "hv_pad_set",
]
