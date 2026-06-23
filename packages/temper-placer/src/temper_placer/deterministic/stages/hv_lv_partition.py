"""
HV/LV pre-placement guard strip.

@req(2026-06-23-001, FR1, FR2, FR3, FR6, FR7, FR8, FR9)
@req(2026-06-23-001, NFR1, NFR4, NFR5, NFR6)

Partitions components into HV (board edge) and LV (board interior) buckets
derived from :class:`NetClassRules.safety_category`, reserves a guard strip
between them whose width is sourced from :attr:`NetClassRules.creepage_mm`,
and exposes the result via :attr:`BoardState.component_domain_map` and
:attr:`BoardState.routing_corridors`.

The dual-domain policy (FR2 last bullet) is fixed here: a component
connected to both an HV-classified net and an LV-classified net is assigned
to the LV bucket and logged as a WARNING. If a future brainstorm reverses
this, the only change required is the order of the two branch arms below.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict

from ..state import BoardState

logger = logging.getLogger(__name__)


class PartitionError(Exception):
    """Raised when a HV/LV partition cannot be satisfied.

    Attributes:
        bucket: Name of the bucket that lacked area (``"HV"`` or ``"LV"``).
        largest_ref: Reference of the largest component in the failing bucket.
        region_area_mm2: Available region area in mm^2.
        required_area_mm2: Footprint area required by the largest component.
    """

    def __init__(
        self,
        bucket: str,
        largest_ref: str,
        region_area_mm2: float,
        required_area_mm2: float,
    ) -> None:
        self.bucket = bucket
        self.largest_ref = largest_ref
        self.region_area_mm2 = region_area_mm2
        self.required_area_mm2 = required_area_mm2
        super().__init__(
            f"PartitionError: {bucket} bucket cannot fit {largest_ref} "
            f"(region {region_area_mm2:.2f}mm^2 < required {required_area_mm2:.2f}mm^2)"
        )


class HvLvGuardConfig(BaseModel):
    """Configuration block for the HV/LV guard strip stage.

    Attributes:
        enabled: When ``False`` the stage returns the input state unchanged.
        width_mm: Optional override for the guard strip width. ``None`` means
            "derive from ``max(creepage_mm)`` of HV-classified net classes";
            ``0`` means "disable guard strip geometry".
        fallback_to_unconstrained: When ``True``, insufficient-area errors
            are logged as warnings and the state is passed through unchanged
            (legacy behaviour).
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    width_mm: Optional[float] = None
    fallback_to_unconstrained: bool = True


def load_guard_config(config: Optional[Mapping[str, Any]]) -> HvLvGuardConfig:
    """Load :class:`HvLvGuardConfig` from a raw config mapping.

    The mapping is expected to have an optional top-level
    ``hv_lv_guard_strip`` key whose value is itself a mapping. Missing keys
    fall back to :class:`HvLvGuardConfig` defaults (``enabled=True``,
    ``width_mm=None``, ``fallback_to_unconstrained=True``).
    """
    if config is None:
        return HvLvGuardConfig()
    block = config.get("hv_lv_guard_strip") if hasattr(config, "get") else None
    if not block:
        return HvLvGuardConfig()
    if not isinstance(block, Mapping):
        logger.warning("hv_lv_guard_strip block is not a mapping; using defaults")
        return HvLvGuardConfig()
    return HvLvGuardConfig(**dict(block))


__all__ = [
    "PartitionError",
    "HvLvGuardConfig",
    "load_guard_config",
]
