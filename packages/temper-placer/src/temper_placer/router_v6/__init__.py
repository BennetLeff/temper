"""
Router V6: Topological-First Architecture

See docs/architecture/ROUTER_V6_TOPOLOGICAL_ARCHITECTURE.md
"""

from temper_placer.router_v6.diff_pair_inference import (
    DiffPair,
    infer_differential_pairs,
)
from temper_placer.router_v6.stage0_data import (
    DesignRules,
    LayerInfo,
    NetClassRules,
    ParsedPCB,
    StackupInfo,
)

__all__ = [
    "ParsedPCB",
    "DesignRules",
    "NetClassRules",
    "StackupInfo",
    "LayerInfo",
    "DiffPair",
    "infer_differential_pairs",
]
