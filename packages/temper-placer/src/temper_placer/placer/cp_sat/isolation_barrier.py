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
import temper_orchestration as _to

from temper_placer.core.isolation_constants import (
    MIN_BARRIER_WIDTH_IS_DETERMINATE,
    MIN_BARRIER_WIDTH_MM,
)
from temper_placer.core.pad_geometry import shape_code

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Netlist
    from temper_placer.placer.cp_sat.model import CpSatModel

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_CORRIDOR_WIDTH_MM",
    "MIN_BARRIER_WIDTH_IS_DETERMINATE",
    "BarrierSetbacks",
    "DomainPartition",
    "IsolatorFeasibility",
    "IsolationBarrierReport",
    "PairingIsolatorFeasibility",
    "add_isolation_barrier_to_model",
    "barrier_setbacks",
    "classify_domain_partition",
    "evaluate_isolator_feasibility",
    "evaluate_isolator_per_pairing",
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

# WHAT MOVED UNDER THIS CONSTANT ON 2026-08-19, and why nothing here changed.
#
# `MIN_BARRIER_WIDTH_MM` stopped being the literal 12.6 (Table 17 row iv,
# doubled) and became a DERIVED per-pairing figure: the worst enforceable
# floor over every HV<->SELV pairing declared in
# `elec/insulation_manifest.yaml`. That is the resonant-tank crossing, so the
# corridor moved 13.1mm -> 20.5mm without a line changing here. This is
# exactly what the "computed, not restated" note above was for.
#
# TWO THINGS A CALLER OF THIS MODULE MUST KNOW.
#
# 1. THE CORRIDOR IS A LOWER BOUND, NOT A REQUIREMENT.
#    `MIN_BARRIER_WIDTH_IS_DETERMINATE` is False: the tank and switch-node
#    crossings run at 47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope
#    ceiling, and cl. 2.3 routes dimensioning above it to IEC 60664-4, which
#    is paywalled and was not obtained. A placement that fits this corridor is
#    NOT thereby compliant. This module cannot express that -- CP-SAT takes a
#    number -- so it takes the proven bound and the flag is re-exported for
#    any caller that reports a verdict. Never resolve the indeterminacy by
#    choosing a number.
#
# 2. THIS WILL MAKE THE SOLVE HARDER, AND THAT IS THE HONEST RESULT.
#    `docs/evidence/2026-08-19-placer-constraint-wiring-and-unsat-core.md`
#    measured the barrier constraint as INFEASIBLE at 12.6mm and at 13.1mm on
#    the committed floorplan. It is not less infeasible at 20.5mm. Widening
#    the corridor did not create that infeasibility and narrowing it does not
#    fix it: the barrier's worst crossing needs at least 20.0mm and five
#    isolation-bridging packages offer between 8.0 and 12.8mm of copper-to-
#    copper separation at ANY placement. Do NOT lower this figure to make a
#    solve terminate.


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
    """Classify every component by which domain(s) its pins touch.

    Phase E batch E3 (plan 2026-08-09-001): the classification compute runs
    in ``temper-orchestration``'s ``clearance::classify_domain_partition_py``
    (the ``IsolationBarrierStage``); this function marshals the components
    to ``(ref, [pin nets])`` pairs and rebuilds the ``DomainPartition``
    dataclass. Exact-name membership only (never substring — the
    net-classification bug history).
    """
    # 2026-08-13 (T2/C37/R65 placement tooling): drop pins with no net
    # (KiCad unconnected/NC pads parse with `net=None`, e.g. K1's 4 spare
    # relay contacts on the real board) before marshalling -- the Rust
    # binding's `components` param is `list[(str, list[str])]` and rejects
    # a `None` element with a bare `TypeError: 'None' is not an instance of
    # 'str'` that names neither the offending component nor pin. An
    # unconnected pin touches no net and therefore no domain, so dropping
    # it cannot change which domain(s) a component is classified into --
    # this is a marshalling fix, not a classification-semantics change.
    marshalled = [(c.ref, [p.net for p in c.pins if p.net]) for c in components]
    hv_only, selv_only, isolators, unclassified = _to.classify_domain_partition_py(
        marshalled, sorted(hv_nets), sorted(selv_nets)
    )
    return DomainPartition(
        hv_only=hv_only,
        selv_only=selv_only,
        isolators=isolators,
        unclassified=unclassified,
    )


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
    distances do, which recentring does not change). Working in the local
    frame is why this function needs no world placement at all, and hence
    why ``temper_placer.geometry.pad_world`` is deliberately NOT used here.

    **KNOWN GAP: ``Pin.pad_rotation_deg`` is dropped.** The ``Pad`` record
    below carries no rotation field, so a pad's own intrinsic angle never
    reaches ``Pad.axis_radius()``; ``_best_rotation_for_barrier`` supplies
    only ``rot_value * pi/2``. That is a real omission, not a deliberate
    simplification like ``_axis_gap``'s "unrotated by contract".

    Its cost on ``pcb/temper.kicad_pcb`` today is **exactly 0.0 mm**,
    measured rather than assumed: every pad on this board carries a
    footprint-relative ``pad_rotation_deg`` of 0 or 180 (486 and 39 pads)
    or is rotationally symmetric at 90 (2 pads), and 0/180 are symmetries
    of every axis-aligned KiCad pad shape -- so honouring the angle changes
    no world axis half-extent, on any pad, on either axis. Closing the gap
    properly means widening the pad tuple that crosses into
    ``temper-geometry``'s ``barrier_axis_gap_py`` /
    ``best_rotation_for_barrier_py``, which their differential suites pin
    by arity; that is a Rust ABI change with zero measured benefit on this
    board, so it is recorded here rather than done quietly. A board that
    ever places a pad at a non-symmetric intrinsic angle makes it live.

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


def _pad_tuple(p: Pad) -> tuple[float, float, float, float, int, float]:
    return (p.x, p.y, p.width, p.height, shape_code(p.shape), p.roundrect_ratio)


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

    Phase E batch E3 (plan 2026-08-09-001): the exact table moved to
    ``temper-orchestration``'s ``clearance::project_onto_barrier_axis_py``
    (the ``IsolationBarrierStage``); this is a thin delegation.
    """
    return _to.project_onto_barrier_axis_py(local_x, local_y, rot_value, barrier_axis)


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

    Phase E batch E3 (plan 2026-08-09-001): the feasibility compute — the
    axis-gap kernels plus the best-rotation assembly — runs in
    ``temper-orchestration``'s ``clearance::evaluate_isolator_feasibility_py``
    (the ``IsolationBarrierStage``); this function marshals the pad groups
    to the kernel ``PadTuple`` shape and rebuilds the ``IsolatorFeasibility``
    dataclass. The ``ValueError`` for a non-isolator (empty HV or SELV
    cluster) is raised from Rust with the identical message.
    """
    if not pad_groups.hv_pads or not pad_groups.selv_pads:
        raise ValueError(
            f"{pad_groups.ref}: not a real isolator -- missing an HV or SELV pad "
            "(caller should not have classified this as an isolator)"
        )
    gap_x, gap_y, achievable_gap, rot_value, feasible_axis, hv_is_lo = (
        _to.evaluate_isolator_feasibility_py(
            pad_groups.ref,
            [_pad_tuple(p) for p in pad_groups.hv_pads],
            [_pad_tuple(p) for p in pad_groups.selv_pads],
            corridor_width_mm,
            barrier_axis,
        )
    )

    return IsolatorFeasibility(
        ref=pad_groups.ref,
        gap_x_mm=gap_x,
        gap_y_mm=gap_y,
        corridor_width_mm=corridor_width_mm,
        barrier_axis=barrier_axis,
        achievable_gap_mm=achievable_gap,
        chosen_rotation=rot_value,
        feasible_axis=feasible_axis,
        hv_is_lo=hv_is_lo,
    )


# ---------------------------------------------------------------------------
# Per-pairing barrier (2026-08-19)
# ---------------------------------------------------------------------------
#
# WHY A SECOND MODE RATHER THAN A NEW WIDTH.
#
# Everything above encodes ONE corridor of ONE width, because until
# 2026-08-19 there was one requirement: `MIN_BARRIER_WIDTH_MM`, a single
# scalar applied to every HV<->SELV crossing. `feat/per-pairing-creepage-
# derivation` replaced that scalar with a requirement derived per *pairing*
# of declared net groups (`elec/insulation_manifest.yaml` ->
# `insulation.rs`), and the four barrier-crossing pairings do not agree:
#
#     MAINS<->SELV         4.8 mm   determinable
#     DC_BUS<->SELV        8.0 mm   determinable
#     SELV<->SWITCHING     8.0 mm   PROVEN FLOOR ONLY (47 kHz, out of scope)
#     SELV<->TANK         20.0 mm   PROVEN FLOOR ONLY (47 kHz, out of scope)
#
# Sizing one corridor by the worst of them (20.0 mm, what
# `MIN_BARRIER_WIDTH_MM` now returns) charges the mains crossing 4.2x its
# requirement and the bus crossing 2.5x. That over-charge is not free: it is
# precisely what made C6, K1, U6 and T2 look like BOM problems.
#
# THE ENCODING. Keep ONE barrier line -- there is one physical barrier, and
# a per-pairing corridor is not a set of independent corridors -- but give
# each HV group its own SETBACK from that line, and put the whole SELV
# domain flush against it:
#
#     SELV copper       >= P                       (setback 0)
#     MAINS copper      <= P - 4.8
#     DC_BUS copper     <= P - 8.0
#     SWITCHING copper  <= P - 8.0
#     TANK copper       <= P - 20.0
#
# SOUNDNESS. For any HV pad in group G and any SELV pad, the constraint pair
# forces their separation ALONG THE BARRIER AXIS to be at least
# `setback(G) + 0 = floor(G <-> SELV)`. Axis-projected separation is a lower
# bound on Euclidean separation, which is itself a lower bound on the true
# creepage path, so clearing the encoded figure implies clearing the derived
# one. The model can only over-constrain, never under-constrain.
#
# IT IS A STRICT GENERALISATION. With every setback equal to W, and no pad
# carrying its own `(at .. ANGLE)` rotation, the need function below reduces
# to `W - gap(rot)` -- exactly `evaluate_isolator_feasibility`'s
# `achievable_gap_mm >= corridor_width_mm`. Where a pad DOES carry its own
# angle the two differ, deliberately and in the strict direction: see
# `_worst_axis_radius`, which exists because the scalar path drops that angle
# and is therefore optimistic by up to 2.6 mm on this board's real packages.
#
# WHAT IT STILL DOES NOT ENCODE. HV<->HV functional pairings (e.g.
# DC_BUS<->TANK, floor 10.0 mm) live entirely on the barrier's HV side and
# this family says nothing about them; they are the netclass family's job
# (`netclass_constraints.py` with `dru_resolved_pairs=True`, which reads the
# same regenerated projections). Naming the gap rather than implying the
# barrier covers it.
#
# THE INDETERMINACY IS NOT RESOLVED HERE. Two of the four figures above are
# proven LOWER BOUNDS, not requirements: 47 kHz is above IEC 60664-1
# cl. 1.1.1's 30 kHz scope ceiling and cl. 2.3 routes dimensioning above it
# to the unobtained IEC 60664-4. CP-SAT takes a number, so this encodes the
# bound -- and `BarrierSetbacks.determinable` carries False for every group
# whose figure is one, so no caller can report "compliant" off a solve that
# depended on it. Never substitute a determinate-looking number here.


@dataclass(frozen=True)
class BarrierSetbacks:
    """Per-HV-group setback from the single barrier line, derived.

    ``setback_mm[G]`` is the largest enforceable floor over every declared
    barrier-crossing pairing that involves HV group ``G`` -- i.e. how far
    ``G``'s copper must sit from the line the whole SELV domain is flush
    against. ``determinable[G]`` is False when any of those pairings has no
    determinable requirement, in which case the setback is a proven lower
    bound and clearing it is **not** compliance.
    """

    setback_mm: dict[str, float]
    determinable: dict[str, bool]
    governing_pairing: dict[str, str]

    @property
    def widest_mm(self) -> float:
        return max(self.setback_mm.values())

    @property
    def all_determinable(self) -> bool:
        return all(self.determinable.values())

    def for_group(self, group: str) -> float:
        """Setback for *group*, or the widest on the board when *group* is
        not a declared HV group.

        The fallback is the fail-closed direction and it is deliberately the
        maximum, not a default figure: an undeclared group reaching this
        function means the domain manifest and the insulation declaration
        have drifted, and the only safe answer to "how far must this unknown
        thing sit from SELV" is "as far as the worst thing on the board".
        ``scripts/check_insulation_pairings.py`` proves the two agree, so
        this branch is unreachable on a consistent repo.
        """
        return self.setback_mm.get(group, self.widest_mm)


def barrier_setbacks() -> BarrierSetbacks:
    """Derive the per-HV-group setbacks from the insulation declaration.

    Reads every declared pairing, keeps the ones that cross the barrier
    (``crosses_barrier()`` -- one side HV domain, one side SELV), and
    reduces onto the HV side with ``max`` over floors and ``all`` over
    determinability: the same conservatism
    ``insulation_coordination.requirement_for_net_classes`` uses, and the
    same predicate ``barrier_floor_mm()`` reduces over.

    No figure is written here. Every number comes from
    ``elec/insulation_manifest.yaml`` through ``insulation.rs``.
    """
    from temper_placer.core.insulation_coordination import _resolution

    setback: dict[str, float] = {}
    determinable: dict[str, bool] = {}
    governing: dict[str, str] = {}
    for pairing in _resolution().pairings():
        if not pairing.crosses_barrier():
            continue
        hv_group = pairing.group_a() if pairing.domain_a() == "HV" else pairing.group_b()
        floor = pairing.enforceable_floor_mm()
        if floor > setback.get(hv_group, float("-inf")):
            setback[hv_group] = floor
            governing[hv_group] = pairing.key()
        determinable[hv_group] = determinable.get(hv_group, True) and pairing.is_determinable()
    if not setback:
        raise ValueError(
            "no barrier-crossing pairing is declared in elec/insulation_manifest.yaml "
            "-- refusing to encode a barrier with no derived requirement (anti-vacuity)"
        )
    return BarrierSetbacks(
        setback_mm=setback, determinable=determinable, governing_pairing=governing
    )


@dataclass(frozen=True)
class PairingIsolatorFeasibility:
    """Per-pairing verdict for one isolator, at its OWN required setbacks."""

    ref: str
    #: Smallest achievable ``need`` over the 4 rotations. ``<= 0`` means the
    #: package can span its own requirement; ``> 0`` is the shortfall in mm.
    need_mm: float
    chosen_rotation: int
    #: The HV group / net / setback that set ``need_mm`` at that rotation.
    binding_group: str
    binding_hv_net: str
    binding_setback_mm: float
    #: Barrier-axis gap the binding HV pad achieves against the nearest SELV
    #: pad -- reported so a shortfall attributes to a real pad pair.
    binding_gap_mm: float
    determinable: bool
    governing_pairing: str

    @property
    def feasible(self) -> bool:
        return self.need_mm <= 0.0


# A PAD'S OWN ROTATION, AND WHY THIS TAKES THE WORST CASE OVER THREE
# CONVENTIONS RATHER THAN PICKING ONE.
#
# `compute_pad_groups` above builds a `Pad` from width/height/shape alone and
# `Pad.axis_radius` is then evaluated at the MODEL's rotation. It never reads
# `Pin.pad_rotation_deg` -- the pad's own `(at x y ANGLE)`. On a footprint
# whose pads are individually rotated that omission makes the model
# OPTIMISTIC, and MEASURED on this board it is:
#
#     CST3015 (T1, T2)  barrier model 9.100 mm   exact copper 7.800 mm
#     Relay G4A-E (K1)  barrier model 8.000 mm   exact copper 5.425 mm
#
# (`docs/evidence/2026-08-19-per-pairing-residual-attribution.py`, against
# `core.pad_geometry.pad_pair_distance` -- the exact Minkowski kernel the
# REQ-SAFE-01 validator and `check_isolation_keepout.py` both use.) A 1.3 mm
# over-report is enough to turn T2's real 0.2 mm shortfall against the
# DC_BUS<->SELV figure into a model PASS, i.e. to certify a part the copper
# does not support. That is the wrong direction for a safety constraint.
#
# Composing the two angles correctly is genuinely ambiguous here: a pad angle
# in a `.kicad_pcb` file is already absolute (the convention
# `scripts/check_pad_orientation.py` polices and
# `scripts/measure_cross_domain_creepage.py` documents), but this model is
# choosing a NEW footprint rotation, and whether the writer re-composes is a
# property of the writer, not of this file. So rather than pick a convention
# and be optimistic if it is the wrong one, this takes the LARGEST axis
# radius over all three candidates:
#
#     theta = model_rot            (what the scalar path assumes)
#     theta = pad_rot              (angle stays absolute through the re-place)
#     theta = model_rot + pad_rot  (angle re-composes with the new rotation)
#
# The maximum is >= each of them, so the encoded gap is <= the gap under
# whichever convention turns out to hold. It can only over-constrain, which
# is the same soundness direction the rest of this module argues from. It is
# NOT the unconditional worst case over all angles ((w+h)/2, at 45 degrees) --
# that would be conservative past the point of usefulness, and the three
# candidates are the only orientations any of the conventions can produce.


def _worst_axis_radius(pad: Pad, pad_rot_rad: float, axis: int, model_rot_rad: float) -> float:
    """Largest half-extent along *axis* over the three candidate pad
    orientations. See the note above for why this is a max and not a choice."""
    return max(
        pad.axis_radius(axis, model_rot_rad),
        pad.axis_radius(axis, pad_rot_rad),
        pad.axis_radius(axis, model_rot_rad + pad_rot_rad),
    )


def _pairing_hv_items(
    comp: Component,
    hv_nets: frozenset[str],
    selv_nets: frozenset[str],
    setbacks: BarrierSetbacks,
) -> tuple[list[tuple[Pad, float, str, str, float]], list[tuple[Pad, float]]]:
    """Split one component's pads into ``(Pad, pad_rot_rad, net, group,
    setback)`` items and ``(Pad, pad_rot_rad)`` SELV pads.

    Deliberately NOT a change to ``compute_pad_groups``/``Pad``: that pair is
    covered by a Rust differential and by equality assertions on ``Pad``
    instances (``test_isolation_barrier.py``), and widening the dataclass
    would change those comparisons for every caller. This is a parallel
    reader over the same ``comp.pins`` using the same shape fields -- plus
    ``pad_rotation_deg``, which `compute_pad_groups` drops and which the
    exact kernel does not.
    """
    from temper_placer.core.insulation_coordination import _resolution

    resolution = _resolution()
    hv_items: list[tuple[Pad, float, str, str, float]] = []
    selv_pads: list[tuple[Pad, float]] = []
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
        pad_rot = math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0)
        if pin.net in hv_nets:
            group = resolution.group_of(pin.net)
            # `group is None` means the domain manifest calls this net HV but
            # the insulation declaration never declared it. Fail closed at the
            # widest setback rather than skipping the pad -- see
            # `BarrierSetbacks.for_group`.
            name = group if group is not None else "<undeclared>"
            hv_items.append((pad, pad_rot, pin.net, name, setbacks.for_group(name)))
        elif pin.net in selv_nets:
            selv_pads.append((pad, pad_rot))
    return hv_items, selv_pads


def _pairing_need(
    hv_items: list[tuple[Pad, float, str, str, float]],
    selv_pads: list[tuple[Pad, float]],
    rot_value: int,
    barrier_axis: int,
) -> tuple[float, str, str, float, float]:
    """How far this package falls SHORT of its own per-pairing requirement at
    one rotation, in mm (``<= 0`` means it clears).

    ``need = max over HV pads of [far edge + that pad's own setback]
             - min over SELV pads of [near edge]``

    -- "the barrier line the HV side demands" minus "the barrier line the
    SELV side can offer". With a single shared setback ``W`` and no pad-level
    rotation this collapses to ``W - achievable_gap``, so the scalar model
    above is that special case of this one.

    Returns ``(need, binding_hv_net, binding_group, binding_setback,
    binding_gap)``.
    """
    rot_rad = rot_value * math.pi / 2.0
    selv_near = min(
        _project_onto_barrier_axis(p.x, p.y, rot_value, barrier_axis)
        - _worst_axis_radius(p, prot, barrier_axis, rot_rad)
        for p, prot in selv_pads
    )
    best_need = float("-inf")
    binding: tuple[str, str, float, float] = ("", "", 0.0, 0.0)
    for pad, pad_rot, net, group, setback in hv_items:
        far = _project_onto_barrier_axis(
            pad.x, pad.y, rot_value, barrier_axis
        ) + _worst_axis_radius(pad, pad_rot, barrier_axis, rot_rad)
        need = far + setback - selv_near
        if need > best_need:
            best_need = need
            binding = (net, group, setback, selv_near - far)
    return (best_need, binding[0], binding[1], binding[2], binding[3])


def evaluate_isolator_per_pairing(
    comp: Component,
    hv_nets: frozenset[str],
    selv_nets: frozenset[str],
    setbacks: BarrierSetbacks,
    barrier_axis: int = 0,
) -> tuple[PairingIsolatorFeasibility, list[tuple[Pad, str, str, float]], list[Pad]]:
    """Best rotation for one isolator against its OWN per-pairing setbacks.

    All 4 axis-aligned rotations are enumerated and the smallest ``need``
    wins -- no ``hv_is_lo`` pre-filter is needed, because a rotation that
    inverts the convention produces a large positive need on its own and
    loses the minimisation. Same enumeration as
    ``_best_rotation_for_barrier``, expressed against a per-pad requirement
    instead of one shared width.
    """
    hv_items, selv_pads = _pairing_hv_items(comp, hv_nets, selv_nets, setbacks)
    if not hv_items or not selv_pads:
        raise ValueError(
            f"{comp.ref}: not a real isolator -- missing an HV or SELV pad "
            "(caller should not have classified this as an isolator)"
        )
    best: tuple[float, int, str, str, float, float] | None = None
    for rot_value in range(4):
        need, net, group, setback, gap = _pairing_need(
            hv_items, selv_pads, rot_value, barrier_axis
        )
        if best is None or need < best[0]:
            best = (need, rot_value, net, group, setback, gap)
    assert best is not None
    need, rot_value, net, group, setback, gap = best
    return (
        PairingIsolatorFeasibility(
            ref=comp.ref,
            need_mm=need,
            chosen_rotation=rot_value,
            binding_group=group,
            binding_hv_net=net,
            binding_setback_mm=setback,
            binding_gap_mm=gap,
            determinable=setbacks.determinable.get(group, False),
            governing_pairing=setbacks.governing_pairing.get(group, "<undeclared>"),
        ),
        hv_items,
        selv_pads,
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
    # Refs whose isolator-straddle constraint was skipped for this solve
    # (the experiment-only K3 relaxation; empty for any production solve).
    relaxed_isolator_straddle: frozenset[str] = frozenset()
    # Populated only when per_pairing=True. `setbacks` is the derived
    # per-HV-group table this solve actually encoded; `pairing_feasibility`
    # is the per-isolator verdict at those figures. Both are None/empty on
    # the scalar path, so a reader can always tell which model produced a
    # verdict.
    setbacks: BarrierSetbacks | None = None
    pairing_feasibility: list[PairingIsolatorFeasibility] = field(default_factory=list)

    @property
    def infeasible_isolators(self) -> list[str]:
        if self.setbacks is not None:
            return [f.ref for f in self.pairing_feasibility if not f.feasible]
        return [f.ref for f in self.isolator_feasibility if not f.feasible]

    @property
    def determinable(self) -> bool:
        """False when ANY figure this solve encoded is a proven lower bound
        rather than a requirement.

        A caller reporting a verdict must check this: an ``optimal`` from a
        model built on an indeterminate floor certifies that the floor was
        cleared, never that the board is compliant. On the scalar path this
        is ``MIN_BARRIER_WIDTH_IS_DETERMINATE``; on the per-pairing path it
        is ``all`` over the groups actually encoded.
        """
        if self.setbacks is not None:
            return self.setbacks.all_determinable
        return MIN_BARRIER_WIDTH_IS_DETERMINATE


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
    relax_isolator_straddle: set[str] | None = None,
    per_pairing: bool = False,
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

    ``relax_isolator_straddle`` (experiment-only, default None): set of
    isolator refs whose pad-cluster straddle constraint is SKIPPED for this
    solve -- their pads are left free to land anywhere (no rotation pin, no
    HV-lo/SELV-hi pad split). Used by the corridor-feasibility experiment
    (docs/plans/2026-08-01-002-*) to quantify what the K3 isolator-BOM
    phase unlocks; the per-isolator feasibility report still records the
    true geometric verdict (K3 remains infeasible at 8.0mm -- the
    relaxation is a solver-level exemption, not a geometry claim). Absent:
    existing behaviour is completely unchanged.

    ``per_pairing`` (default False -- the scalar model above is unchanged):
    encode each HV group's OWN derived setback from a single barrier line
    instead of one shared corridor width. See the "Per-pairing barrier"
    section for the encoding, its soundness argument, and why it is a strict
    generalisation of the scalar path. ``corridor_width_mm`` is DERIVED in
    this mode and passing one is an error -- the requirement comes from
    ``elec/insulation_manifest.yaml``, not from a caller.
    """
    if orientation not in ("vertical", "horizontal"):
        raise ValueError(f"orientation must be 'vertical' or 'horizontal', got {orientation!r}")
    if per_pairing and corridor_width_mm != DEFAULT_CORRIDOR_WIDTH_MM:
        raise ValueError(
            "per_pairing=True derives every figure from elec/insulation_manifest.yaml; "
            f"corridor_width_mm={corridor_width_mm} cannot be supplied alongside it. "
            "A caller-chosen width is exactly the single scalar this mode replaces, and "
            "accepting one would let a solve be made feasible by lowering a requirement."
        )

    hv_nets, selv_nets = load_domain_manifest_nets(manifest_path)
    partition = classify_domain_partition(netlist.components, hv_nets, selv_nets)
    if not partition.hv_only:
        raise ValueError("zero HV-only components found -- nothing to separate (anti-vacuity)")
    if not partition.selv_only:
        raise ValueError("zero SELV-only components found -- nothing to separate (anti-vacuity)")

    axis = 0 if orientation == "vertical" else 1
    span_mm = board_w_mm if orientation == "vertical" else board_h_mm

    setbacks = barrier_setbacks() if per_pairing else None
    if setbacks is not None:
        # The widest setback is the widest corridor this barrier contains, so
        # it is what the corridor is positioned by -- exactly what
        # `corridor_width_mm` meant on the scalar path. Derived, never given.
        corridor_width_mm = setbacks.widest_mm
    if corridor_position_mm is None:
        corridor_position_mm = span_mm / 2.0 - corridor_width_mm / 2.0

    barrier_lo_units = model.mm_to_units(corridor_position_mm)
    barrier_hi_units = model.mm_to_units(corridor_position_mm + corridor_width_mm)
    # The single barrier line the whole SELV domain sits flush against, and
    # every HV group's setback is measured back from. On the scalar path this
    # is the corridor's hi edge, which is the same line -- the two modes
    # differ only in where each HV group's own boundary falls.
    selv_boundary_mm = corridor_position_mm + corridor_width_mm

    def _hv_group_boundary_units(group: str) -> int:
        """Where copper of *group* must stop, in model units."""
        return model.mm_to_units(selv_boundary_mm - setbacks.for_group(group))  # type: ignore[union-attr]

    def _component_setback_group(ref: str) -> str:
        """The HV group whose setback governs an HV-only component: the
        widest over the groups of its own HV nets.

        Whole-component (bounding-box) enforcement, exactly as on the scalar
        path, so the governing group must be the strictest one the component
        carries -- a part with one DC_BUS pad and one TANK pad is placed by
        the tank figure or its tank pad would sit inside the tank's setback.
        """
        from temper_placer.core.insulation_coordination import _resolution

        resolution = _resolution()
        best_group = ""
        best = float("-inf")
        for pin in comp_by_ref_all[ref].pins:
            if pin.net not in hv_nets:
                continue
            group = resolution.group_of(pin.net) or "<undeclared>"
            value = setbacks.for_group(group)  # type: ignore[union-attr]
            if value > best:
                best, best_group = value, group
        return best_group

    comp_by_ref_all = {c.ref: c for c in netlist.components}
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
        bound = (
            _hv_group_boundary_units(_component_setback_group(ref))
            if setbacks is not None
            else barrier_lo_units
        )
        model.add_constraint_enforced(end <= bound, assumption)
        hv_assumption_labels.append(label)

    for ref in sorted(partition.selv_only):
        if ref not in model_refs:
            continue
        cvars = model.get_component(ref)
        start = cvars.x_start if axis == 0 else cvars.y_start
        label = f"isolation_barrier_selv_{ref}"
        assumption = model.new_assumption(label)
        # Identical on both paths: the SELV domain has setback 0, and the
        # corridor's hi edge IS the barrier line.
        model.add_constraint_enforced(start >= barrier_hi_units, assumption)
        selv_assumption_labels.append(label)

    # ---- isolators: per-component pad-cluster split, rotation chosen per
    # ``_best_rotation_for_barrier`` (NOT unconditionally fixed to 0 -- see
    # that function's docstring for the real bug this fixes: an isolator
    # whose only adequate separation is along its local Y axis needs a
    # 90-degree rotation to bring it onto the corridor's own (here, X) axis).
    comp_by_ref = comp_by_ref_all
    isolator_feasibility: list[IsolatorFeasibility] = []
    pairing_feasibility: list[PairingIsolatorFeasibility] = []
    isolator_assumption_labels: list[str] = []
    relaxed = frozenset(relax_isolator_straddle or ())

    for ref in sorted(partition.isolators):
        if ref not in model_refs:
            continue
        comp = comp_by_ref[ref]

        if setbacks is not None:
            # ---- per-pairing: each HV group in this package gets its own
            # boundary; the SELV cluster sits flush against the barrier line.
            pfeas, hv_items, selv_pads = evaluate_isolator_per_pairing(
                comp, hv_nets, selv_nets, setbacks, barrier_axis=axis
            )
            pairing_feasibility.append(pfeas)
            cvars = model.get_component(ref)
            if ref in relaxed:
                continue
            rot_value = pfeas.chosen_rotation
            if cvars.rot_ref is not None:
                model.model_ref.Add(cvars.rot_ref == rot_value)

            label = f"isolator_straddle_{ref}"
            assumption = model.new_assumption(label)
            isolator_assumption_labels.append(label)

            rot_rad = rot_value * math.pi / 2.0
            center_coord = cvars.x_center if axis == 0 else cvars.y_center

            # One constraint per HV group present in the package -- the
            # group's own farthest pad against the group's own boundary.
            # Equivalent to one constraint per pad, minus the duplicates.
            far_by_group: dict[str, float] = {}
            for pad, pad_rot, _net, group, _setback in hv_items:
                far = _project_onto_barrier_axis(
                    pad.x, pad.y, rot_value, axis
                ) + _worst_axis_radius(pad, pad_rot, axis, rot_rad)
                if far > far_by_group.get(group, float("-inf")):
                    far_by_group[group] = far
            for group, far_mm in sorted(far_by_group.items()):
                model.add_constraint_enforced(
                    center_coord + model.mm_to_units(far_mm) <= _hv_group_boundary_units(group),
                    assumption,
                )

            selv_near_edge_mm = min(
                _project_onto_barrier_axis(p.x, p.y, rot_value, axis)
                - _worst_axis_radius(p, prot, axis, rot_rad)
                for p, prot in selv_pads
            )
            model.add_constraint_enforced(
                center_coord + model.mm_to_units(selv_near_edge_mm) >= barrier_hi_units,
                assumption,
            )
            continue

        pad_groups = compute_pad_groups(comp, hv_nets, selv_nets)
        feas = evaluate_isolator_feasibility(pad_groups, corridor_width_mm, barrier_axis=axis)
        isolator_feasibility.append(feas)

        cvars = model.get_component(ref)
        if ref in relaxed:
            # Experiment-only K3 relaxation: this isolator's pad clusters are
            # free to land anywhere -- skip BOTH the rotation pin and the
            # straddle constraint (its pads need not clear the corridor on the
            # HV-lo/SELV-hi sides). The geometric verdict above is still
            # recorded for the decision record.
            continue
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
        relaxed_isolator_straddle=relaxed,
        setbacks=setbacks,
        pairing_feasibility=pairing_feasibility,
    )
    return report
