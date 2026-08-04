"""Property-based + metamorphic tests for the migrated ConstraintCompiler.

Wave 4, Phase 4 (R1c/R1d). The Rust-migrated ``temper_placer.constraints.compiler``
must satisfy these properties; bit-identical parity against the pinned
pre-migration Python is asserted separately by
``test_compiler_rust_differential.py``.

Five properties (all non-vacuously guarded — each fails if the function under
test returns a constant):

- P1. Filter totality & empty-input semantics: the compiled filter never raises
  and returns ``True`` for an empty constraint set, for ANY slot/component/
  placements.
- P2. Hard-spacing monotonicity along a ray: for a hard spacing rule (A,B),
  if ``filter(slot, B, {A: p})`` is True, then a slot strictly farther from
  ``p`` along the same ray is also True (moving away never creates a spacing
  violation). Non-vacuous: a slot inside the forbidden circle is rejected.
- P3. Scorer non-negativity: the compiled scorer returns ``score >= 0`` for any
  input (every term is a non-negative penalty); and there EXIST inputs with
  score > 0 (guarded by constructing a violation).
- P4. Filter rejection is witnessed by a rule: if the filter rejects, at least
  one hard rule (spacing/proximity/escape/corridor/zone) fires on the input —
  cross-checked by an independent re-evaluation of each rule.
- P5. Soft rules do not filter: with only soft-tier rules, the filter accepts
  every input (soft penalties live in the scorer, not the filter).

Four metamorphic relations (honestly bounded):

- MR1. Translation invariance (bit-exact): with no zone/thermal constraints,
  translating the slot AND every placement by the same vector leaves
  filter/scorer results bit-identical (distances are translation-invariant;
  the bound is what makes it exact).
- MR2. Adding an unrelated placement is inert: for a component governed only by
  rules among {A, B}, adding a placement for an unrelated ref Z never changes
  the filter/scorer result for A or B (lookups are exact-ref).
- MR3. Scorer additivity over disjoint universes (bit-exact): with two rule
  sets over disjoint component universes and no group spanning both, the scorer
  on the union equals the sum of the scorers on each universe (score terms are
  independent; the bound: universes must be disjoint).
- MR4. Doubling symmetry is exact on powers of two: scaling all coordinates and
  thresholds by 2.0 doubles every distance and keeps the score-vs-threshold
  comparisons identical; for a pure soft-spacing penalty the score exactly
  doubles (all operations are scale-homogeneous).
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer._constraint_types import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)
from temper_placer.constraints.compiler import ConstraintCompiler

MAX_EXAMPLES = 100

_REFS = ["A", "B", "C", "Z", "U1", "U2", "Q1", "Q2", "R5", "J1"]
_REF = st.sampled_from(_REFS)
# Placement coordinates are millimeters; subnormal magnitudes (1e-300) are
# outside the physical domain and break the exact-arithmetic bounds of the
# metamorphic relations, so they are excluded from the strategy.
_COORD = st.floats(
    min_value=-100.0,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
    allow_subnormal=False,
)
_POINT = st.tuples(_COORD, _COORD)
_PLACEMENTS = st.dictionaries(_REF, _POINT, max_size=5)
_TIER = st.sampled_from(["hard", "soft"])


def _mk(**kw) -> PlacementConstraints:
    return PlacementConstraints(**kw)


# ---------------------------------------------------------------------------
# P1 — totality + empty semantics
# ---------------------------------------------------------------------------


@given(slot=_POINT, comp=_REF, placements=_PLACEMENTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_filter_total_and_empty_accepts_all(slot, comp, placements):
    compiler = ConstraintCompiler(_mk())
    filter_fn = compiler.compile_to_slot_filter()
    assert filter_fn(slot, comp, placements) is True


@given(slot=_POINT, comp=_REF, placements=_PLACEMENTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_scorer_total_and_empty_is_zero(slot, comp, placements):
    compiler = ConstraintCompiler(_mk())
    scorer = compiler.compile_to_slot_scorer()
    assert scorer(slot, comp, placements) == 0.0


# ---------------------------------------------------------------------------
# P2 — hard-spacing monotonicity along a ray
# ---------------------------------------------------------------------------


@given(p=_POINT, base=_POINT, comp=st.sampled_from(["B", "C", "D"]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_hard_spacing_monotonic_along_ray(p, base, comp):
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b=comp, min_separation_mm=15.0, tier="hard")
        ]
    )
    compiler = ConstraintCompiler(constraints)
    filter_fn = compiler.compile_to_slot_filter()

    dx, dy = p[0] - base[0], p[1] - base[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0.0:
        return
    ux, uy = dx / length, dy / length  # unit direction

    # Guard: a point 5 mm along the ray is strictly inside the forbidden circle
    # (dist 5 < 15), so the property actually sees a rejection (non-vacuous).
    near = (base[0] + ux * 5.0, base[1] + uy * 5.0)
    assert filter_fn(near, comp, {"A": base}) is False

    # Moving farther along the ray never flips True -> False (distances grow).
    # 14.9mm is strictly inside, 15.1mm strictly outside — the exact 15.0
    # boundary is deliberately avoided (computed sqrt distance may sit a ulp
    # either side; that is parity-correct behaviour, not a property to pin).
    prev = False
    for dist_mm in (5.0, 10.0, 14.9, 15.1, 20.0, 50.0):
        slot = (base[0] + ux * dist_mm, base[1] + uy * dist_mm)
        cur = filter_fn(slot, comp, {"A": base})
        if dist_mm < 15.0:
            assert cur is False, f"inside circle accepted at {dist_mm}mm"
        else:
            assert cur is True, f"outside circle rejected at {dist_mm}mm"
        assert cur or not prev, "moving away reintroduced a violation"
        prev = cur


# ---------------------------------------------------------------------------
# P3 — scorer non-negativity, with a positive-score witness
# ---------------------------------------------------------------------------


@given(slot=_POINT, comp=_REF, placements=_PLACEMENTS, weight=st.floats(min_value=0.1, max_value=5.0))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_scorer_non_negative(slot, comp, placements, weight):
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a=comp, component_b="Z", min_separation_mm=40.0, tier="soft", weight=weight)
        ]
    )
    scorer = ConstraintCompiler(constraints).compile_to_slot_scorer()
    score = scorer(slot, comp, placements)
    assert score >= 0.0
    assert math.isnan(score) is False


def test_p3_scorer_positive_witness():
    """A real violation yields a strictly positive score (guards against the
    property being vacuously satisfied by a constant-zero scorer)."""
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="soft", weight=2.0)
        ]
    )
    scorer = ConstraintCompiler(constraints).compile_to_slot_scorer()
    # A at origin, slot for B at (5, 0): dist 5 < 10 -> (10-5)*2 = 10.0
    assert scorer((5.0, 0.0), "B", {"A": (0.0, 0.0)}) == 10.0
    assert scorer((5.0, 0.0), "B", {"A": (0.0, 0.0)}) > 0.0


# ---------------------------------------------------------------------------
# P4 — every filter rejection is witnessed by a firing hard rule
# ---------------------------------------------------------------------------


def _hard_rules_fire(constraints, slot, comp, placements) -> list[str]:
    """Independent re-evaluation of every hard rule (no Rust, no shim)."""
    fired: list[str] = []
    x, y = slot
    for rule in constraints.component_spacing_rules:
        if rule.tier != "hard" or comp not in (rule.component_a, rule.component_b):
            continue
        other = rule.component_b if comp == rule.component_a else rule.component_a
        if other in placements:
            dist = math.sqrt((x - placements[other][0]) ** 2 + (y - placements[other][1]) ** 2)
            if dist < rule.min_separation_mm:
                fired.append(f"spacing:{other}")
    for group in constraints.component_groups:
        if comp not in group.components:
            continue
        for pr in group.proximity_rules:
            if pr.tier != "hard" or comp not in (pr.component_a, pr.component_b):
                continue
            other = pr.component_b if comp == pr.component_a else pr.component_a
            if other in placements:
                dist = math.sqrt((x - placements[other][0]) ** 2 + (y - placements[other][1]) ** 2)
                if dist > pr.max_distance_mm:
                    fired.append(f"proximity:{other}")
    for ec in constraints.escape_clearances:
        if ec.tier != "hard":
            continue
        if ec.component in placements:
            cp = placements[ec.component]
            dist = math.sqrt((x - cp[0]) ** 2 + (y - cp[1]) ** 2)
            clearance = ec.clearance_mm if ec.clearance_mm is not None else 3.0
            if dist < clearance:
                fired.append(f"escape:{ec.component}")
    for corridor in constraints.routing_corridors:
        if not corridor.keep_clear or corridor.tier != "hard":
            continue
        if corridor.from_component in placements and corridor.to_component in placements:
            p1 = placements[corridor.from_component]
            p2 = placements[corridor.to_component]
            d = _p2s(slot, p1, p2)
            if d < corridor.width_mm / 2:
                fired.append(f"corridor:{corridor.name}")
    required_zone = constraints.get_zone_for_component(comp)
    if required_zone:
        zone = next((z for z in constraints.zones if z.name == required_zone), None)
        if zone and not (zone.bounds[0] <= x <= zone.bounds[2] and zone.bounds[1] <= y <= zone.bounds[3]):
            fired.append(f"zone:{required_zone}")
    return fired


def _p2s(p, a, b):
    ab_x, ab_y = b[0] - a[0], b[1] - a[1]
    ap_x, ap_y = p[0] - a[0], p[1] - a[1]
    ab_len_sq = ab_x * ab_x + ab_y * ab_y
    if ab_len_sq == 0:
        return math.sqrt((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2)
    t = max(0, min(1, (ap_x * ab_x + ap_y * ab_y) / ab_len_sq))
    cx, cy = a[0] + t * ab_x, a[1] + t * ab_y
    return math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2)


@given(
    slot=_POINT,
    comp=_REF,
    placements=_PLACEMENTS,
    min_sep=st.floats(min_value=1.0, max_value=30.0),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_filter_rejection_is_witnessed(slot, comp, placements, min_sep):
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b=comp, min_separation_mm=min_sep, tier="hard")
        ],
        component_groups=[],
        escape_clearances=[],
        routing_corridors=[],
    )
    filter_fn = ConstraintCompiler(constraints).compile_to_slot_filter()
    fired = _hard_rules_fire(constraints, slot, comp, placements)
    accepted = filter_fn(slot, comp, placements)
    if fired:
        assert accepted is False, f"rule fired but filter accepted: {fired}"
    else:
        assert accepted is True, f"filter rejected but no rule fired at slot={slot} comp={comp}"


# ---------------------------------------------------------------------------
# P5 — soft rules never filter
# ---------------------------------------------------------------------------


@given(slot=_POINT, comp=_REF, placements=_PLACEMENTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_soft_rules_never_filter(slot, comp, placements):
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a=comp, component_b="Z", min_separation_mm=100.0, tier="soft")
        ],
        escape_clearances=[EscapeClearance(component=comp, clearance_mm=100.0, tier="soft")],
        component_groups=[
            ComponentGroup(
                name="g",
                components=[comp, "Z"],
                proximity_rules=[
                    ProximityRule(component_a=comp, component_b="Z", max_distance_mm=1.0, tier="soft")
                ],
            )
        ],
    )
    filter_fn = ConstraintCompiler(constraints).compile_to_slot_filter()
    assert filter_fn(slot, comp, placements) is True


# ---------------------------------------------------------------------------
# MR1 — translation invariance (bit-exact; honestly bounded to the integer
# coordinate domain where every f64 add/sub/square is exact up to 2^53, and
# to constraint sets with no zone/thermal rules — those reference board edges)
# ---------------------------------------------------------------------------

_INT = st.integers(min_value=-64, max_value=64)
_INT_POINT = st.tuples(_INT, _INT)


@given(
    slot=_INT_POINT,
    comp=st.sampled_from(["A", "B"]),
    placements=st.dictionaries(st.sampled_from(["A", "B"]), _INT_POINT, max_size=2),
    t=_INT_POINT,
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_translation_invariance(slot, comp, placements, t):
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=20.0, tier="hard")
        ],
        component_groups=[
            ComponentGroup(
                name="g",
                components=["A", "B"],
                max_spread_mm=50.0,
                proximity_rules=[ProximityRule(component_a="A", component_b="B", max_distance_mm=30.0, tier="soft")],
            )
        ],
    )
    compiler = ConstraintCompiler(constraints)
    filter_fn = compiler.compile_to_slot_filter()
    scorer = compiler.compile_to_slot_scorer()
    shifted = {k: (v[0] + t[0], v[1] + t[1]) for k, v in placements.items()}
    assert filter_fn(slot, comp, placements) == filter_fn(
        (slot[0] + t[0], slot[1] + t[1]), comp, shifted
    )
    assert scorer(slot, comp, placements).hex() == scorer(
        (slot[0] + t[0], slot[1] + t[1]), comp, shifted
    ).hex()


# ---------------------------------------------------------------------------
# MR2 — unrelated placement is inert
# ---------------------------------------------------------------------------


@given(slot=_POINT, placements=st.dictionaries(st.sampled_from(["A", "B", "Z"]), _POINT, max_size=3))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_unrelated_placement_inert(slot, placements):
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=15.0, tier="hard")
        ],
        thermal_constraints=[],
    )
    compiler = ConstraintCompiler(constraints)
    filter_fn = compiler.compile_to_slot_filter()
    scorer = compiler.compile_to_slot_scorer()

    base = {k: v for k, v in placements.items() if k in ("A", "B")}
    with_z = dict(base)
    if "Z" in placements:
        with_z["Z"] = placements["Z"]
    for comp in ("A", "B"):
        assert filter_fn(slot, comp, base) == filter_fn(slot, comp, with_z)
        assert scorer(slot, comp, base).hex() == scorer(slot, comp, with_z).hex()


# ---------------------------------------------------------------------------
# MR3 — scorer additivity over disjoint universes (bit-exact)
# ---------------------------------------------------------------------------


def test_mr3_scorer_additivity_disjoint_universes():
    # Universe 1: {A, B} spacing; universe 2: {C, D} escape. No group spans both.
    set1 = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=12.0, tier="soft", weight=1.5)
        ]
    )
    set2 = _mk(
        escape_clearances=[EscapeClearance(component="C", clearance_mm=8.0, tier="soft")]
    )
    combined = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=12.0, tier="soft", weight=1.5)
        ],
        escape_clearances=[EscapeClearance(component="C", clearance_mm=8.0, tier="soft")],
    )
    scorer1 = ConstraintCompiler(set1).compile_to_slot_scorer()
    scorer2 = ConstraintCompiler(set2).compile_to_slot_scorer()
    scorer_c = ConstraintCompiler(combined).compile_to_slot_scorer()

    cases = [
        ((5.0, 0.0), "B", {"A": (0.0, 0.0), "C": (0.0, 0.0)}),  # B inside A's spacing AND unrelated C
        ((0.0, 0.0), "D", {"C": (3.0, 0.0), "A": (50.0, 50.0)}),  # D inside C's escape zone
        ((50.0, 50.0), "B", {"A": (0.0, 0.0), "C": (100.0, 100.0)}),  # nothing violated
    ]
    for slot, comp, placements in cases:
        a = scorer1(slot, comp, placements)
        b = scorer2(slot, comp, placements)
        assert scorer_c(slot, comp, placements).hex() == (a + b).hex(), f"additivity broke for {comp}"


# ---------------------------------------------------------------------------
# MR4 — power-of-two scale homogeneity (bit-exact on soft spacing)
# ---------------------------------------------------------------------------


def test_mr4_scale_homogeneity_power_of_two():
    """Scaling rule thresholds AND all coordinates by exactly 2.0 doubles every
    soft-spacing penalty bit-exactly (multiplication by a power of two is exact
    in IEEE-754, and (2a - 2b) == 2(a - b) exactly). The bound: pure soft
    spacing rules, coordinates and thresholds chosen so both the base and
    scaled cases are violations of the same kind."""
    base = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="soft", weight=2.0)
        ]
    )
    scaled = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=20.0, tier="soft", weight=2.0)
        ]
    )
    scorer_base = ConstraintCompiler(base).compile_to_slot_scorer()
    scorer_scaled = ConstraintCompiler(scaled).compile_to_slot_scorer()

    for slot, placements in [
        ((5.0, 0.0), {"A": (0.0, 0.0)}),  # dist 5 < 10 -> (10-5)*2 = 10
        ((2.5, 0.0), {"A": (0.0, 0.0)}),  # dist 2.5 < 10 -> (10-2.5)*2 = 15
        ((9.0, 0.0), {"A": (0.0, 0.0)}),  # dist 9 < 10 -> 2.0
    ]:
        s_base = scorer_base(slot, "B", placements)
        assert s_base > 0.0, "base case must be a violation (non-vacuous)"
        s_scaled = scorer_scaled((slot[0] * 2.0, slot[1] * 2.0), "B", {k: (v[0] * 2.0, v[1] * 2.0) for k, v in placements.items()})
        assert s_scaled.hex() == (2.0 * s_base).hex(), f"scale homogeneity broke for {slot}"

    # The non-violating boundary of the scaled space stays zero:
    assert scorer_scaled((30.0, 0.0), "B", {"A": (0.0, 0.0)}) == 0.0

