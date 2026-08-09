"""
Router V6 Stage 1.1: Identify Dense Packages

Identifies high-pin-count components requiring escape routing strategies.
Part of temper-wpwf (Stage 1 - Pin Escape Planning)

Wave 4 migration note: the per-component classifiers (``_estimate_pitch`` /
``_infer_package_type``) now delegate to ``temper_geometry``'s
``dense_package_detection`` kernels
(``packages/temper-geometry/src/dense_package_detection.rs``); the
``DensePackage`` dataclass, the ``Component``/``Pin`` object access, and the
``identify_dense_packages`` loop stay here.  See
``packages/temper-geometry/VERIFICATION.md`` for the full writeup.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg

from temper_placer.core.netlist import Component


@dataclass
class DensePackage:
    """A high-pin-count component requiring escape routing."""

    component: Component
    pin_count: int
    pitch_mm: float  # Pin-to-pin spacing
    package_type: str  # "QFN", "BGA", "TQFP", "SOIC", etc.
    requires_escape: bool  # True if pitch < 0.5mm (dense)

    @property
    def is_bga(self) -> bool:
        """True if this is a BGA (Ball Grid Array) package."""
        return "BGA" in self.package_type.upper()

    @property
    def is_qfn(self) -> bool:
        """True if this is a QFN (Quad Flat No-lead) package."""
        return "QFN" in self.package_type.upper()


def identify_dense_packages(
    components: list[Component],
    dense_threshold_mm: float = 0.5,
    min_pin_count: int = 16,
) -> list[DensePackage]:
    """
    Identify components requiring escape routing strategies.

    A package is considered "dense" if:
    - Pin pitch < threshold (default 0.5mm = fine pitch)
    - Pin count >= min_pin_count (default 16 pins)

    Args:
        components: List of Component instances from ParsedPCB
        dense_threshold_mm: Maximum pitch considered "dense" (default 0.5mm)
        min_pin_count: Minimum pins to be considered (default 16)

    Returns:
        List of DensePackage instances requiring escape planning.

    Example:
        >>> comp = Component(ref="U1", footprint="QFN-48_0.5mm", bounds=(7, 7), pins=[...])
        >>> dense = identify_dense_packages([comp])
        >>> dense[0].requires_escape
        True
    """
    dense_packages = []

    for comp in components:
        # Skip components with too few pins
        pin_count = len(comp.pins)
        if pin_count < min_pin_count:
            continue

        # Estimate pitch from footprint name or calculate from geometry
        pitch_mm = _estimate_pitch(comp)

        # Infer package type from footprint name
        package_type = _infer_package_type(comp)

        # Determine if escape routing is required
        requires_escape = pitch_mm <= dense_threshold_mm or package_type in ["BGA", "FBGA", "LFBGA"]

        dense_packages.append(
            DensePackage(
                component=comp,
                pin_count=pin_count,
                pitch_mm=pitch_mm,
                package_type=package_type,
                requires_escape=requires_escape,
            )
        )

    return dense_packages


def _estimate_pitch(comp: Component) -> float:
    """
    Estimate pin pitch from footprint name or pin positions.

    Tries in order:
    1. Parse from footprint name (e.g., "QFN-48_0.5mm" -> 0.5mm)
    2. Calculate from actual pin positions

    Args:
        comp: Component instance

    Returns:
        Estimated pitch in mm (default 0.65mm if unknown)
    """
    positions = [c for p in comp.pins for c in p.position]
    return _tg.estimate_pitch_py(comp.footprint, positions)


def _infer_package_type(comp: Component) -> str:
    """
    Infer package type from footprint name.

    Args:
        comp: Component instance

    Returns:
        Package type string ("QFN", "BGA", "TQFP", "SOIC", etc.)
    """
    return _tg.infer_package_type_py(comp.footprint)
