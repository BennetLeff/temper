from dataclasses import dataclass


@dataclass
class DiffPairConfig:
    """Configuration for a differential pair."""

    net_pos: str  # Positive net name (e.g., "USB_D+")
    net_neg: str  # Negative net name (e.g., "USB_D-")
    spacing_mm: float = 0.15  # Target spacing between traces
    coupling_tolerance_mm: float = 0.5  # Max allowed divergence
    max_skew_mm: float = 0.5  # Max length mismatch
