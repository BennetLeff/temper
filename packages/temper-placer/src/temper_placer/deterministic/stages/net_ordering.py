"""Stage that determines the order in which nets are routed.

The stage orchestration is implemented in Rust (``temper-orchestation``'s
``NetOrderingStage``, Phase D batch D1 of the Rust Orchestration Engine plan
2026-08-09-001): it reads ``netlist``/``loops`` from the state and delegates
the ordering compute to the already-Rust ``temper_rust_router.order_nets_py``
kernel (the ``router_v6.net_ordering.order_nets`` marshalling shim). This
module keeps the public API (the ``Stage`` subclass, its constructor and
``name``) and delegates ``run`` across the FFI once per stage call. The
differential oracle for the pre-migration implementation is pinned VERBATIM
in ``tests/deterministic/_net_ordering_py_oracle.py``.

EXP-6: Supports explicit net priorities from config to route
critical nets (USB, SPI) first when board is least congested.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class NetOrderingStage(Stage):
    """Stage that determines the order in which nets are routed."""

    def __init__(self, net_priority: dict[str, int] | None = None):
        """Initialize net ordering stage.

        Args:
            net_priority: Optional dict mapping net names to priority (1=highest, 5=default).
                         Lower numbers route first.
        """
        self.net_priority = net_priority or {}

    @property
    def name(self) -> str:
        return "net_ordering"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_net_ordering(state, self.net_priority)
