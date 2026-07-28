"""Mains<->SELV physical isolation-barrier constraint for CP-SAT placement.

**The gap this closes.** ``docs/evidence/2026-07-28-isolation-keepout.md``
(and ``scripts/check_isolation_keepout.py``, the fail-closed gate it added)
established that the *current* board placement cannot have a compliant
keepout barrier drawn on it at all -- HV and SELV components interleave in
a checkerboard across the full board. That analysis never asked the CP-SAT
placer to *re-solve* placement with the barrier as a constraint; it only
asked whether one could be drawn post-hoc on the placement that already
existed. This module is that re-solve: a HARD constraint that a
board-spanning, copper-free corridor exists between the HV and SELV
domains, fed into the same ``domain_clearance.py`` classification
machinery this codebase already uses for domain-crossing clearance.

**Why not the existing ``SeparatedConstraint`` machinery ``domain_clearance.py``
uses.** An earlier version of this module registered the corridor as a
fixed virtual ``ComponentVars`` entry and emitted one ``SeparatedConstraint``
per domain-only component against it, reusing ``handlers/separated.py``
unmodified. That is the WRONG semantics for a barrier: ``SeparatedConstraint``
encodes "at least the margin on *either* side" -- exactly what you want
between two components that could legitimately swap places, but it does
**not** stop two HV-only components and two SELV-only components all
piling up on the *same* side of the corridor while each individually
"clears" it (caught by ``test_barrier_separates_domain_only_components_sat``
during development: the solver put both a HV-only and a SELV-only
component 5mm apart on the corridor's right side, satisfying "not
overlapping the corridor" for both while satisfying nothing about actual
domain separation). The barrier needs a **directional** split -- HV-only
components strictly on one named side, SELV-only strictly on the other --
which is a single one-sided linear inequality per component, not a
disjunction. This module encodes that directly (``model.model_ref.Add``,
assumption-guarded exactly like ``CpSatModel.set_bounds`` guards each edge
margin), rather than forcing a symmetric two-component constraint type to
express an inherently asymmetric requirement. The corridor's own extent is
therefore also just two integer constants (``barrier_lo_units``,
``barrier_hi_units``) -- no virtual ``ComponentVars`` entry is needed at
all once the constraint is directional.

**Isolators need a different, pad-level encoding.** The 8 manifest-declared
isolators (components whose own pads bridge HV and SELV -- the barrier's
*intended* crossing points) must be allowed to have their *courtyard*
overlap the corridor (that is their function: a Y-cap, opto, gate driver,
relay, transformer or CT physically straddles the isolation gap). But
``scripts/check_isolation_keepout.py`` does not special-case isolators at
all -- it fails on *any* pad of *any* component found inside the barrier
polygon, unconditionally (see its "NO INTRUSION" check). So "the courtyard
may straddle" is necessary but not sufficient: each isolator's own
HV-classified pads and SELV-classified pads individually must land on
opposite, correct sides of the corridor -- which is possible if and only if
the real, physical edge-to-edge distance between that isolator's HV pad
cluster and its SELV pad cluster is at least the corridor width, on some
axis, for some rotation.

**This is a rotation- and position-independent, per-component fact**,
computed once from the real board's pad geometry (``Component.pins`` from
``io.kicad_parser.parse_kicad_pcb``) using the *same* conservative
bounding-circle pad model ``check_isolation_keepout.py`` itself uses
(``radius = max(size.X, size.Y) / 2``) -- so "feasible here" and "gate
passes there" cannot disagree about the geometry, only about where the
solver decides to put things. See ``evaluate_isolator_feasibility``.

**Isolator rotation is fixed to 0 in this module's encoding** (mirroring the
existing ``_POLARIZED_REFS`` fixed-rotation mechanism in
``_encoder_solve.py`` for diodes/electrolytics) -- not because isolators
must physically be non-rotatable, but because it makes the per-isolator
split constraint a plain linear inequality instead of a 4-way
``AddElement`` dispatch, AND because it loses no feasibility for this
question: the maximum achievable HV/SELV pad-cluster separation under any
of the 4 axis-aligned rotations is exactly the larger of the two values
``evaluate_isolator_feasibility`` already computes (gap along local X, gap
along local Y) -- rotating 90 degrees only swaps which global axis sees
which local value, it cannot create a larger value than the pair already
sampled. Both axes are evaluated up front, so fixing rotation to 0 and
choosing the axis that already clears the bar (if any) is complete, not a
narrowing of the search.

**Orientation and corridor position are fixed constants, not solver
variables**, for a documented reason that is *not* "simpler to implement":
this module's own ``evaluate_isolator_feasibility`` proves that isolator
feasibility does not depend on where the corridor sits along its own axis
(a two-point cluster-pair's achievable projected separation is a property
of the pair, not of the corridor's position), so a movable corridor buys
zero extra isolator feasibility. It could still matter for how well the
150 domain-only components pack against a fixed corridor -- this module
picks the board's own centreline by default (``corridor_position_mm=None``)
and accepts a caller override for that reason, but does not encode the
position as an ``IntVar`` because doing so would not change the
determination this module exists to make (see the evidence doc for the
real board's outcome).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Netlist
    from temper_placer.placer.cp_sat.model import CpSatModel

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_CORRIDOR_WIDTH_MM",
    "DomainPartition",
    "IsolatorFeasibility",
    "IsolationBarrierReport",
    "add_isolation_barrier_to_model",
    "classify_domain_partition",
    "evaluate_isolator_feasibility",
    "load_domain_manifest_nets",
]

# 0.5mm above scripts/check_isolation_keepout.py's MIN_BARRIER_WIDTH_MM
# (8.0mm, REINFORCED creepage -- see that module's docstring for the full
# IEC 60335-1 derivation). The margin exists so integer-unit rounding
# (CpSatModel.mm_to_units rounds to the nearest *even* unit) and the gate's
# own Shapely negative-buffer erosion test (a strict "> 0 everywhere", not
# "== 0 at the edge") both have headroom -- never used to justify shrinking
# the 8.0mm safety figure itself, which this module never touches.
DEFAULT_CORRIDOR_WIDTH_MM = 8.5


# ---------------------------------------------------------------------------
# Domain manifest loading (self-contained, exact-name matching only -- same
# discipline as scripts/check_isolation_keepout.py's own load_manifest and
# this project's repeated net-classification-bug history
# (docs/evidence/2026-07-27-net-classification-gate.md): never substring or
# pattern match a net name against a domain).
# ---------------------------------------------------------------------------


def load_domain_manifest_nets(manifest_path: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Return (hv_nets, selv_nets) read verbatim from ``domain_manifest.yaml``.

    Deliberately re-implemented here rather than imported from
    ``scripts/check_isolation_keepout.py`` (scripts/ is not a package this
    src/ tree can import) or from ``router_v6/net_classification.py`` (that
    module classifies by *pattern*, which is exactly the defect class this
    manifest's exact-name convention exists to avoid -- see its own module
    docstring). This is intentionally the smallest possible loader, not a
    general manifest parser.
    """
    import yaml

    if not manifest_path.is_file():
        raise FileNotFoundError(f"domain manifest not found: {manifest_path}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    domains = data["domains"]
    hv_nets = frozenset(domains["HV"]["nets"])
    selv_nets = frozenset(domains["SELV"]["nets"])
    overlap = hv_nets & selv_nets
    if overlap:
        raise ValueError(f"domain manifest declares net(s) in both HV and SELV: {sorted(overlap)}")
    return hv_nets, selv_nets


# ---------------------------------------------------------------------------
# Domain partition
# ---------------------------------------------------------------------------


@dataclass
class DomainPartition:
    """Every board component classified into exactly one bucket.

    A component is an ``isolator`` if and only if it has at least one pad on
    an HV-classified net AND at least one pad on an SELV-classified net --
    this is a *derived*, pad-level fact, not a copy of
    ``domain_manifest.yaml``'s own ``isolators:`` list (which names
    atopile instance paths, not board refs, and would require re-deriving
    the instance-path -> ref mapping this module has no independent need
    for). On the real board (2026-07-28) this derived set is exactly
    ``{C6, K1, K2, K3, PS1, T1, U3, U7}`` -- exactly the manifest's 7
    declared isolator instances plus the Y-cap, the same cross-check
    ``docs/evidence/2026-07-28-isolation-keepout.md`` already reports for
    this board -- but the derivation here is independent of that file.
    """

    hv_only: list[str] = field(default_factory=list)
    selv_only: list[str] = field(default_factory=list)
    isolators: list[str] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.hv_only) + len(self.selv_only) + len(self.isolators) + len(self.unclassified)


def classify_domain_partition(
    components: list[Component],
    hv_nets: frozenset[str],
    selv_nets: frozenset[str],
) -> DomainPartition:
    """Classify every component by which domain(s) its pins touch."""
    partition = DomainPartition()
    for comp in components:
        touches_hv = any(p.net in hv_nets for p in comp.pins)
        touches_selv = any(p.net in selv_nets for p in comp.pins)
        if touches_hv and touches_selv:
            partition.isolators.append(comp.ref)
        elif touches_hv:
            partition.hv_only.append(comp.ref)
        elif touches_selv:
            partition.selv_only.append(comp.ref)
        else:
            partition.unclassified.append(comp.ref)
    return partition


# ---------------------------------------------------------------------------
# Isolator pad-group geometry and feasibility
# ---------------------------------------------------------------------------

Pad = tuple[float, float, float]  # (local_x_mm, local_y_mm, radius_mm)


@dataclass
class IsolatorPadGroups:
    ref: str
    hv_pads: list[Pad]
    selv_pads: list[Pad]
    other_pads: list[Pad]


def compute_pad_groups(
    comp: Component,
    hv_nets: frozenset[str],
    selv_nets: frozenset[str],
) -> IsolatorPadGroups:
    """Split one component's real pads into HV/SELV/other groups.

    ``Pin.position`` is the pad's position in the component's own local
    (pre-rotation) frame, in mm (``io/_parse_modules.py`` builds it by
    recentring every pad on the footprint's own pad-bounding-box centre --
    the recentring point does not matter here, only pairwise pad-to-pad
    distances do, which recentring does not change).

    Radius uses the SAME conservative "bounding circle from the larger pad
    dimension" model ``scripts/check_isolation_keepout.py`` uses
    (``radius = max(size.X, size.Y) / 2``) so a pad this module judges
    "clears the corridor" and the gate's own pad-intrusion check can never
    disagree about the geometry.
    """
    hv_pads: list[Pad] = []
    selv_pads: list[Pad] = []
    other_pads: list[Pad] = []
    for pin in comp.pins:
        x, y = pin.position
        radius = max(pin.width, pin.height) / 2.0
        rec = (x, y, radius)
        if pin.net in hv_nets:
            hv_pads.append(rec)
        elif pin.net in selv_nets:
            selv_pads.append(rec)
        else:
            other_pads.append(rec)
    return IsolatorPadGroups(ref=comp.ref, hv_pads=hv_pads, selv_pads=selv_pads, other_pads=other_pads)


def _axis_gap(hv_pads: list[Pad], selv_pads: list[Pad], axis_idx: int) -> float:
    """Worst-case (minimum, over every HV-pad x SELV-pad pair) edge-to-edge
    separation projected onto one axis (0=X, 1=Y).

    This is the binding quantity: for the whole HV pad cluster to land on
    one side of a barrier and the whole SELV pad cluster to land on the
    other, EVERY HV/SELV pad pair must individually clear the gap -- the
    tightest pair sets the achievable separation, exactly like
    ``domain_clearance.py``'s own per-pair Chebyshev margin.
    """
    worst = float("inf")
    for hx, hy, hr in hv_pads:
        for sx, sy, sr in selv_pads:
            h = (hx, hy)[axis_idx]
            s = (sx, sy)[axis_idx]
            gap = abs(h - s) - hr - sr
            worst = min(worst, gap)
    return worst


@dataclass
class IsolatorFeasibility:
    ref: str
    gap_x_mm: float
    gap_y_mm: float
    corridor_width_mm: float
    feasible_axis: int | None  # 0=X, 1=Y, None=infeasible on either
    hv_is_lo: bool  # True if the HV pad cluster sits at the smaller local coordinate

    @property
    def feasible(self) -> bool:
        return self.feasible_axis is not None


def evaluate_isolator_feasibility(
    pad_groups: IsolatorPadGroups,
    corridor_width_mm: float,
) -> IsolatorFeasibility:
    """Can this isolator's HV/SELV pad clusters straddle a corridor this wide?

    Checks both candidate split axes (X and Y) -- see module docstring for
    why this covers all 4 axis-aligned rotations without needing to
    enumerate them.
    """
    if not pad_groups.hv_pads or not pad_groups.selv_pads:
        raise ValueError(
            f"{pad_groups.ref}: not a real isolator -- missing an HV or SELV pad "
            "(caller should not have classified this as an isolator)"
        )
    gap_x = _axis_gap(pad_groups.hv_pads, pad_groups.selv_pads, 0)
    gap_y = _axis_gap(pad_groups.hv_pads, pad_groups.selv_pads, 1)

    feasible_axis: int | None = None
    hv_is_lo = True
    for axis_idx, gap in ((0, gap_x), (1, gap_y)):
        if gap >= corridor_width_mm:
            feasible_axis = axis_idx
            hv_mean = sum(p[axis_idx] for p in pad_groups.hv_pads) / len(pad_groups.hv_pads)
            selv_mean = sum(p[axis_idx] for p in pad_groups.selv_pads) / len(pad_groups.selv_pads)
            hv_is_lo = hv_mean <= selv_mean
            break

    return IsolatorFeasibility(
        ref=pad_groups.ref,
        gap_x_mm=gap_x,
        gap_y_mm=gap_y,
        corridor_width_mm=corridor_width_mm,
        feasible_axis=feasible_axis,
        hv_is_lo=hv_is_lo,
    )


# ---------------------------------------------------------------------------
# Model wiring
# ---------------------------------------------------------------------------


@dataclass
class IsolationBarrierReport:
    partition: DomainPartition
    isolator_feasibility: list[IsolatorFeasibility]
    orientation: str
    corridor_width_mm: float
    corridor_position_mm: float
    barrier_constraint_ids: list[str] = field(default_factory=list)
    isolator_assumption_labels: list[str] = field(default_factory=list)

    @property
    def infeasible_isolators(self) -> list[str]:
        return [f.ref for f in self.isolator_feasibility if not f.feasible]


def add_isolation_barrier_to_model(
    model: CpSatModel,
    netlist: Netlist,
    manifest_path: Path,
    *,
    board_w_mm: float,
    board_h_mm: float,
    corridor_width_mm: float = DEFAULT_CORRIDOR_WIDTH_MM,
    orientation: str = "vertical",
    corridor_position_mm: float | None = None,
) -> IsolationBarrierReport:
    """Add the barrier's HARD constraints directly to *model* and return a report.

    Must be called AFTER every real netlist component has already been
    registered via ``model.add_component``/``add_rotation`` (this function
    calls ``model.get_component(ref)`` for every HV-only/SELV-only/isolator
    ref). All constraints are added directly to ``model.model_ref`` by this
    function -- there is nothing further for the caller to encode.

    Side convention (arbitrary but applied uniformly -- see module docstring
    "Why not the existing SeparatedConstraint machinery"): HV-only
    components are forced to the corridor's "lo" side (smaller X for a
    vertical corridor, smaller Y for horizontal); SELV-only components to
    the "hi" side. Each isolator's own HV pad cluster is forced to the same
    "lo" side and its SELV pad cluster to "hi", consistent with every other
    HV/SELV component on the board.
    """
    if orientation not in ("vertical", "horizontal"):
        raise ValueError(f"orientation must be 'vertical' or 'horizontal', got {orientation!r}")

    hv_nets, selv_nets = load_domain_manifest_nets(manifest_path)
    partition = classify_domain_partition(netlist.components, hv_nets, selv_nets)
    if not partition.hv_only:
        raise ValueError("zero HV-only components found -- nothing to separate (anti-vacuity)")
    if not partition.selv_only:
        raise ValueError("zero SELV-only components found -- nothing to separate (anti-vacuity)")

    axis = 0 if orientation == "vertical" else 1
    span_mm = board_w_mm if orientation == "vertical" else board_h_mm
    if corridor_position_mm is None:
        corridor_position_mm = span_mm / 2.0 - corridor_width_mm / 2.0

    barrier_lo_units = model.mm_to_units(corridor_position_mm)
    barrier_hi_units = model.mm_to_units(corridor_position_mm + corridor_width_mm)

    model_refs = set(model.component_map.keys())
    hv_assumption_labels: list[str] = []
    selv_assumption_labels: list[str] = []

    for ref in sorted(partition.hv_only):
        if ref not in model_refs:
            continue  # not registered in this model instance (subset solve)
        cvars = model.get_component(ref)
        end = cvars.x_end if axis == 0 else cvars.y_end
        label = f"isolation_barrier_hv_{ref}"
        assumption = model.new_assumption(label)
        model.add_constraint_enforced(end <= barrier_lo_units, assumption)
        hv_assumption_labels.append(label)

    for ref in sorted(partition.selv_only):
        if ref not in model_refs:
            continue
        cvars = model.get_component(ref)
        start = cvars.x_start if axis == 0 else cvars.y_start
        label = f"isolation_barrier_selv_{ref}"
        assumption = model.new_assumption(label)
        model.add_constraint_enforced(start >= barrier_hi_units, assumption)
        selv_assumption_labels.append(label)

    # ---- isolators: per-component pad-cluster split, rotation fixed to 0 -
    comp_by_ref = {c.ref: c for c in netlist.components}
    isolator_feasibility: list[IsolatorFeasibility] = []
    isolator_assumption_labels: list[str] = []

    for ref in sorted(partition.isolators):
        if ref not in model_refs:
            continue
        comp = comp_by_ref[ref]
        pad_groups = compute_pad_groups(comp, hv_nets, selv_nets)
        feas = evaluate_isolator_feasibility(pad_groups, corridor_width_mm)
        isolator_feasibility.append(feas)

        cvars = model.get_component(ref)
        if cvars.rot_ref is not None:
            model.model_ref.Add(cvars.rot_ref == 0)

        # Same global side convention as every HV-only/SELV-only component
        # above: HV cluster -> lo side, SELV cluster -> hi side. This is
        # NOT the per-isolator "whichever side is closer" choice
        # ``evaluate_isolator_feasibility.hv_is_lo`` reports (that field is
        # only about which axis/orientation *can* achieve the required gap
        # at all, order-agnostic) -- the actual encoded constraint must use
        # the SAME global convention as every other component, or an
        # isolator could straddle "backwards" relative to the rest of the
        # board's domain split, which would make check 6 (far-side
        # crossing) fail on the real board even though this module's own
        # constraint was satisfied.
        hv_far_edge_mm = max(p[axis] + p[2] for p in pad_groups.hv_pads)
        selv_near_edge_mm = min(p[axis] - p[2] for p in pad_groups.selv_pads)

        label = f"isolator_straddle_{ref}"
        assumption = model.new_assumption(label)
        isolator_assumption_labels.append(label)

        center_coord = cvars.x_center if axis == 0 else cvars.y_center
        hv_far_edge_units = model.mm_to_units(hv_far_edge_mm)
        selv_near_edge_units = model.mm_to_units(selv_near_edge_mm)

        # center + (HV cluster's far edge, relative to centre) <= corridor lo
        # center + (SELV cluster's near edge, relative to centre) >= corridor hi
        model.add_constraint_enforced(center_coord + hv_far_edge_units <= barrier_lo_units, assumption)
        model.add_constraint_enforced(center_coord + selv_near_edge_units >= barrier_hi_units, assumption)

    report = IsolationBarrierReport(
        partition=partition,
        isolator_feasibility=isolator_feasibility,
        orientation=orientation,
        corridor_width_mm=corridor_width_mm,
        corridor_position_mm=corridor_position_mm,
        barrier_constraint_ids=hv_assumption_labels + selv_assumption_labels,
        isolator_assumption_labels=isolator_assumption_labels,
    )
    return report
