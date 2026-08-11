"""Connectivity validation stage.

Phase D batch D6 of the Rust Orchestration Engine plan (2026-08-09-001): the
``run()`` orchestration (the no-oracle guard, the drc-oracle geometry
extraction, the per-net grouping, the plane-net / empty-net / NoNet skips, the
``_validate_net_connectivity`` marshalling + UnionFind kernel call, the
``ConnectivityViolation`` construction, the summary logging and the
``connectivity_violations`` write) is implemented in Rust
(``temper-orchestration``'s ``ConnectivityValidationStage`` /
``run_connectivity_validation``), crossing the FFI once per stage call. This
module keeps the public API unchanged: the ``ConnectivityValidationStage`` /
``ConnectivityViolation`` / ``ConnectivityValidationError`` names (the
violation dataclass and the exception class stay Python; the Rust stage
constructs the violations through FFI and surfaces the raise decision through
the shim's exception type). The pre-migration implementation is pinned
VERBATIM as ``tests/deterministic/_connectivity_validation_run_py_oracle.py``.
"""

import logging
from dataclasses import dataclass

import temper_orchestration as _to

from temper_placer.router_v6.constraints_geometry import Point

from ..state import BoardState
from .base import Stage

logger = logging.getLogger(__name__)


@dataclass
class ConnectivityViolation:
    """Represents a connectivity error on the PCB."""

    type: str  # "orphan_island", "dangling_track", "unconnected_pad"
    net: str
    location: Point
    description: str


class ConnectivityValidationError(Exception):
    """Raised when connectivity violations exceed configured thresholds."""

    pass


class ConnectivityValidationStage(Stage):
    """
    Validates net connectivity, detecting unconnected pads,
    dangling tracks, and isolated copper islands.
    """

    def __init__(self, fail_on_violations: bool = False):
        self.fail_on_violations = fail_on_violations

    @property
    def name(self) -> str:
        return "connectivity_validation"

    def run(self, state: BoardState) -> BoardState:
        """Run the per-net connectivity validation in Rust (Phase D D6) and
        surface the raise decision as the module's
        ``ConnectivityValidationError``."""
        out_state, message = _to.run_connectivity_validation(
            state, self.fail_on_violations
        )
        if message is not None:
            raise ConnectivityValidationError(message)
        return out_state
