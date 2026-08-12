#!/usr/bin/env python3
"""CP-SAT cross-engine equivalence harness (Wave-4 BLOCKER-ORTOOLS decidability).

# provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 dirty=false

Companion to ``docs/evidence/2026-08-07-cpsat-equivalence-harness.md``.

This file has two independent halves:

1. ``IndependentVerifier`` — given a placement model (component sizes, PCL
   constraints, board bounds/zones/loops) and a proposed assignment
   (positions + rotations), re-checks every constraint DIRECTLY from its
   geometric definition, in pure Python, without ever constructing a
   ``cp_model.CpModel`` or asking a solver anything. This is the keystone
   piece the task asks for: it converts "do two solvers agree?" (usually
   unanswerable across engines) into "is this solution valid?" (decidable
   for any engine's output, including OR-Tools' own).

   Each check below is a direct transcription of the corresponding
   ``handlers/*.py`` docstring's encoding (cited in the docstring of each
   ``_check_*`` method) — re-derived independently from the *semantics*,
   not from reading the CP-SAT variables OR-Tools built.

2. ``Engine`` / ``OrToolsEngine`` / ``DifferentialHarness`` — a pluggable
   "solve a model, get an assignment" abstraction, and a runner that solves
   a corpus of real encoder models multiple times (varying seed and/or
   thread count) and reports agreement across four tiers: feasibility
   parity, objective parity, solution-set membership (independent verifier
   pass rate), and same-config determinism.

Usage:
    uv run --no-sync python docs/evidence/2026-08-07-cpsat-equivalence-harness.py

Writes ``docs/evidence/2026-08-07-cpsat-equivalence-summary.json``.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACER_ROOT = REPO_ROOT / "packages" / "temper-placer"
PLACER_SRC = PLACER_ROOT / "src"
if str(PLACER_SRC) not in sys.path:
    sys.path.insert(0, str(PLACER_SRC))

from temper_placer.core.netlist import Component, Netlist  # noqa: E402
from temper_placer.pcl.constraints import (  # noqa: E402
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BaseConstraint,
    BoardSide,
    ConstraintTier,
    DistanceMetric,
    EdgeType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.placer.cp_sat import _encoder_core  # noqa: E402
from temper_placer.placer.cp_sat._encoder_solve import courtyard_clearance_mm  # noqa: E402
from temper_placer.placer.cp_sat.encoder import solve_placement  # noqa: E402

# Grid quantum: solve_placement uses units_per_mm=100, so 1 model unit =
# 0.01mm, and mm_to_units() round-half-even can shift an mm value by up to
# half a unit either way. Every geometric check below tolerates this much
# slack -- and no more -- before calling something a violation, so the
# verifier is checking real constraint satisfaction, not solver rounding.
GRID_TOL_MM = 0.02
COPPER_EDGE_CLEARANCE_MM = 0.5  # must match _encoder_solve.py's own constant


# ===========================================================================
# 1. Independent solution verifier
# ===========================================================================


@dataclass
class Violation:
    constraint_id: str
    ctype: str
    detail: str


@dataclass
class VerificationResult:
    ok: bool
    violations: list[Violation] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "PASS"
        return f"FAIL ({len(self.violations)} violation(s)): " + "; ".join(
            f"{v.ctype}/{v.constraint_id}: {v.detail}" for v in self.violations[:5]
        )


@dataclass
class PlacementModel:
    """Everything the verifier needs, independent of how it was solved.

    ``constraints`` must already include the auto-generated courtyard-tau
    SEPARATED pairs (see ``build_courtyard_constraints`` below) -- the
    verifier does not infer them, it checks exactly the constraint list it
    is given, the same fail-closed discipline the encoder itself uses.
    """

    board_w_mm: float
    board_h_mm: float
    sizes_mm: dict[str, tuple[float, float]]  # ref -> (w0, h0), unrotated
    constraints: list[BaseConstraint]
    zones: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    zone_components: dict[str, list[str]] = field(default_factory=dict)
    loop_components: dict[str, list[str]] = field(default_factory=dict)
    edge_margin_mm: float = COPPER_EDGE_CLEARANCE_MM


def _component_box(
    model: PlacementModel, ref: str, positions: dict[str, tuple[float, float]], rotations: dict[str, int]
) -> tuple[float, float, float, float]:
    """(x_min, y_min, x_max, y_max) in mm, honoring the encoder's 4-way
    rotation convention: rot in {0,2} keeps (w0,h0); rot in {1,3} swaps to
    (h0,w0) -- transcribed from ``model.py::add_rotation``'s AddElement
    tables ``[w0,h0,w0,h0]`` / ``[h0,w0,h0,w0]``."""
    w0, h0 = model.sizes_mm[ref]
    rot = rotations.get(ref, 0)
    w, h = (w0, h0) if rot in (0, 2) else (h0, w0)
    cx, cy = positions[ref]
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _resolve(name: str, comp_refs: set[str], zone_components: dict[str, list[str]]) -> list[str]:
    if name in comp_refs:
        return [name]
    return [r for r in zone_components.get(name, []) if r in comp_refs]


class IndependentVerifier:
    """Checks a (model, assignment) pair against every constraint directly.

    Never touches OR-Tools, never reads a solver variable. Reusable against
    ANY engine's output, and against OR-Tools' own as a self-check (task
    requirement).
    """

    def verify(
        self, model: PlacementModel, positions: dict[str, tuple[float, float]], rotations: dict[str, int]
    ) -> VerificationResult:
        violations: list[Violation] = []
        comp_refs = set(model.sizes_mm.keys())
        if set(positions.keys()) != comp_refs:
            missing = comp_refs - set(positions)
            extra = set(positions) - comp_refs
            violations.append(
                Violation("<assignment>", "shape", f"missing={missing} extra={extra}")
            )
            return VerificationResult(False, violations)

        boxes = {ref: _component_box(model, ref, positions, rotations) for ref in comp_refs}

        # Board-bounds / edge-margin (C2 in the spike's enumeration).
        for ref, (x0, y0, x1, y1) in boxes.items():
            if (
                x0 < model.edge_margin_mm - GRID_TOL_MM
                or y0 < model.edge_margin_mm - GRID_TOL_MM
                or x1 > model.board_w_mm - model.edge_margin_mm + GRID_TOL_MM
                or y1 > model.board_h_mm - model.edge_margin_mm + GRID_TOL_MM
            ):
                violations.append(
                    Violation(
                        f"bounds_{ref}",
                        "board_bounds",
                        f"box=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}) board=({model.board_w_mm},{model.board_h_mm}) margin={model.edge_margin_mm}",
                    )
                )

        # Global pairwise no-overlap (C6, AddNoOverlap2D redundant global).
        # Strictly weaker than SEPARATED (touching allowed); kept as an
        # independent class-C6 check per the enumeration, not derived from
        # the SEPARATED check below.
        for ra, rb in itertools.combinations(sorted(comp_refs), 2):
            ax0, ay0, ax1, ay1 = boxes[ra]
            bx0, by0, bx1, by1 = boxes[rb]
            ox = min(ax1, bx1) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > GRID_TOL_MM and oy > GRID_TOL_MM:
                violations.append(
                    Violation(f"overlap_{ra}_{rb}", "no_overlap_2d", f"overlap=({ox:.3f},{oy:.3f})mm")
                )

        for c in model.constraints:
            violations.extend(self._check_one(c, model, boxes, positions, comp_refs))

        return VerificationResult(len(violations) == 0, violations)

    # -- per-constraint-class checks, one per handlers/*.py -----------------

    def _check_one(
        self,
        c: BaseConstraint,
        model: PlacementModel,
        boxes: dict[str, tuple[float, float, float, float]],
        positions: dict[str, tuple[float, float]],
        comp_refs: set[str],
    ) -> list[Violation]:
        if isinstance(c, SeparatedConstraint):
            return self._check_separated(c, boxes, comp_refs, model.zone_components)
        if isinstance(c, AdjacentConstraint):
            return self._check_adjacent(c, boxes, positions)
        if isinstance(c, AlignedConstraint):
            return self._check_aligned(c, positions)
        if isinstance(c, AnchoredConstraint):
            return self._check_anchored(c, boxes, positions)
        if isinstance(c, EnclosingConstraint):
            return self._check_enclosing(c, boxes, model.zones)
        if isinstance(c, KeepoutConstraint):
            return self._check_keepout(c, boxes, model.zones)
        if isinstance(c, OnSideConstraint):
            return self._check_onside(c, boxes, model)
        if isinstance(c, LoopAreaConstraint):
            return self._check_loop_area(c, boxes, model.loop_components)
        return []

    def _check_separated(self, c, boxes, comp_refs, zone_components) -> list[Violation]:
        """handlers/separated.py: Chebyshev disjunction -- gap on x OR y >= margin."""
        out = []
        refs_a = _resolve(c.a, comp_refs, zone_components)
        refs_b = _resolve(c.b, comp_refs, zone_components)
        for ra in refs_a:
            for rb in refs_b:
                if ra == rb:
                    continue
                ax0, ay0, ax1, ay1 = boxes[ra]
                bx0, by0, bx1, by1 = boxes[rb]
                gap_x = max(ax0 - bx1, bx0 - ax1)
                gap_y = max(ay0 - by1, by0 - ay1)
                if gap_x < c.min_distance_mm - GRID_TOL_MM and gap_y < c.min_distance_mm - GRID_TOL_MM:
                    out.append(
                        Violation(
                            c.id,
                            "separated",
                            f"{ra}<->{rb} gap=({gap_x:.4f},{gap_y:.4f}) need>={c.min_distance_mm}",
                        )
                    )
        return out

    def _check_adjacent(self, c, boxes, positions) -> list[Violation]:
        """handlers/adjacent.py: both axes bounded (AND, not OR)."""
        if c.a not in boxes or c.b not in boxes:
            return []
        max_d = c.max_distance_mm
        metric = getattr(c, "metric", DistanceMetric.EDGE_TO_EDGE)
        if metric == DistanceMetric.CENTER_TO_CENTER:
            ax, ay = positions[c.a]
            bx, by = positions[c.b]
            dx, dy = abs(ax - bx), abs(ay - by)
        else:
            ax0, ay0, ax1, ay1 = boxes[c.a]
            bx0, by0, bx1, by1 = boxes[c.b]
            dx = max(ax0 - bx1, bx0 - ax1)
            dy = max(ay0 - by1, by0 - ay1)
        if dx > max_d + GRID_TOL_MM or dy > max_d + GRID_TOL_MM:
            return [Violation(c.id, "adjacent", f"{c.a}<->{c.b} d=({dx:.4f},{dy:.4f}) need<={max_d}")]
        return []

    def _check_aligned(self, c, positions) -> list[Violation]:
        """handlers/aligned.py: pairwise center-coordinate tolerance on one axis."""
        out = []
        axis_idx = 0 if c.axis.value in ("x", "major") else 1
        refs = [r for r in c.components if r in positions]
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                va = positions[refs[i]][axis_idx]
                vb = positions[refs[j]][axis_idx]
                if abs(va - vb) > c.tolerance_mm + GRID_TOL_MM:
                    out.append(
                        Violation(
                            c.id,
                            "aligned",
                            f"{refs[i]}<->{refs[j]} d={abs(va - vb):.4f} need<={c.tolerance_mm}",
                        )
                    )
        return out

    def _check_anchored(self, c, boxes, positions) -> list[Violation]:
        """handlers/anchored.py: exact position or hard region."""
        if c.component not in positions:
            return []
        if c.position is not None:
            px, py = c.position
            cx, cy = positions[c.component]
            if abs(cx - px) > GRID_TOL_MM or abs(cy - py) > GRID_TOL_MM:
                return [
                    Violation(
                        c.id, "anchored", f"{c.component} pos=({cx:.4f},{cy:.4f}) need=({px},{py})"
                    )
                ]
            return []
        rx0, ry0, rx1, ry1 = c.region
        x0, y0, x1, y1 = boxes[c.component]
        if x0 < rx0 - GRID_TOL_MM or y0 < ry0 - GRID_TOL_MM or x1 > rx1 + GRID_TOL_MM or y1 > ry1 + GRID_TOL_MM:
            return [
                Violation(
                    c.id,
                    "anchored",
                    f"{c.component} box=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}) region={c.region}",
                )
            ]
        return []

    def _check_enclosing(self, c, boxes, zones) -> list[Violation]:
        """handlers/enclosing.py: box inside zone shrunk by margin_mm."""
        zone = zones.get(c.outer)
        if zone is None:
            return []
        zx0, zy0, zx1, zy1 = zone
        m = c.margin_mm
        out = []
        for ref in c.inner:
            if ref not in boxes:
                continue
            x0, y0, x1, y1 = boxes[ref]
            if (
                x0 < zx0 + m - GRID_TOL_MM
                or y0 < zy0 + m - GRID_TOL_MM
                or x1 > zx1 - m + GRID_TOL_MM
                or y1 > zy1 - m + GRID_TOL_MM
            ):
                out.append(
                    Violation(
                        c.id,
                        "enclosing",
                        f"{ref} box=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}) zone={zone} margin={m}",
                    )
                )
        return out

    def _check_keepout(self, c, boxes, zones) -> list[Violation]:
        """handlers/keepout.py: zone expanded by margin_mm; no positive-area overlap."""
        zone = zones.get(c.zone_name)
        if zone is None:
            return []
        zx0, zy0, zx1, zy1 = zone
        m = c.margin_mm
        kx0, ky0, kx1, ky1 = zx0 - m, zy0 - m, zx1 + m, zy1 + m
        out = []
        for ref, (x0, y0, x1, y1) in boxes.items():
            ox = min(x1, kx1) - max(x0, kx0)
            oy = min(y1, ky1) - max(y0, ky0)
            if ox > GRID_TOL_MM and oy > GRID_TOL_MM:
                out.append(
                    Violation(
                        c.id,
                        "keepout",
                        f"{ref} box=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}) keepout=({kx0:.3f},{ky0:.3f},{kx1:.3f},{ky1:.3f})",
                    )
                )
        return out

    def _check_onside(self, c, boxes, model: PlacementModel) -> list[Violation]:
        """handlers/onside.py: box within max_distance_mm of the named edge."""
        side = c.side.value
        max_d = c.max_distance_mm
        out = []
        for ref in c.components:
            if ref not in boxes:
                continue
            x0, y0, x1, y1 = boxes[ref]
            ok = True
            if side == "left":
                ok = x0 <= 0.0 + max_d + GRID_TOL_MM
            elif side == "right":
                ok = x1 >= model.board_w_mm - max_d - GRID_TOL_MM
            elif side == "top":
                ok = y1 >= model.board_h_mm - max_d - GRID_TOL_MM
            elif side == "bottom":
                ok = y0 <= 0.0 + max_d + GRID_TOL_MM
            if not ok:
                out.append(
                    Violation(
                        c.id, "on_side", f"{ref} box=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}) side={side}"
                    )
                )
        return out

    def _check_loop_area(self, c, boxes, loop_components) -> list[Violation]:
        """handlers/loop_area.py: AABB area of the loop's components <= ceiling.

        Ceiling gets a +0.01mm^2 slack matching the handler's own documented
        rounding quantum (mm_to_units even-rounds at 0.01mm resolution).
        """
        comps = loop_components.get(c.loop_name, [])
        comp_boxes = [boxes[r] for r in comps if r in boxes]
        if not comp_boxes:
            return []
        x0 = min(b[0] for b in comp_boxes)
        y0 = min(b[1] for b in comp_boxes)
        x1 = max(b[2] for b in comp_boxes)
        y1 = max(b[3] for b in comp_boxes)
        area = (x1 - x0) * (y1 - y0)
        if area > c.max_area_mm2 + 0.01 + GRID_TOL_MM * max(x1 - x0, y1 - y0, 1.0):
            return [
                Violation(
                    c.id, "loop_area", f"loop={c.loop_name} area={area:.4f} need<={c.max_area_mm2}"
                )
            ]
        return []


def build_courtyard_constraints(
    comp_refs: list[str], explicit_constraints: list[BaseConstraint], tau_mm: float
) -> list[BaseConstraint]:
    """Independent replica of ``_encoder_core._generate_courtyard_separated_constraints``.

    Deliberately duplicated rather than imported: the verifier's whole job
    is to check the encoder's output without trusting the encoder's own
    machinery, so it recomputes the same all-pairs-tau rule from the same
    (public, deterministic) inputs -- the repo's own stated discipline for
    "this check's correctness must not depend on a sibling's internal
    representation" (see docs/evidence/2026-08-04-wave4-residual-verdicts.md
    Sec 4.2, citing check_isolation_keepout.py's identical rationale).
    """
    existing_pairs: dict[tuple[str, str], float] = {}
    for c in explicit_constraints:
        if isinstance(c, SeparatedConstraint) and c.min_distance_mm >= tau_mm:
            if c.a in comp_refs and c.b in comp_refs and c.a != c.b:
                key = tuple(sorted([c.a, c.b]))
                existing_pairs[key] = max(existing_pairs.get(key, 0.0), c.min_distance_mm)
    extra: list[BaseConstraint] = []
    refs = sorted(comp_refs)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            ra, rb = refs[i], refs[j]
            key = (ra, rb)
            if key in existing_pairs:
                continue
            extra.append(
                SeparatedConstraint(
                    a=ra,
                    b=rb,
                    min_distance_mm=tau_mm,
                    tier=ConstraintTier.HARD,
                    because="courtyard clearance (independent-verifier replica of C1)",
                )
            )
    return list(explicit_constraints) + extra


def default_clearance_mm() -> float:
    """Same fallback/lookup solve_placement itself uses for tau's input."""
    try:
        from temper_placer.io.netclass_loader import load_netclass_rules

        cfg = PLACER_ROOT / "configs" / "netclass_rules.yaml"
        if cfg.exists():
            return load_netclass_rules(cfg).design_rules.default_clearance
    except Exception:
        pass
    return 0.2


# ===========================================================================
# 2. Pluggable engine + differential harness
# ===========================================================================


@dataclass
class SolveOutcome:
    engine: str
    config: dict[str, Any]
    status: str
    positions: dict[str, tuple[float, float]]
    rotations: dict[str, int]
    objective_value: float
    solve_time_ms: float


class Engine(Protocol):
    name: str

    def solve(self, spec: "CorpusModel", *, seed: int, timeout_ms: int, num_workers: int) -> SolveOutcome: ...


@contextlib.contextmanager
def _forced_worker_count(n: int):
    """Force CP-SAT's num_search_workers for the duration of one Solve()
    call. solve_placement() hardcodes num_search_workers=4
    (_encoder_solve.py) and exposes no parameter for it -- this is the
    harness's ONLY hook to vary thread count for the self-differential
    (task requirement: "different random seeds/thread counts"), and it is
    scoped to a single call via monkeypatch + restore. It does not change
    solve_placement's own code or its shipped default.
    """
    from ortools.sat.python import cp_model as cp

    original = cp.CpSolver.Solve

    def patched(self, model, *args, **kwargs):
        self.parameters.num_search_workers = n
        return original(self, model, *args, **kwargs)

    cp.CpSolver.Solve = patched
    try:
        yield
    finally:
        cp.CpSolver.Solve = original


class OrToolsEngine:
    name = "ortools-cpsat"

    def solve(self, spec: "CorpusModel", *, seed: int, timeout_ms: int, num_workers: int) -> SolveOutcome:
        t0 = time.monotonic()
        with _forced_worker_count(num_workers):
            result = solve_placement(
                netlist=spec.netlist,
                board=spec.board,
                extra_constraints=spec.extra_constraints,
                timeout_ms=timeout_ms,
                seed=seed,
                zones=spec.zones,
                loop_components=spec.loop_components,
                zone_components=spec.zone_components,
                minimize_displacement_to=spec.minimize_displacement_to,
            )
        elapsed = (time.monotonic() - t0) * 1000.0
        return SolveOutcome(
            engine=self.name,
            config={"seed": seed, "num_workers": num_workers, "timeout_ms": timeout_ms},
            status=result.status,
            positions=dict(result.positions),
            rotations=dict(result.rotations),
            objective_value=result.objective_value,
            solve_time_ms=elapsed,
        )


# ===========================================================================
# 3. Corpus: real encoder models (small synthetic / medium synthetic /
#    corpus-fixture-33c -- a small, frozen, 33-component fixture, NOT the
#    real 169-component pcb/temper.kicad_pcb board -- see
#    build_full_board_corpus()'s docstring), built through the exact same
#    production entry points (Component/Netlist/PCL constraint
#    dataclasses/solve_placement) that the placer itself uses -- not a
#    hand-rolled toy format.
# ===========================================================================


@dataclass
class CorpusModel:
    name: str
    netlist: Netlist
    board: Any
    extra_constraints: list[BaseConstraint]
    zones: dict[str, tuple[float, float, float, float]]
    zone_components: dict[str, list[str]]
    loop_components: dict[str, list[str]]
    minimize_displacement_to: dict[str, tuple[float, float]] | None
    verification_model: PlacementModel


def _comp(ref: str, w: float, h: float) -> Component:
    return Component(ref=ref, footprint=f"FP_{ref}", bounds=(w, h), pins=[])


def build_small_corpus() -> CorpusModel:
    """5 components, board 30x20mm. Exercises SEPARATED (courtyard, all
    pairs), ADJACENT, ANCHORED, ON_SIDE."""
    refs_sizes = {
        "U1": (4.0, 4.0),
        "R1": (1.6, 0.8),
        "R2": (1.6, 0.8),
        "C1": (2.0, 1.2),
        "J1": (3.0, 2.0),
    }
    components = [_comp(r, w, h) for r, (w, h) in refs_sizes.items()]
    netlist = Netlist(components=components, nets=[])
    board = SimpleNamespace(width=30.0, height=20.0, zones=[], constraints=[])

    constraints: list[BaseConstraint] = [
        AdjacentConstraint(
            "R1", "R2", max_distance_mm=6.0, tier=ConstraintTier.HARD,
            because="R1/R2 must stay close for series-pair layout",
        ),
        AnchoredConstraint(
            "J1", region=(0.0, 0.0, 6.0, 20.0), tier=ConstraintTier.HARD,
            because="J1 connector must sit on the left edge strip",
        ),
        OnSideConstraint(
            ["U1"], side=BoardSide.RIGHT, edge=EdgeType.NEAR, tier=ConstraintTier.HARD,
            max_distance_mm=10.0, because="U1 must stay near the right edge for routing",
        ),
    ]
    tau = courtyard_clearance_mm(default_clearance_mm())
    full_constraints = build_courtyard_constraints(list(refs_sizes), constraints, tau)
    vmodel = PlacementModel(
        board_w_mm=30.0, board_h_mm=20.0, sizes_mm=refs_sizes, constraints=full_constraints,
    )
    return CorpusModel(
        name="small",
        netlist=netlist,
        board=board,
        extra_constraints=constraints,
        zones={},
        zone_components={},
        loop_components={},
        minimize_displacement_to=None,
        verification_model=vmodel,
    )


def build_medium_corpus() -> CorpusModel:
    """12 components, board 60x60mm, two zones. Exercises SEPARATED,
    ALIGNED, ENCLOSING, KEEPOUT, LOOP_AREA, plus a real Manhattan
    minimize_displacement_to objective (so objective parity is measuring
    something, not comparing 0.0 == 0.0)."""
    refs_sizes: dict[str, tuple[float, float]] = {}
    for i in range(1, 5):
        refs_sizes[f"C{i}"] = (2.0, 1.2)
    for i in range(1, 4):
        refs_sizes[f"R{i}"] = (1.6, 0.8)
    refs_sizes["U1"] = (7.0, 7.0)
    refs_sizes["U2"] = (5.0, 5.0)
    refs_sizes["L1"] = (4.0, 4.0)
    refs_sizes["Q1"] = (3.0, 3.0)
    refs_sizes["Q2"] = (3.0, 3.0)

    components = [_comp(r, w, h) for r, (w, h) in refs_sizes.items()]
    netlist = Netlist(components=components, nets=[])
    board = SimpleNamespace(width=60.0, height=60.0, zones=[], constraints=[])

    zones = {"DIGITAL": (0.0, 0.0, 30.0, 60.0), "POWER_KEEPOUT": (45.0, 0.0, 60.0, 15.0)}
    zone_components = {"DIGITAL": ["U1", "U2", "C1", "C2", "C3", "C4"]}
    loop_components = {"commutation_loop": ["Q1", "Q2", "L1"]}

    constraints: list[BaseConstraint] = [
        EnclosingConstraint(
            outer="DIGITAL", inner=["U1", "U2", "C1", "C2", "C3", "C4"], tier=ConstraintTier.HARD,
            margin_mm=1.0, because="digital cluster must stay inside the DIGITAL zone",
        ),
        KeepoutConstraint(
            zone_name="POWER_KEEPOUT", tier=ConstraintTier.HARD, margin_mm=0.5,
            because="mounting hole keepout, no components may overlap it",
        ),
        AlignedConstraint(
            ["C1", "C2", "C3"], axis=Axis.Y, tier=ConstraintTier.HARD, tolerance_mm=1.0,
            because="decoupling caps aligned in a row for pick-and-place",
        ),
        LoopAreaConstraint(
            loop_name="commutation_loop", max_area_mm2=250.0, tier=ConstraintTier.HARD,
            because="commutation loop area ceiling to bound EMI",
        ),
        SeparatedConstraint(
            "Q1", "Q2", min_distance_mm=3.0, tier=ConstraintTier.HARD,
            because="switch pair thermal/isolation separation",
        ),
    ]
    tau = courtyard_clearance_mm(default_clearance_mm())
    full_constraints = build_courtyard_constraints(list(refs_sizes), constraints, tau)
    vmodel = PlacementModel(
        board_w_mm=60.0, board_h_mm=60.0, sizes_mm=refs_sizes, constraints=full_constraints,
        zones=zones, zone_components=zone_components, loop_components=loop_components,
    )
    # A real repair-style objective: prefer positions close to a synthetic
    # "current board" so the solver has an actual optimum to be compared
    # across seeds/thread-counts, not a vacuous 0.0.
    reference = {
        "C1": (5.0, 10.0), "C2": (5.0, 20.0), "C3": (5.0, 30.0), "C4": (5.0, 40.0),
        "R1": (35.0, 10.0), "R2": (35.0, 20.0), "R3": (35.0, 30.0),
        "U1": (15.0, 45.0), "U2": (15.0, 15.0),
        "L1": (50.0, 45.0), "Q1": (50.0, 35.0), "Q2": (50.0, 25.0),
    }
    return CorpusModel(
        name="medium",
        netlist=netlist,
        board=board,
        extra_constraints=constraints,
        zones=zones,
        zone_components=zone_components,
        loop_components=loop_components,
        minimize_displacement_to=reference,
        verification_model=vmodel,
    )


def build_full_board_corpus() -> CorpusModel | None:
    """**NOT the real board.** This is
    power_pcb_dataset/corpus/temper/temper.kicad_pcb -- a small, frozen,
    33-component *independent test fixture* (100x150mm, last touched
    2026-07-08), placed under the ACTUAL production PCL config
    (configs/constraints/temper_induction_cooker.yaml) -- the same
    fixture + config test_golden_board_drc_regression uses. The real ship
    target is pcb/temper.kicad_pcb (169 components, 152x234mm); this
    function intentionally does NOT read it -- see
    docs/evidence/2026-08-11-golden-fixture-regeneration-decision.md for
    why (CP-SAT does not decide feasibility on the real board within this
    harness's 30s full-board timeout; see that doc's measurement).
    Earlier revisions of this docstring called this "the real golden-board
    corpus", which is what led three CP-SAT spikes
    (docs/evidence/2026-08-07-cpsat-equivalence-harness.md,
    docs/evidence/2026-08-07-cpsat-objective-frequency.md, and one more) to
    report conclusions about "the real board" that were actually about this
    33-component fixture -- see
    docs/evidence/2026-08-11-pumpkin-real-budget-spike.md Sec 5. Returns
    None if the fixture files are missing (kept optional, not a hard
    failure of the harness). Every caller of this function must report the
    returned model's own component count (``len(model.verification_model
    .sizes_mm)``) alongside any result derived from it -- never assume or
    imply it is the real board's count."""
    board_path = REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"
    pcl_config = PLACER_ROOT / "configs" / "constraints" / "temper_induction_cooker.yaml"
    if not board_path.exists() or not pcl_config.exists():
        return None

    from temper_placer.io.config_loader import load_constraints
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parse_result = parse_kicad_pcb(board_path)
    netlist = parse_result.netlist
    board = parse_result.board
    if board is None or not netlist.components:
        return None

    loaded = load_constraints(pcl_config)
    extra_constraints = list(getattr(loaded, "pcl_constraints", []))
    zones = {z.name: z.bounds for z in getattr(loaded, "zones", [])}

    # Same downgrade test_regression_drc.py applies: the config names
    # critical loops (commutation_loop, gate_drive_high, gate_drive_low)
    # that solve_placement's auto-loop-extraction never reproduces by name.
    _encoder_core._UNRESOLVED_REF_POLICY = "warn"

    refs_sizes = {c.ref: (float(c.bounds[0]), float(c.bounds[1])) for c in netlist.components}
    zone_dict = {name: tuple(bounds) for name, bounds in zones.items()}
    zone_components: dict[str, list[str]] = {}
    for z in board.zones:
        zone_components.setdefault(z.name, list(z.components))

    tau = courtyard_clearance_mm(default_clearance_mm())
    full_constraints = build_courtyard_constraints(list(refs_sizes), extra_constraints, tau)
    vmodel = PlacementModel(
        board_w_mm=float(board.width), board_h_mm=float(board.height), sizes_mm=refs_sizes,
        constraints=full_constraints, zones=zone_dict, zone_components=zone_components,
        loop_components={},
    )
    return CorpusModel(
        # Named for what it IS (a frozen 33-component corpus fixture), not
        # what it is sometimes mistaken for (the real board) -- see this
        # function's own docstring.
        name="corpus-fixture-33c",
        netlist=netlist,
        board=board,
        extra_constraints=extra_constraints,
        zones=zones,
        zone_components={},
        loop_components={},
        minimize_displacement_to=None,
        verification_model=vmodel,
    )


# ===========================================================================
# 4. Differential runner
# ===========================================================================


SAT_STATUSES = {"optimal", "feasible"}
UNSAT_STATUSES = {"infeasible"}


@dataclass
class ModelReport:
    name: str
    n_components: int
    n_constraints: int
    runs: list[dict[str, Any]]
    feasibility_parity: bool
    status_set: list[str]
    objective_parity: bool | None
    objective_spread: float | None
    membership_rate: float
    membership_fail_examples: list[str]
    determinism_rate: float | None
    determinism_groups: int


def run_differential(
    model: CorpusModel,
    engines: list[Engine],
    seeds: list[int],
    worker_counts: list[int],
    repeats: int,
    timeout_ms: int,
) -> ModelReport:
    verifier = IndependentVerifier()
    runs: list[dict[str, Any]] = []
    outcomes: list[SolveOutcome] = []

    for engine, seed, workers in itertools.product(engines, seeds, worker_counts):
        for rep in range(repeats):
            outcome = engine.solve(model, seed=seed, timeout_ms=timeout_ms, num_workers=workers)
            outcomes.append(outcome)
            entry: dict[str, Any] = {
                "engine": outcome.engine,
                "seed": seed,
                "num_workers": workers,
                "repeat": rep,
                "status": outcome.status,
                "objective_value": outcome.objective_value,
                "solve_time_ms": round(outcome.solve_time_ms, 1),
            }
            if outcome.status in SAT_STATUSES:
                vres = verifier.verify(model.verification_model, outcome.positions, outcome.rotations)
                entry["verified"] = vres.ok
                entry["verification_summary"] = vres.summary()
            runs.append(entry)

    status_set = sorted({o.status for o in outcomes})
    sat_class = lambda s: "SAT" if s in SAT_STATUSES else ("UNSAT" if s in UNSAT_STATUSES else "OTHER")
    classes = {sat_class(o.status) for o in outcomes}
    feasibility_parity = len(classes) <= 1

    sat_outcomes = [o for o in outcomes if o.status in SAT_STATUSES]
    objective_parity: bool | None = None
    objective_spread: float | None = None
    if len(sat_outcomes) >= 2:
        objs = [o.objective_value for o in sat_outcomes]
        objective_spread = max(objs) - min(objs)
        objective_parity = objective_spread <= 1e-6 * max(1.0, abs(statistics.fmean(objs)))

    membership_checks = [e for e in runs if "verified" in e]
    membership_rate = (
        sum(1 for e in membership_checks if e["verified"]) / len(membership_checks)
        if membership_checks
        else float("nan")
    )
    membership_fail_examples = [
        e["verification_summary"] for e in membership_checks if not e["verified"]
    ][:3]

    # Determinism: group by (engine, seed, workers); a group is
    # bit-identical if every repeat has identical status, objective,
    # positions, rotations.
    groups: dict[tuple[str, int, int], list[SolveOutcome]] = {}
    for o in outcomes:
        key = (o.engine, o.config["seed"], o.config["num_workers"])
        groups.setdefault(key, []).append(o)
    multi_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    determinism_rate: float | None = None
    if multi_groups:
        identical = 0
        for members in multi_groups.values():
            ref = members[0]
            same = all(
                m.status == ref.status
                and abs(m.objective_value - ref.objective_value) < 1e-9
                and m.positions == ref.positions
                and m.rotations == ref.rotations
                for m in members[1:]
            )
            identical += int(same)
        determinism_rate = identical / len(multi_groups)

    return ModelReport(
        name=model.name,
        n_components=len(model.verification_model.sizes_mm),
        n_constraints=len(model.verification_model.constraints),
        runs=runs,
        feasibility_parity=feasibility_parity,
        status_set=status_set,
        objective_parity=objective_parity,
        objective_spread=objective_spread,
        membership_rate=membership_rate,
        membership_fail_examples=membership_fail_examples,
        determinism_rate=determinism_rate,
        determinism_groups=len(multi_groups),
    )


def main() -> None:
    corpora = [build_small_corpus(), build_medium_corpus()]
    full = build_full_board_corpus()
    if full is not None:
        corpora.append(full)
    else:
        print(
            "[warn] corpus-fixture-33c (power_pcb_dataset/corpus/temper/temper.kicad_pcb, "
            "NOT the real board) unavailable (missing fixture files); skipping",
            file=sys.stderr,
        )

    engines: list[Engine] = [OrToolsEngine()]
    seeds = [0, 1, 7]
    worker_counts = [1, 4, 8]
    reports = []
    for model in corpora:
        timeout_ms = 30_000 if model.name == "corpus-fixture-33c" else 5_000
        repeats = 2
        # Every result line carries its own component count -- do not rely
        # on the model name alone to convey scale (see
        # build_full_board_corpus()'s docstring: "corpus-fixture-33c" is a
        # 33-component fixture, never the real 169-component board).
        print(f"=== {model.name}: {len(model.verification_model.sizes_mm)} components, "
              f"{len(model.verification_model.constraints)} constraints ===")
        report = run_differential(
            model, engines, seeds, worker_counts, repeats=repeats, timeout_ms=timeout_ms
        )
        reports.append(report)
        print(
            f"  feasibility_parity={report.feasibility_parity} status_set={report.status_set} "
            f"objective_parity={report.objective_parity} spread={report.objective_spread} "
            f"membership_rate={report.membership_rate:.3f} "
            f"determinism_rate={report.determinism_rate} ({report.determinism_groups} groups)"
        )
        if report.membership_fail_examples:
            for ex in report.membership_fail_examples:
                print(f"    MEMBERSHIP FAIL: {ex}")

    out_path = Path(__file__).parent / "2026-08-07-cpsat-equivalence-summary.json"
    payload = {
        "provenance": {"commit": "7e1194b776aad76db2f1fd2a323defa0bebd5367", "dirty": False},
        "generated_by": Path(__file__).name,
        "engines": [e.name for e in engines],
        "seeds": seeds,
        "worker_counts": worker_counts,
        "models": [
            {
                "name": r.name,
                "n_components": r.n_components,
                "n_constraints": r.n_constraints,
                "feasibility_parity": r.feasibility_parity,
                "status_set": r.status_set,
                "objective_parity": r.objective_parity,
                "objective_spread": r.objective_spread,
                "membership_rate": r.membership_rate,
                "membership_fail_examples": r.membership_fail_examples,
                "determinism_rate": r.determinism_rate,
                "determinism_groups": r.determinism_groups,
                "runs": r.runs,
            }
            for r in reports
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
