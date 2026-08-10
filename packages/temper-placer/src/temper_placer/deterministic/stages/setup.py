"""Setup stages: DRC-oracle setup and net-class setup.

The stage orchestration is implemented in Rust (``temper-orchestration``'s
``DrcOracleSetupStage`` / ``NetClassSetupStage``, Phase D batch D1 of the
Rust Orchestration Engine plan 2026-08-09-001). This module keeps the public
API (the ``Stage`` subclasses, their constructors, ``name`` and the
``SetupStage`` alias) and delegates ``run`` across the FFI once per stage
call. The differential oracle for the pre-migration implementation is pinned
VERBATIM in ``tests/deterministic/_setup_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class DRCOracleSetupStage(Stage):
    """Setup stage for initializing DRCOracle and other common utilities.

    Args:
        design_rules: Design rules configuration
        parsed_pads: Optional list of PadData from kicad_parser. If provided,
            these are used for DRC oracle instead of computing from placements.
            This ensures DRC uses the actual KiCad positions, not optimized placements.
    """

    def __init__(self, design_rules=None, parsed_pads=None):
        self.design_rules = design_rules
        self.parsed_pads = parsed_pads

    @property
    def name(self) -> str:
        return "drc_oracle_setup"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_drc_oracle_setup(state, self.design_rules, self.parsed_pads)


class NetClassSetupStage(Stage):
    """Setup stage to apply net class mapping from config to netlist.

    This stage should run early in the pipeline to ensure net classes
    are properly assigned before routing decisions are made.
    """

    def __init__(self, net_classes=None):
        self.net_classes = net_classes

    @property
    def name(self) -> str:
        return "net_class_setup"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_net_class_setup(state, self.net_classes)


# Alias for backward compatibility
SetupStage = DRCOracleSetupStage
