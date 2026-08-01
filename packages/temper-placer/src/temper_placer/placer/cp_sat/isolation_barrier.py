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

**This is a position-independent, per-component fact** (position-
independent, not rotation-independent -- rotation changes which physical
pad dimension faces the barrier axis, which is exactly what
``_best_rotation_for_barrier`` searches over), computed once from the real
board's pad geometry (``Component.pins`` from
``io.kicad_parser.parse_kicad_pcb``) using the *same* shape-correct,
rotation-aware pad model ``check_isolation_keepout.py`` itself uses
(``temper_placer.core.pad_geometry`` -- exact circle/oval/rect/roundrect
Minkowski-sum geometry, not a single isotropic
``radius = max(size.X, size.Y) / 2`` circle) -- so "feasible here" and
"gate passes there" cannot disagree about the geometry, only about where
the solver decides to put things. See ``evaluate_isolator_feasibility``.

**Isolator rotation is CHOSEN, then fixed, not left as a free CP-SAT
variable** (``_best_rotation_for_barrier`` picks it; ``add_isolation_barrier_to_model``
then pins ``rot_ref`` to that value via a plain ``Add(rot_ref == ...)``,
mirroring the existing ``_POLARIZED_REFS`` fixed-rotation mechanism in
``_encoder_solve.py`` for diodes/electrolytics). This makes the
per-isolator split constraint a plain linear inequality instead of a
4-way ``AddElement`` dispatch, without losing any feasibility: of the
model's 4 axis-aligned rotations, exactly 2 project the local X axis onto
the corridor's own axis (rot 0/2, sign-flipped) and 2 project local Y
(rot 1/3, sign-flipped), so only 2 *magnitudes* are reachable at all (the
``gap_x``/``gap_y`` values), each reachable in either of 2 directions --
one of which keeps this module's global HV=lo/SELV=hi convention, one of
which inverts it. ``_best_rotation_for_barrier`` checks all 4 explicitly
and picks the convention-preserving one with the larger achievable gap.
Fixing rotation to a *constant* 0 (an earlier version of this module did
this, reasoning that "both axes are sampled so no feasibility is lost")
was a real bug: it silently always used the local-X-to-barrier-axis
mapping regardless of which axis actually cleared the bar, so an isolator
whose only adequate separation was along local Y (real example: K1, the
bypass relay -- adequate along local Y at small corridor widths, always
inadequate along local X) was wrongly reported/encoded as infeasible
against a barrier axis it could have used with a 90-degree rotation. Caught
by a corridor-width control experiment (docs/evidence/
2026-07-28-barrier-constrained-placement.md) and fixed by actually
enumerating the 4 rotations rather than assuming rot=0 is as good as any.

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
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import temper_geometry as _tg

from temper_placer.core.isolation_constants import MIN_BARRIER_WIDTH_MM

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

# 0.5mm above the SSOT REINFORCED creepage figure, MIN_BARRIER_WIDTH_MM
# (temper_placer.core.isolation_constants -- scripts/check_isolation_keepout.py's
# module docstring has the full IEC 60335-1 derivation; never restated here
# as a literal). The margin exists so integer-unit rounding
# (CpSatModel.mm_to_units rounds to the nearest *even* unit) and the gate's
# own Shapely negative-buffer erosion test (a strict "> 0 everywhere", not
# "== 0 at the edge") both have headroom -- never used to justify shrinking
# MIN_BARRIER_WIDTH_MM itself, which this module never touches. Computed,
# not restated: a future retarget of MIN_BARRIER_WIDTH_MM now moves this
# value for free instead of relying on someone finding and hand-updating a
# duplicated literal -- see docs/solutions/design-patterns/derived-constant-
# in-prose-drifts-make-the-gate-emit-it-2026-07-29.md.
DEFAULT_CORRIDOR_WIDTH_MM = MIN_BARRIER_WIDTH_MM + 0.5


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

@dataclass(frozen=True)
class Pad:
    """A pad's position (in the component's local, pre-rotation frame, mm)
    and its exact declared shape.

    This used to be a plain ``(local_x_mm, local_y_mm, radius_mm)`` tuple,
    with ``radius_mm = max(width, height) / 2`` -- a single isotropic
    number that cannot be correct for both the X-axis gap and the Y-axis
    gap of an elongated pad (see ``core.pad_geometry`` module docstring for
    the full derivation), nor for a pad's true extent under a 90-degree
    rotation swap. Carrying the real shape instead, and deferring the
    radius computation to ``axis_radius()`` for the specific axis and
    rotation being evaluated, is what makes both correct: see
    ``pad_geometry.pad_axis_radius``.
    """

    x: float
    y: float
    width: float
    height: float
    shape: str = "circle"
    roundrect_ratio: float = 0.25

    def axis_radius(self, axis: int, rotation_rad: float = 0.0) -> float:
        """Exact half-extent along a *world* axis (0=X, 1=Y), given the pad
        has been rotated by ``rotation_rad`` (in addition to whatever local
        orientation ``width``/``height``/``shape`` already encode)."""
        from temper_placer.core.pad_geometry import pad_axis_radius

        return pad_axis_radius(self.width, self.height, self.shape, axis, rotation_rad, self.roundrect_ratio)


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

    Each pad's real declared shape (``Pin.shape``/``width``/``height``/
    ``roundrect_ratio``) is carried through uninterpreted -- the exact,
    shape-aware, rotation-aware radius is computed on demand by
    ``Pad.axis_radius()`` for whichever axis/rotation a caller (``_axis_gap``,
    ``_best_rotation_for_barrier``) actually needs, using the SAME shared
    model (``core.pad_geometry``) ``scripts/check_isolation_keepout.py``
    uses, so a pad this module judges "clears the corridor" and the gate's
    own pad-intrusion check can never disagree about the geometry.
    """
    hv_pads: list[Pad] = []
    selv_pads: list[Pad] = []
    other_pads: list[Pad] = []
    for pin in comp.pins:
        x, y = pin.position
        pad = Pad(
            x=x,
            y=y,
            width=pin.width,
            height=pin.height,
            shape=pin.shape or "rect",
            roundrect_ratio=getattr(pin, "roundrect_ratio", None) or 0.25,
        )
        if pin.net in hv_nets:
            hv_pads.append(pad)
        elif pin.net in selv_nets:
            selv_pads.append(pad)
        else:
            other_pads.append(pad)
    return IsolatorPadGroups(ref=comp.ref, hv_pads=hv_pads, selv_pads=selv_pads, other_pads=other_pads)


def _axis_gap(hv_pads: list[Pad], selv_pads: list[Pad], axis_idx: int) -> float:
    """Worst-case (minimum, over every HV-pad x SELV-pad pair) edge-to-edge
    separation projected onto one *local*-frame axis (0=X, 1=Y; rotation=0,
    matching this function's pre-existing "informational, unrotated"
    contract -- ``_best_rotation_for_barrier`` is what searches rotations).

    This is the binding quantity: for the whole HV pad cluster to land on
    one side of a barrier and the whole SELV pad cluster to land on the
    other, EVERY HV/SELV pad pair must individually clear the gap -- the
    tightest pair sets the achievable separation, exactly like
    ``domain_clearance.py``'s own per-pair Chebyshev margin.

    Computed in the ``temper-geometry`` Rust crate (``pad_geometry.rs``)
    with the exact f64 operation order of the former pure-Python loop.
    """
    return _tg.barrier_axis_gap_py(
        [_pad_tuple(p) for p in hv_pads], [_pad_tuple(p) for p in selv_pads], axis_idx
    )


def _pad_tuple(p: Pad) -> tuple[float, float, float, float, str, float]:
    return (p.x, p.y, p.width, p.height, p.shape, p.roundrect_ratio)


def _project_onto_barrier_axis(local_x: float, local_y: float, rot_value: int, barrier_axis: int) -> float:
    """Global coordinate (along *barrier_axis*, 0=X/1=Y) a local pad offset
    maps to under one of the model's 4 axis-aligned rotations.

    This is the exact, hand-unrolled closed form of
    ``temper_placer.geometry.kicad_transform.rotate_local_to_world_deg(lx,
    ly, rot_value * 90.0)`` for the 4 axis-aligned cases this CP-SAT model
    uses -- see that module's docstring for the confirming evidence (KiCad
    rotates a footprint child by R(-theta), not R(+theta)). Deliberately
    NOT routed through that module's floating-point ``math.cos``/``sin``:
    at exact 90-degree multiples those evaluate to values like
    ``cos(90 deg) == 6.123e-17`` rather than an exact 0, which would
    introduce sub-ULP float noise into this CP-SAT model's integer-scaled
    coordinates. This dict is the exact, integer-only equivalent instead,
    pinned to the sanctioned module's convention by
    ``test_isolation_barrier_matches_kicad_transform`` in this file's test
    module. So (lx, ly) -> (lx*cos(a) + ly*sin(a), -lx*sin(a) + ly*cos(a))
    for a = rot_value * 90 degrees, i.e.:

        rot=0:  (gx, gy) = ( lx,  ly)
        rot=1:  (gx, gy) = ( ly, -lx)
        rot=2:  (gx, gy) = (-lx, -ly)
        rot=3:  (gx, gy) = (-ly,  lx)
    """
    gx, gy = {
        0: (local_x, local_y),
        1: (local_y, -local_x),
        2: (-local_x, -local_y),
        3: (-local_y, local_x),
    }[rot_value]
    return gx if barrier_axis == 0 else gy


def _best_rotation_for_barrier(
    hv_pads: list[Pad],
    selv_pads: list[Pad],
    barrier_axis: int,
) -> tuple[int, float, bool]:
    """Pick the rotation (of the model's 4) that gives the LARGEST HV/SELV
    cluster gap projected onto *barrier_axis*, restricted to rotations where
    the HV cluster's mean projection is <= the SELV cluster's (this
    module's global "HV=lo side, SELV=hi side" convention -- see
    ``add_isolation_barrier_to_model``'s docstring for why this must be a
    single board-wide convention, not chosen independently per component).

    Fixes a real bug an earlier version of this module had: unconditionally
    fixing rotation to 0 only ever tests the local-X-onto-barrier-axis
    mapping. An isolator whose only adequate HV/SELV separation is along
    its local Y axis (true achievable magnitude: ``gap_y`` in
    ``evaluate_isolator_feasibility``) needs a 90-degree rotation to bring
    that separation onto the barrier's own axis -- rot=0 would silently use
    the WRONG (inadequate) local axis and report a false infeasibility.
    Caught by a corridor-width control experiment during development (see
    docs/evidence/2026-07-28-barrier-constrained-placement.md) where an
    isolator with an adequate Y-axis gap was still reported UNSAT at a
    corridor width its Y-axis gap should have cleared.

    Returns (rot_value, gap_mm) for the best eligible rotation. If NO
    rotation keeps the HV=lo/SELV=hi convention (never observed on the real
    board -- every isolator's HV/SELV clusters are cleanly ordered on at
    least one axis), returns rot=0 and the (necessarily negative or
    convention-violating) gap for rot=0 as a safe, still-checkable fallback.

    Computed in the ``temper-geometry`` Rust crate (``pad_geometry.rs``)
    with the exact operation order (first-maximum tie-breaking, fallback
    semantics) of the former pure-Python sweep.
    """
    return _tg.best_rotation_for_barrier_py(
        [_pad_tuple(p) for p in hv_pads], [_pad_tuple(p) for p in selv_pads], barrier_axis
    )


@dataclass
class IsolatorFeasibility:
    ref: str
    gap_x_mm: float  # informational: raw local-X-axis gap (order-agnostic)
    gap_y_mm: float  # informational: raw local-Y-axis gap (order-agnostic)
    corridor_width_mm: float
    barrier_axis: int  # 0=X (vertical corridor), 1=Y (horizontal corridor)
    achievable_gap_mm: float  # best gap over all 4 rotations consistent with HV=lo/SELV=hi
    chosen_rotation: int  # the rotation that achieves achievable_gap_mm
    feasible_axis: int | None  # 0=X, 1=Y: which LOCAL axis chosen_rotation projects, or None
    hv_is_lo: bool  # True if the HV pad cluster sits at the smaller local coordinate

    @property
    def feasible(self) -> bool:
        return self.achievable_gap_mm >= self.corridor_width_mm


def evaluate_isolator_feasibility(
    pad_groups: IsolatorPadGroups,
    corridor_width_mm: float,
    barrier_axis: int = 0,
) -> IsolatorFeasibility:
    """Can this isolator's HV/SELV pad clusters straddle a corridor this wide?

    ``achievable_gap_mm`` is the TRUE achievable separation for THIS
    specific corridor (``barrier_axis`` fixed, 0=vertical/X or
    1=horizontal/Y) -- the best of the model's 4 axis-aligned rotations,
    restricted to rotations that keep the HV cluster on the board-wide
    "lo" side (see ``_best_rotation_for_barrier``). ``gap_x_mm``/
    ``gap_y_mm`` remain as order-agnostic, rotation-agnostic diagnostic
    values (the two distinct magnitudes achievable by SOME rotation on
    SOME axis, regardless of which axis the actual corridor uses or which
    side convention is in force) -- useful for reporting, but
    ``achievable_gap_mm``/``feasible`` are what ``add_isolation_barrier_to_model``
    actually encodes and must be checked for a specific corridor.
    """
    if not pad_groups.hv_pads or not pad_groups.selv_pads:
        raise ValueError(
            f"{pad_groups.ref}: not a real isolator -- missing an HV or SELV pad "
            "(caller should not have classified this as an isolator)"
        )
    gap_x = _axis_gap(pad_groups.hv_pads, pad_groups.selv_pads, 0)
    gap_y = _axis_gap(pad_groups.hv_pads, pad_groups.selv_pads, 1)

    rot_value, achievable_gap, hv_is_lo = _best_rotation_for_barrier(
        pad_groups.hv_pads, pad_groups.selv_pads, barrier_axis
    )
    # rot in {0, 2} projects local X onto the barrier axis; {1, 3} projects
    # local Y -- see _project_onto_barrier_axis's table.
    feasible_axis = 0 if rot_value in (0, 2) else 1

    return IsolatorFeasibility(
        ref=pad_groups.ref,
        gap_x_mm=gap_x,
        gap_y_mm=gap_y,
        corridor_width_mm=corridor_width_mm,
        barrier_axis=barrier_axis,
        achievable_gap_mm=achievable_gap,
        chosen_rotation=rot_value,
        feasible_axis=feasible_axis if achievable_gap >= corridor_width_mm else None,
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

    # ---- isolators: per-component pad-cluster split, rotation chosen per
    # ``_best_rotation_for_barrier`` (NOT unconditionally fixed to 0 -- see
    # that function's docstring for the real bug this fixes: an isolator
    # whose only adequate separation is along its local Y axis needs a
    # 90-degree rotation to bring it onto the corridor's own (here, X) axis).
    comp_by_ref = {c.ref: c for c in netlist.components}
    isolator_feasibility: list[IsolatorFeasibility] = []
    isolator_assumption_labels: list[str] = []

    for ref in sorted(partition.isolators):
        if ref not in model_refs:
            continue
        comp = comp_by_ref[ref]
        pad_groups = compute_pad_groups(comp, hv_nets, selv_nets)
        feas = evaluate_isolator_feasibility(pad_groups, corridor_width_mm, barrier_axis=axis)
        isolator_feasibility.append(feas)

        cvars = model.get_component(ref)
        rot_value = feas.chosen_rotation
        if cvars.rot_ref is not None:
            model.model_ref.Add(cvars.rot_ref == rot_value)

        # Project every pad through the SAME rotation the constraint below
        # assumes, using the module's global HV=lo/SELV=hi side convention
        # (see _best_rotation_for_barrier -- it already restricted its
        # search to rotations preserving this, so hv_far_edge_mm here is
        # genuinely the "towards the corridor" edge of the HV cluster).
        rot_rad = rot_value * math.pi / 2.0
        hv_far_edge_mm = max(
            _project_onto_barrier_axis(p.x, p.y, rot_value, axis) + p.axis_radius(axis, rot_rad)
            for p in pad_groups.hv_pads
        )
        selv_near_edge_mm = min(
            _project_onto_barrier_axis(p.x, p.y, rot_value, axis) - p.axis_radius(axis, rot_rad)
            for p in pad_groups.selv_pads
        )

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
