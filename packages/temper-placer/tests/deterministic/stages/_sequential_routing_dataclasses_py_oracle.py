"""VERBATIM pre-migration oracle for ``deterministic/stages/sequential_routing_dataclasses.py``.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing_dataclasses.py``
at the dispatch base (origin/main). Do NOT edit: this file is the Python arm
of the differential. If it drifts, the differential proves nothing.

The module is a single plain dataclass with three defaults. The migration
turns it into a pyo3 pyclass with identical construction, field access,
default chain, repr, and equality semantics.
"""

from dataclasses import dataclass


@dataclass
class DiffPairConfig:
    """Configuration for a differential pair."""

    net_pos: str  # Positive net name (e.g., "USB_D+")
    net_neg: str  # Negative net name (e.g., "USB_D-")
    spacing_mm: float = 0.15  # Target spacing between traces
    coupling_tolerance_mm: float = 0.5  # Max allowed divergence
    max_skew_mm: float = 0.5  # Max length mismatch
