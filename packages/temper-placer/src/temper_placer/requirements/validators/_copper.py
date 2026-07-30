"""Copper geometry for the REQ-SAFE-01 clearance/creepage check.

Split out of ``clearance.py`` so that module stays under the repo's
1000-line file cap; this is the "how far apart is the copper" half, and
``clearance.py`` is the "which pairs, against which requirement, reported
how" half. Both are internal to this package.

The measurement itself, and why it replaced origin-to-origin distance, is
documented in ``clearance``'s module docstring. Everything here is built on
the single shared pad model in :mod:`temper_placer.core.pad_geometry` -- no
second geometry implementation exists or should be added.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from temper_placer.core.pad_geometry import (
    DEFAULT_ROUNDRECT_RATIO,
    pad_bounding_radius,
    pad_pair_distance,
)

from ._geometry import _distance

if TYPE_CHECKING:
    # Annotation-only, under `from __future__ import annotations`. Imported
    # lazily because ``clearance`` imports this module at runtime, and
    # VoltageDomain is only ever used here as a dict key / parameter type.
    from .clearance import VoltageDomain

logger = logging.getLogger(__name__)

# Creepage models, in decreasing order of fidelity. Recorded on every creepage
# violation (``ClearanceViolation.creepage_model``) so a reader can never
# mistake the conservative model for a real surface-path measurement.
CREEPAGE_MODEL_UNBROKEN_SURFACE = "unbroken-surface (exact: geodesic == straight line)"
CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND = (
    "straight-line lower bound (CONSERVATIVE: board has cutouts, "
    "slot-aware surface pathing not implemented)"
)


# =============================================================================
# Copper geometry
# =============================================================================


@dataclass(frozen=True)
class _Pad:
    """One pad's copper, resolved into board coordinates."""

    ref: str
    number: str
    net: str | None
    cx: float
    cy: float
    width: float
    height: float
    shape: str
    roundrect_ratio: float
    rotation_rad: float

    @property
    def label(self) -> str:
        return f"{self.ref}.{self.number}({self.net})" if self.net else f"{self.ref}.{self.number}"


def _rotate(x: float, y: float, theta_rad: float) -> tuple[float, float]:
    """R(-theta) -- KiCad's actual footprint-rotation convention: a
    footprint's ``(at X Y ANGLE)`` rotates each pad's stored local offset
    *clockwise* by ANGLE to reach its absolute board position. Verified
    directly against ``pcbnew`` (KiCad's own placement engine, not a
    re-derivation): a footprint at 37 deg with local pad offset (10, 4)
    places that pad at (10.393615, -2.823608) mm -- the R(-theta)
    prediction to 6 decimal places. The standard-CCW R(+theta) this
    function previously used predicts a different point, (5.579095,
    9.212693), and was wrong -- see
    docs/evidence/2026-07-30-generic-separation-writer-frame-fix.md.

    Using the *same* sign as ``io/_parse_modules.py``'s
    ``Component.initial_position`` (``fp.position + R(-theta) *
    center_offset``, fixed to match this) is what makes
    ``world_pad = position + R(-theta) * local_offset`` consistent with the
    ``position`` this validator is handed: substituting
    ``local_offset = pad_local - center_offset`` recovers
    ``fp.position + R(-theta) * pad_local`` exactly, and both R(-theta)
    factors need the SAME sign for the ``center_offset`` terms to cancel --
    self-consistency alone (matching sign between the two call sites)
    doesn't make the result correct if that shared sign is itself wrong,
    which it was: on ``pcb/temper.kicad_pcb``, 18 real components (C1, C24,
    C25, C4, C8, F1, J1, K3, PS1, R1, R11, R12, R13, R60, RT1, T1, U1, U6)
    sit at a 90/270 degree rotation with a nonzero ``center_offset``, and
    R(+theta) computed each of their pads at the wrong point -- the
    ``+theta``/``-theta`` conventions only coincide at 0/180 degrees.
    """
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c + y * s, -x * s + y * c)


def _component_pads(comp: dict[str, Any]) -> list[_Pad]:
    """Resolve a placement component's ``pads`` into board-coordinate pads.

    Returns ``[]`` when the component carries no pad data -- callers fall
    back to the (optimistic) origin point model and must account for it.
    """
    raw = comp.get("pads")
    if not raw:
        return []
    ref = str(comp.get("ref", "?"))
    ox, oy = comp["position"]
    comp_rot_rad = math.radians(float(comp.get("rotation_deg", 0.0)))

    pads: list[_Pad] = []
    for i, p in enumerate(raw):
        dx, dy = p.get("offset", (0.0, 0.0))
        rx, ry = _rotate(float(dx), float(dy), comp_rot_rad)
        pad_rot_rad = comp_rot_rad + math.radians(float(p.get("pad_rotation_deg", 0.0)))
        pads.append(
            _Pad(
                ref=ref,
                number=str(p.get("number", i)),
                net=p.get("net"),
                cx=ox + rx,
                cy=oy + ry,
                width=float(p.get("width", 1.0)),
                height=float(p.get("height", 1.0)),
                shape=str(p.get("shape", "rect")),
                roundrect_ratio=float(p.get("roundrect_ratio", DEFAULT_ROUNDRECT_RATIO)),
                rotation_rad=pad_rot_rad,
            )
        )
    return pads


class _CopperModel:
    """Per-placement pad geometry, with memoized per-pair distances.

    Exists so :func:`verify_iec60335_compliance` -- which walks the same
    boundary twice (clearance + creepage) and usually twice more (basic +
    reinforced tiers) -- pays for each pair's exact distance once instead of
    four times.
    """

    def __init__(self, placement: dict[str, Any]) -> None:
        self._pads: dict[str, list[_Pad]] = {}
        self._origin: dict[str, tuple[float, float]] = {}
        self._reach: dict[str, float] = {}
        self._dist_cache: dict[tuple[str, Any, str, Any], tuple[float, str, str]] = {}
        self.components_without_pads: list[str] = []

        for comp in placement.get("components", []):
            ref = str(comp.get("ref", "?"))
            self._origin[ref] = tuple(comp["position"])  # type: ignore[assignment]
            pads = _component_pads(comp)
            self._pads[ref] = pads
            if not pads:
                self.components_without_pads.append(ref)
                self._reach[ref] = 0.0
                continue
            ox, oy = self._origin[ref]
            self._reach[ref] = max(
                math.hypot(p.cx - ox, p.cy - oy)
                + pad_bounding_radius(p.width, p.height, p.shape, p.roundrect_ratio)
                for p in pads
            )

    # -- pad selection -----------------------------------------------------

    def pads_in_domain(
        self, ref: str, domain: VoltageDomain, nets_domain: dict[str, VoltageDomain]
    ) -> list[_Pad]:
        """Pads of *ref* whose own net is classified into *domain*.

        Falls back to **all** of the component's pads when none of its pads'
        nets resolve to *domain*. That happens when a component is a member
        of the domain by way of the compiled netlist while the board file's
        own pad-net annotation disagrees (stale or absent). Using every pad
        is the conservative choice -- it can only shorten the reported
        distance, never lengthen it -- and is counted in
        ``stats["pairs_unrestricted_pads"]`` rather than hidden.
        """
        pads = self._pads.get(ref, [])
        matching = [p for p in pads if p.net is not None and nets_domain.get(p.net) == domain]
        return matching if matching else pads

    def has_pads(self, ref: str) -> bool:
        return bool(self._pads.get(ref))

    def domain_restricted(
        self, ref: str, domain: VoltageDomain, nets_domain: dict[str, VoltageDomain]
    ) -> bool:
        pads = self._pads.get(ref, [])
        return any(p.net is not None and nets_domain.get(p.net) == domain for p in pads)

    # -- geometry ----------------------------------------------------------

    @staticmethod
    def _spec(pad: _Pad) -> tuple[float, float, str, float, float, float, float]:
        """``pad_geometry.pad_pair_distance``'s pad tuple."""
        return (
            pad.width,
            pad.height,
            pad.shape,
            pad.cx,
            pad.cy,
            pad.rotation_rad,
            pad.roundrect_ratio,
        )

    def lower_bound(self, ref_a: str, ref_b: str) -> float:
        """Cheap, sound lower bound on copper-to-copper distance.

        ``origin_distance - reach_a - reach_b``: no copper of A can be more
        than ``reach_a`` from A's origin, likewise B, so the true gap cannot
        be smaller than this. Used only to skip pairs that provably cannot
        violate -- never to report a number. Domain restriction only removes
        pads, which can only *increase* the true distance, so this bound
        stays valid for the restricted sets too.
        """
        if ref_a == ref_b:
            return -math.inf
        pa, pb = self._origin[ref_a], self._origin[ref_b]
        return _distance(pa, pb) - self._reach[ref_a] - self._reach[ref_b]

    def copper_distance(
        self,
        ref_a: str,
        domain_a: VoltageDomain,
        ref_b: str,
        domain_b: VoltageDomain,
        nets_domain: dict[str, VoltageDomain],
    ) -> tuple[float, str, str]:
        """Return ``(distance_mm, geometry_model, closest_pads_label)``.

        ``geometry_model`` is ``"copper"`` when both sides had real pad
        geometry and ``"origin"`` when either did not (the optimistic
        legacy proxy -- reported, not silently substituted).
        """
        key = (ref_a, domain_a, ref_b, domain_b)
        cached = self._dist_cache.get(key)
        if cached is not None:
            return cached

        pads_a = self.pads_in_domain(ref_a, domain_a, nets_domain)
        pads_b = self.pads_in_domain(ref_b, domain_b, nets_domain)

        if not pads_a or not pads_b:
            result = (
                _distance(self._origin[ref_a], self._origin[ref_b]),
                "origin",
                f"{ref_a} <-> {ref_b} (origins; no pad geometry)",
            )
            self._dist_cache[key] = result
            return result

        best = math.inf
        best_label = ""
        for pa in pads_a:
            ra = pad_bounding_radius(pa.width, pa.height, pa.shape, pa.roundrect_ratio)
            for pb in pads_b:
                if pa is pb:
                    continue  # a pad has no clearance to itself
                rb = pad_bounding_radius(pb.width, pb.height, pb.shape, pb.roundrect_ratio)
                centre_gap = math.hypot(pa.cx - pb.cx, pa.cy - pb.cy) - ra - rb
                if centre_gap >= best:
                    continue  # provably cannot beat the incumbent
                d = pad_pair_distance(self._spec(pa), self._spec(pb))
                if d < best:
                    best = d
                    best_label = f"{pa.label} <-> {pb.label}"

        if best is math.inf:
            result = (
                _distance(self._origin[ref_a], self._origin[ref_b]),
                "origin",
                f"{ref_a} <-> {ref_b} (origins; no distinct pad pair)",
            )
        else:
            result = (best, "copper", best_label)
        self._dist_cache[key] = result
        return result


def _board_cutouts(placement: dict[str, Any]) -> list[Any]:
    """Interior ``Edge.Cuts`` loops (slots/cutouts) declared by *placement*.

    ``placement["board"]["surface_cutouts"]`` is a list of rings, each a list
    of ``(x, y)`` points, produced by the caller from the real board outline.
    An absent key means "the caller did not supply board geometry", which is
    treated the same as "no cutouts" -- see :func:`check_creepage_path` for
    why that is the safe direction either way.
    """
    board = placement.get("board")
    if not isinstance(board, dict):
        return []
    cutouts = board.get("surface_cutouts") or []
    return list(cutouts)


def _creepage_from_clearance(straight_mm: float, cutouts: list[Any]) -> tuple[float, str]:
    """Convert a straight-line copper gap into a creepage figure + its model.

    Creepage is the shortest path *along the insulating surface*. On an
    unbroken surface the surface geodesic between two coplanar points **is**
    the straight line, so with no cutouts this is exact, not an
    approximation -- ``CREEPAGE_MODEL_UNBROKEN_SURFACE``.

    With a cutout present the true surface path must detour around it and is
    therefore strictly longer. Slot-aware surface pathing is **not
    implemented here** (see :func:`check_creepage_path`); the straight-line
    figure is returned as an explicit *lower bound* -- safe (it can only
    over-report violations, never mask one) but pessimistic -- tagged
    ``CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND`` on every violation it
    produces, and logged at WARNING. It is never silently identical to
    clearance: the two differ by their recorded model as well as by their
    thresholds.
    """
    if not cutouts:
        return straight_mm, CREEPAGE_MODEL_UNBROKEN_SURFACE
    logger.warning(
        "REQ-SAFE-01 creepage: the board declares %d Edge.Cuts cutout(s)/slot(s), "
        "but slot-aware surface pathing is not implemented. Reported creepage is "
        "the straight-line CLEARANCE distance -- a conservative LOWER BOUND on the "
        "true surface path. Violations near a slot may be false positives; no real "
        "violation can be masked. Implement surface pathing before relying on these "
        "numbers to justify a placement.",
        len(cutouts),
    )
    return straight_mm, CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND

