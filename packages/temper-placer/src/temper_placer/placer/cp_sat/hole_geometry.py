"""Drilled-hole placement constraints for CP-SAT: hole-to-hole and hole-to-edge.

**The gap this closes.** Before this module the CP-SAT placement model
constrained component *boxes* (``NoOverlap2D``, courtyard tau, netclass and
domain separations, the isolation barrier's per-pairing setbacks) and, for
isolators, individual *pad copper* projected onto the barrier axis. Nothing
constrained a **drilled hole** at all. Two fabrication rules the board is
actually checked against were therefore outside the model:

* ``hole_to_hole``  -- kicad-cli "Drilled hole too close to other hole",
  enforced by ``pcb/temper.kicad_dru``'s ``(rule "PTH hole to hole")``.
* board-edge clearance applied to holes -- kicad-cli "Board edge clearance
  violation", enforced by ``pcb/temper.kicad_pro``'s board-setup
  ``min_copper_edge_clearance``.

A solve could satisfy every box constraint and still return a placement whose
through-hole pads drill into each other or off the board, and nothing in the
pipeline would have rejected it before kicad-cli did.

**What this module adds.** Two HARD constraint families over the *real*
through-hole pad geometry of every placed component:

* **A. inter-component hole-to-hole.** For every pair of distinct components
  that both carry through-hole pads, an axis-projected Chebyshev separation
  at a margin derived from those two components' own hole geometry.
* **B. hole-to-board-edge.** For every component carrying through-hole pads,
  its hole discs must stay inside the board outline inset by the enforced
  edge clearance.

**Intra-footprint hole pairs are deliberately NOT constrained**, for the same
reason ``domain_clearance.py`` does not constrain intra-footprint domain
straddling: no placement decision can move a footprint's own pads relative to
each other. A footprint whose own holes violate ``hole_to_hole`` is a
footprint-library defect, and posting a constraint the solver cannot satisfy
would make the model spuriously infeasible for something placement does not
control. ``HoleGeometryReport.intra_footprint_violations`` surfaces any such
pair instead, so it is reported rather than silently skipped.

NO REQUIREMENT IS AUTHORED HERE
-------------------------------
Every figure this module posts is READ from the tree at call time:

* hole-to-hole: the strictest ``hole_to_hole`` ``(min ...)`` in the generated
  ``pcb/temper.kicad_dru``, taken together with ``pcb/temper.kicad_pro``'s
  board-setup ``min_hole_to_hole``. KiCad enforces the stricter of the two, so
  this module takes their **max**. On today's tree that is 0.5 mm (the DRU
  rule; the board-setup figure is 0.3 mm).
* hole-to-edge: ``pcb/temper.kicad_pro``'s ``min_copper_edge_clearance``
  (0.5 mm today). This is the figure kicad-cli actually checks a drilled hole
  against on this board -- verified directly against its own violation text,
  "Board edge clearance violation (board setup constraints edge clearance
  0.5000 mm; ...)".

  **There is no fabricator hole-to-board-edge figure in this repository.**
  Neither ``docs/hardware/FAB_CAPABILITY.md`` nor
  ``docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md`` quotes a
  JLCPCB minimum hole-to-board-edge distance; their sourced edge rows (5a,
  5b) are board-edge-to-**copper**, and their sourced hole rows (2a, 2b, 2c)
  are annular ring, minimum drill diameter, and hole-to-**copper**. The
  0.5 mm used here is this repo's own enforced design figure and is NOT
  claimed to be traceable to JLCPCB. The same is true of the 0.5 mm
  hole-to-hole figure.

``resolve_hole_requirements`` therefore takes no requirement argument at all,
and ``add_hole_geometry_to_model``'s optional overrides are accepted **only
when they are stricter than** the resolved tree figures. A caller-chosen
looser figure is exactly the mechanism by which a solve could be made feasible
by lowering a requirement, so it is refused with a ``ValueError`` rather than
honoured or silently clamped.

THE ENCODING, and why it is sound
---------------------------------
CP-SAT works on integer-scaled axis-aligned quantities, and a component's
position enters the model only as its box centre ``(x_center, y_center)`` plus
a rotation index. A hole's exact world position is therefore not a model
variable; what this module does is bound the true Euclidean hole-to-hole
distance below by a quantity that *is* linear in the model variables.

For component ``c`` define, over its through-hole pads ``k`` with local offset
``(ox_k, oy_k)`` (``Pin.position``, the same offset-from-box-centre frame
``isolation_barrier.py`` projects against ``cvars.x_center``) and hole radius
``r_k = drill_k / 2``::

    Ax(c) = max_k ( |ox_k| + r_k )        Ay(c) = max_k ( |oy_k| + r_k )

For two components ``i``, ``j`` with box centres ``c_i``, ``c_j`` and any
holes ``h_i in i``, ``h_j in j``, projecting on X::

    euclid(h_i, h_j) >= |h_ix - h_jx| >= |c_ix - c_jx| - |ox_i| - |ox_j|

so the edge-to-edge hole gap obeys::

    gap = euclid(h_i, h_j) - r_i - r_j
        >= |c_ix - c_jx| - (|ox_i| + r_i) - (|ox_j| + r_j)
        >= |c_ix - c_jx| - Ax(i) - Ax(j)

and symmetrically on Y. Hence **either** of::

    |c_ix - c_jx| >= Ax(i) + Ax(j) + H        |c_iy - c_jy| >= Ay(i) + Ay(j) + H

is sufficient for ``gap >= H`` for *every* hole pair across the two
components. That disjunction is exactly the Chebyshev encoding
``handlers/separated.py`` already uses (four direction Booleans, two axis
Booleans, one ``AddBoolOr``), so this module reuses that shape.

Because an axis projection lower-bounds the Euclidean distance, the encoding
can only ever **over**-constrain -- it never admits a placement whose true
hole-to-hole distance is below ``H``. Conservatism is the price: a pair
separated diagonally may be forced further apart than the true requirement
strictly needs.

**Rotation is handled exactly, not conservatively.** The model's four
rotations map a local offset by (``isolation_barrier._project_onto_barrier_axis``,
the sanctioned table, pinned to ``geometry.kicad_transform``, and independently
re-verified against kicad-cli's own reported pad coordinates)::

    rot=0: ( lx,  ly)   rot=1: ( ly, -lx)   rot=2: (-lx, -ly)   rot=3: (-ly,  lx)

so ``|gx|`` takes the value ``|lx|`` at even rotations and ``|ly|`` at odd
ones. ``Ax`` and ``Ay`` therefore simply **swap** on odd rotations, and the
active value is selected with the same ``AddElement`` table shape
``model.add_rotation`` already uses for ``x_size``/``y_size``
(``[Ax, Ay, Ax, Ay]``). No rotation case is approximated by a worst-case max.

Family B uses the same ``Ax``/``Ay`` selection against the board outline. The
outline is required to be an axis-aligned rectangle matching the board
dimensions the solver was given; a non-rectangular outline is **refused**
rather than approximated by its bounding box, because a bounding-box
approximation of a concave outline would be *unsound* in the other direction
(it would permit holes outside the real board).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from temper_placer.placer.cp_sat.model import CpSatModel

logger = logging.getLogger(__name__)

#: Repo root, resolved from this file's location the same way
#: ``_encoder_solve.py`` resolves ``configs/netclass_rules.yaml``.
_REPO_ROOT = Path(__file__).resolve().parents[6]

DEFAULT_DRU_PATH = _REPO_ROOT / "pcb" / "temper.kicad_dru"
DEFAULT_PRO_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pro"

_HOLE_TO_HOLE_RE = re.compile(
    r"\(\s*constraint\s+hole_to_hole\s+\(\s*min\s+([0-9]*\.?[0-9]+)\s*mm\s*\)", re.I
)


class HoleRequirementUnavailableError(RuntimeError):
    """Neither the DRU nor the board setup declares a needed hole figure.

    Fail closed: a placer that silently fell back to a built-in default here
    would be authoring a fabrication requirement, which is exactly what this
    module's contract forbids.
    """


@dataclass(frozen=True)
class HoleRequirements:
    """The enforced hole figures, with the provenance of each."""

    hole_to_hole_mm: float
    hole_to_edge_mm: float
    hole_to_hole_source: str
    hole_to_edge_source: str
    #: True when a fabricator-sourced figure backs the value. Both are False
    #: today -- see this module's docstring. Carried so a caller can report
    #: the distinction rather than implying a fab traceability that does not
    #: exist.
    hole_to_hole_fab_sourced: bool = False
    hole_to_edge_fab_sourced: bool = False


def resolve_hole_requirements(
    dru_path: Path | None = None,
    pro_path: Path | None = None,
    dru_text: str | None = None,
) -> HoleRequirements:
    """Read the enforced hole-to-hole and hole-to-edge figures from the tree.

    Takes no requirement argument by design; see the module docstring.
    ``dru_text`` supplies DRU content directly instead of generating/reading it
    -- an injection point for tests, and the only way to exercise the
    "no DRU resolvable" branch, since the in-process generator would otherwise
    always succeed inside this repo.
    """
    import json

    dru_path = dru_path or DEFAULT_DRU_PATH
    pro_path = pro_path or DEFAULT_PRO_PATH

    # pcb/temper.kicad_dru is a GENERATED artifact and is not committed, so
    # reading the file alone would find nothing on a clean checkout and leave
    # only pcb/temper.kicad_pro's 0.3mm -- which is LOOSER than the 0.5mm the
    # generator emits and KiCad actually enforces. Solving against the looser
    # figure while the DRC enforces the stricter one is precisely the silent
    # under-constraint this module exists to remove, so the generator is run
    # in-process first (the same `generate_dru()` call the repo's own
    # ci_check_drc / measure-board harnesses use), and the committed file is
    # only a fallback.
    dru_origin = "caller-supplied dru_text"
    if dru_text is None:
        try:
            import sys

            scripts_dir = str(_REPO_ROOT / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            from generate_kicad_dru import generate_dru  # type: ignore[import-not-found]

            dru_text = generate_dru()
            dru_origin = "scripts/generate_kicad_dru.py::generate_dru() [in-process]"
        except Exception:  # noqa: BLE001 - fall back to the on-disk artifact
            logger.debug("in-process DRU generation unavailable", exc_info=True)
            if dru_path.exists():
                dru_text = dru_path.read_text(encoding="utf-8")
                dru_origin = f"{dru_path.name} (on disk)"

    dru_min: float | None = None
    if dru_text is not None:
        found = [float(m) for m in _HOLE_TO_HOLE_RE.findall(dru_text)]
        if found:
            # KiCad's last-matching-rule-wins precedence is normalised by
            # generate_kicad_dru.order_rules_by_strictness so the strictest
            # matching rule wins; take the max for the same fail-closed reason.
            dru_min = max(found)

    pro_h2h: float | None = None
    pro_edge: float | None = None
    if pro_path.exists():
        rules = (
            json.loads(pro_path.read_text(encoding="utf-8"))
            .get("board", {})
            .get("design_settings", {})
            .get("rules", {})
        )
        if "min_hole_to_hole" in rules:
            pro_h2h = float(rules["min_hole_to_hole"])
        if "min_copper_edge_clearance" in rules:
            pro_edge = float(rules["min_copper_edge_clearance"])

    if dru_min is None:
        raise HoleRequirementUnavailableError(
            "no hole_to_hole rule could be resolved from the DRU (tried "
            f"in-process generation and {dru_path}). Refusing to fall back on "
            f"{pro_path.name}'s board-setup min_hole_to_hole alone: that figure "
            "is LOOSER than the one the generator emits, so solving against it "
            "would silently under-constrain relative to what the DRC enforces."
        )

    candidates = {
        f"{dru_origin} (rule 'PTH hole to hole')": dru_min,
        f"{pro_path.name} design_settings.rules.min_hole_to_hole": pro_h2h,
    }
    present = {k: v for k, v in candidates.items() if v is not None}
    h2h_source = max(present, key=lambda k: present[k])
    h2h = present[h2h_source]
    if len(present) > 1:
        h2h_source += " (strictest of " + ", ".join(sorted(present)) + ")"

    if pro_edge is None:
        raise HoleRequirementUnavailableError(
            f"{pro_path} declares no design_settings.rules."
            "min_copper_edge_clearance; this is the figure kicad-cli checks a "
            "drilled hole against and there is no fabricator hole-to-edge "
            "figure in-tree to fall back on (see this module's docstring)"
        )

    return HoleRequirements(
        hole_to_hole_mm=h2h,
        hole_to_edge_mm=pro_edge,
        hole_to_hole_source=h2h_source,
        hole_to_edge_source=f"{pro_path.name} design_settings.rules.min_copper_edge_clearance",
    )


@dataclass(frozen=True)
class ComponentHoles:
    """One component's through-hole extent, in its local box-centre frame."""

    ref: str
    n_holes: int
    #: ``max_k(|ox_k| + r_k)`` at rotation 0.
    ax_mm: float
    #: ``max_k(|oy_k| + r_k)`` at rotation 0.
    ay_mm: float
    #: Smallest edge-to-edge gap between two of this component's OWN holes,
    #: or ``None`` when it has fewer than two. Placement cannot change it.
    min_intra_gap_mm: float | None


@dataclass
class HoleGeometryReport:
    """What ``add_hole_geometry_to_model`` actually posted."""

    requirements: HoleRequirements
    holes_by_ref: dict[str, ComponentHoles] = field(default_factory=dict)
    refs_without_holes: list[str] = field(default_factory=list)
    pairs_constrained: int = 0
    edge_constrained_refs: list[str] = field(default_factory=list)
    #: ``(ref, gap_mm)`` for footprints whose OWN holes are closer than the
    #: hole-to-hole figure. Reported, never constrained -- see the module
    #: docstring.
    intra_footprint_violations: list[tuple[str, float]] = field(default_factory=list)
    constraint_ids: list[str] = field(default_factory=list)

    def summary(self) -> str:
        r = self.requirements
        return (
            f"hole geometry: {len(self.holes_by_ref)} components with through-holes, "
            f"{self.pairs_constrained} inter-component pairs at "
            f"{r.hole_to_hole_mm:.3f}mm, {len(self.edge_constrained_refs)} refs "
            f"edge-constrained at {r.hole_to_edge_mm:.3f}mm, "
            f"{len(self.intra_footprint_violations)} intra-footprint violations "
            f"(reported, not constrained)"
        )


class UnhandledDrillError(ValueError):
    """A drill representation this module does not know how to bound.

    Raised rather than skipped. A silent skip is the exact failure mode this
    repo has been bitten by (AGENTS.md: "a constraint operand that resolves to
    nothing is a silent no-op"): the pad would simply not be constrained, the
    solve would come back SAT, and nothing would say the hole was never
    considered.
    """


def _pin_hole(pin: Any) -> tuple[float, float, float] | None:
    """``(radius_x, radius_y, extra_offset)`` for *pin*'s drilled hole, or None.

    ``Pin.drill`` is NOT uniformly a float on this parser: SMD pads carry the
    float ``0.0``, while a through-hole pad carries a ``DrillDefinition``
    pyclass (``oval``/``diameter``/``width``/``offset``) -- see
    ``temper-design-bundle/src/parse_engine.rs``'s module docstring,
    "``DrillDefinition`` objects (not floats) flow into ``Pin.drill``". A
    ``float(pin.drill)`` on the pyclass raises ``TypeError``, so a
    try/except-float test silently classifies EVERY real through-hole pad as
    drill-free. That bug produced "0 components with drilled holes" on a board
    with 94 of them; both shapes are handled explicitly here for that reason.

    ``Pin.is_pth`` is deliberately not the test: it distinguishes *plated*
    from non-plated, and an NPTH mounting hole is still a drilled hole that
    participates in ``hole_to_hole`` and the board-edge check.
    """
    drill = getattr(pin, "drill", None)
    if drill is None:
        return None
    if isinstance(drill, (int, float)):
        d = float(drill)
        if d <= 0.0:
            return None
        return (d / 2.0, d / 2.0, 0.0)

    diameter = getattr(drill, "diameter", None)
    if diameter is None:
        # A ``(drill (offset ...))`` token with no diameter -- parse_engine.rs
        # calls this out as a real kiutils-era shape. There is no hole size to
        # bound, so refuse rather than guess one.
        raise UnhandledDrillError(
            f"pad {getattr(pin, 'number', '?')!r} has a drill token with no "
            f"diameter ({drill!r}); cannot bound its hole"
        )
    d = float(diameter)
    if d <= 0.0:
        return None
    w = getattr(drill, "width", None)
    if getattr(drill, "oval", False) and w is not None:
        # An oval drill is a stadium of ``diameter`` x ``width`` in the PAD's
        # own local frame, which carries its own rotation independent of the
        # component's. Bounding both axes by the larger half-dimension is the
        # rotation-free sound envelope.
        r = max(d, float(w)) / 2.0
        rx = ry = r
    else:
        rx = ry = d / 2.0

    extra = 0.0
    off = getattr(drill, "offset", None)
    if off is not None:
        # The hole centre is displaced from the pad centre, in the pad's own
        # rotated frame. Rather than model that rotation, absorb the full
        # displacement magnitude into BOTH axis radii -- sound for any pad
        # rotation, at the cost of conservatism on a shape this board does not
        # currently use.
        try:
            ox_o, oy_o = float(off[0]), float(off[1])
        except (TypeError, ValueError, IndexError, KeyError):
            ox_o = float(getattr(off, "x", 0.0))
            oy_o = float(getattr(off, "y", 0.0))
        extra = max(abs(ox_o), abs(oy_o))
    return (rx + extra, ry + extra, extra)


def extract_component_holes(comp: Any) -> ComponentHoles | None:
    """Build one component's :class:`ComponentHoles`, or ``None`` if drill-free."""
    import math

    offsets: list[tuple[float, float, float, float]] = []
    for pin in getattr(comp, "pins", ()) or ():
        hole = _pin_hole(pin)
        if hole is None:
            continue
        rx, ry, _extra = hole
        ox, oy = pin.position
        offsets.append((float(ox), float(oy), rx, ry))
    if not offsets:
        return None

    ax = max(abs(ox) + rx for ox, _oy, rx, _ry in offsets)
    ay = max(abs(oy) + ry for _ox, oy, _rx, ry in offsets)

    min_intra: float | None = None
    for a in range(len(offsets)):
        xa, ya, rxa, rya = offsets[a]
        for b in range(a + 1, len(offsets)):
            xb, yb, rxb, ryb = offsets[b]
            gap = math.hypot(xa - xb, ya - yb) - max(rxa, rya) - max(rxb, ryb)
            if min_intra is None or gap < min_intra:
                min_intra = gap

    return ComponentHoles(
        ref=comp.ref, n_holes=len(offsets), ax_mm=ax, ay_mm=ay, min_intra_gap_mm=min_intra
    )


def _axis_extent_vars(model: CpSatModel, ref: str, holes: ComponentHoles) -> tuple[Any, Any]:
    """Rotation-selected ``(Ax, Ay)`` in model units for *ref*.

    ``Ax``/``Ay`` swap on odd rotations (module docstring). Selected with the
    same ``AddElement`` table shape ``model.add_rotation`` uses for the size
    variables, so the extent a constraint sees and the box size the solver
    sees are always driven by the identical ``rot_ref``.
    """
    ax_u = model.mm_to_units(holes.ax_mm)
    ay_u = model.mm_to_units(holes.ay_mm)
    cvars = model.get_component(ref)
    rot = cvars.rot_ref

    lo, hi = min(ax_u, ay_u), max(ax_u, ay_u)
    if rot is None or lo == hi:
        # No rotation variable (or a hole field that is square in extent):
        # the two orientations are indistinguishable, so a constant is exact.
        return (
            model.model_ref.NewConstant(ax_u),
            model.model_ref.NewConstant(ay_u),
        )

    ax_var = model.new_int_var(lo, hi, f"hole_ax_{ref}")
    ay_var = model.new_int_var(lo, hi, f"hole_ay_{ref}")
    model.model_ref.AddElement(rot, [ax_u, ay_u, ax_u, ay_u], ax_var)
    model.model_ref.AddElement(rot, [ay_u, ax_u, ay_u, ax_u], ay_var)
    return ax_var, ay_var


def _require_rect_outline(
    board_w_mm: float, board_h_mm: float, outline: tuple[float, float, float, float] | None
) -> tuple[float, float, float, float]:
    """Validate the placement frame's board rectangle, or refuse.

    The solver's frame is ``[0, board_w] x [0, board_h]`` (see
    ``_encoder_solve.solve_placement``, which normalises against Edge.Cuts).
    A caller may pass an explicit rectangle; anything that is not a rectangle
    matching those dimensions is refused rather than approximated -- a
    bounding box of a concave outline would let holes sit outside the real
    board, which is unsound in the direction that matters.
    """
    if outline is None:
        return (0.0, 0.0, float(board_w_mm), float(board_h_mm))
    x0, y0, x1, y1 = (float(v) for v in outline)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"degenerate board outline rectangle {outline!r}")
    if abs((x1 - x0) - float(board_w_mm)) > 1e-6 or abs((y1 - y0) - float(board_h_mm)) > 1e-6:
        raise ValueError(
            f"board outline {outline!r} spans {x1 - x0:.4f} x {y1 - y0:.4f} mm but the "
            f"solver frame is {board_w_mm} x {board_h_mm} mm; refusing to encode a "
            "hole-to-edge constraint against a frame the solver does not share"
        )
    return (x0, y0, x1, y1)


def add_hole_geometry_to_model(
    model: CpSatModel,
    netlist: Any,
    *,
    board_w_mm: float,
    board_h_mm: float,
    board_outline: tuple[float, float, float, float] | None = None,
    hole_to_hole_mm: float | None = None,
    hole_to_edge_mm: float | None = None,
    dru_path: Path | None = None,
    pro_path: Path | None = None,
    dru_text: str | None = None,
    enforce_hole_to_hole: bool = True,
    enforce_hole_to_edge: bool = True,
) -> HoleGeometryReport:
    """Post the hole-to-hole and hole-to-edge HARD constraints.

    Must be called AFTER every component is registered on *model* (it calls
    ``model.get_component``), same contract as
    ``isolation_barrier.add_isolation_barrier_to_model``.

    ``hole_to_hole_mm``/``hole_to_edge_mm`` are accepted only when **stricter
    than or equal to** the figures resolved from the tree; a looser override
    raises ``ValueError``. See the module docstring for why.
    """
    reqs = resolve_hole_requirements(
        dru_path=dru_path, pro_path=pro_path, dru_text=dru_text
    )

    if hole_to_hole_mm is not None:
        if hole_to_hole_mm < reqs.hole_to_hole_mm:
            raise ValueError(
                f"hole_to_hole_mm={hole_to_hole_mm} is LOOSER than the enforced "
                f"{reqs.hole_to_hole_mm}mm from {reqs.hole_to_hole_source}; a "
                "caller-supplied requirement may only tighten, never relax"
            )
        reqs = HoleRequirements(
            hole_to_hole_mm=hole_to_hole_mm,
            hole_to_edge_mm=reqs.hole_to_edge_mm,
            hole_to_hole_source=f"caller override (tightens {reqs.hole_to_hole_source})",
            hole_to_edge_source=reqs.hole_to_edge_source,
        )
    if hole_to_edge_mm is not None:
        if hole_to_edge_mm < reqs.hole_to_edge_mm:
            raise ValueError(
                f"hole_to_edge_mm={hole_to_edge_mm} is LOOSER than the enforced "
                f"{reqs.hole_to_edge_mm}mm from {reqs.hole_to_edge_source}; a "
                "caller-supplied requirement may only tighten, never relax"
            )
        reqs = HoleRequirements(
            hole_to_hole_mm=reqs.hole_to_hole_mm,
            hole_to_edge_mm=hole_to_edge_mm,
            hole_to_hole_source=reqs.hole_to_hole_source,
            hole_to_edge_source=f"caller override (tightens {reqs.hole_to_edge_source})",
        )

    report = HoleGeometryReport(requirements=reqs)

    registered = set(model.component_map.keys())
    for comp in netlist.components:
        if comp.ref not in registered:
            continue
        holes = extract_component_holes(comp)
        if holes is None:
            report.refs_without_holes.append(comp.ref)
            continue
        report.holes_by_ref[comp.ref] = holes
        if holes.min_intra_gap_mm is not None and holes.min_intra_gap_mm < reqs.hole_to_hole_mm:
            report.intra_footprint_violations.append((comp.ref, holes.min_intra_gap_mm))

    if report.intra_footprint_violations:
        logger.warning(
            "hole_geometry: %d footprint(s) have their OWN holes closer than "
            "%.3fmm; no placement can fix an intra-footprint gap, so these are "
            "REPORTED, not constrained: %s",
            len(report.intra_footprint_violations),
            reqs.hole_to_hole_mm,
            ", ".join(f"{r}={g:.3f}mm" for r, g in report.intra_footprint_violations),
        )

    refs = sorted(report.holes_by_ref)
    if not refs:
        logger.info("hole_geometry: no component carries a drilled hole; nothing posted")
        return report

    extents = {ref: _axis_extent_vars(model, ref, report.holes_by_ref[ref]) for ref in refs}

    # ---- family A: inter-component hole-to-hole ----------------------------
    if enforce_hole_to_hole:
        h2h_u = model.mm_to_units(reqs.hole_to_hole_mm)
        for a in range(len(refs)):
            ra = refs[a]
            va = model.get_component(ra)
            ax_a, ay_a = extents[ra]
            for b in range(a + 1, len(refs)):
                rb = refs[b]
                vb = model.get_component(rb)
                ax_b, ay_b = extents[rb]

                left = model.new_bool_var(f"h2h_left_{ra}_{rb}")
                right = model.new_bool_var(f"h2h_right_{ra}_{rb}")
                below = model.new_bool_var(f"h2h_below_{ra}_{rb}")
                above = model.new_bool_var(f"h2h_above_{ra}_{rb}")

                # |c_ax - c_bx| >= Ax(a) + Ax(b) + H, split into its two sides.
                model.model_ref.Add(
                    vb.x_center - va.x_center >= ax_a + ax_b + h2h_u
                ).OnlyEnforceIf(left)
                model.model_ref.Add(
                    va.x_center - vb.x_center >= ax_a + ax_b + h2h_u
                ).OnlyEnforceIf(right)
                model.model_ref.Add(
                    vb.y_center - va.y_center >= ay_a + ay_b + h2h_u
                ).OnlyEnforceIf(below)
                model.model_ref.Add(
                    va.y_center - vb.y_center >= ay_a + ay_b + h2h_u
                ).OnlyEnforceIf(above)

                model.model_ref.AddBoolOr([left, right, below, above])
                report.pairs_constrained += 1
                report.constraint_ids.append(f"hole_to_hole_{ra}_{rb}")

    # ---- family B: hole-to-board-edge --------------------------------------
    if enforce_hole_to_edge:
        x0, y0, x1, y1 = _require_rect_outline(board_w_mm, board_h_mm, board_outline)
        edge_u = model.mm_to_units(reqs.hole_to_edge_mm)
        x_lo = model.mm_to_units(x0) + edge_u
        y_lo = model.mm_to_units(y0) + edge_u
        x_hi = model.mm_to_units(x1) - edge_u
        y_hi = model.mm_to_units(y1) - edge_u
        for ref in refs:
            cv = model.get_component(ref)
            ax_v, ay_v = extents[ref]
            model.model_ref.Add(cv.x_center - ax_v >= x_lo)
            model.model_ref.Add(cv.x_center + ax_v <= x_hi)
            model.model_ref.Add(cv.y_center - ay_v >= y_lo)
            model.model_ref.Add(cv.y_center + ay_v <= y_hi)
            report.edge_constrained_refs.append(ref)
            report.constraint_ids.append(f"hole_to_edge_{ref}")

    logger.info("hole_geometry: %s", report.summary())
    return report


__all__ = [
    "ComponentHoles",
    "HoleGeometryReport",
    "HoleRequirementUnavailableError",
    "HoleRequirements",
    "add_hole_geometry_to_model",
    "extract_component_holes",
    "resolve_hole_requirements",
]
