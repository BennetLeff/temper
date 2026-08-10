"""R1c/R1d: property-based and metamorphic tests for the PCL contract objects.

Wave 4, Phase 2/6 -- the Rust pyclasses in ``temper-constraint-compiler``
(``src/pcl_contracts.rs``) implement the eight PCL constraint classes and
``CompilationContext``. This suite checks the *contract* properties those
objects must satisfy, fuzzed over random constructor inputs.

The properties are intentionally live-only (the bit-identical differential
against the pinned oracle lives in ``test_constraints_rust_differential.py``,
including id, repr, to_dict and involves_component parity). What is checked
here is that the shipped surface is internally coherent:

R1c: >= 5 properties. R1d: >= 3 metamorphic relations.
Every property is non-vacuously guarded: a constant-returning
implementation fails at least one assertion in each.
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl import constraints as live

CONSTRAINT_CLASSES = [
    "AdjacentConstraint",
    "SeparatedConstraint",
    "EnclosingConstraint",
    "KeepoutConstraint",
    "AlignedConstraint",
    "OnSideConstraint",
    "AnchoredConstraint",
    "LoopAreaConstraint",
]

TIER_NAMES = ["HARD", "STRONG", "SOFT"]
TIER_RANK = {"HARD": 1, "STRONG": 2, "SOFT": 3}

REFDES = st.sampled_from(["Q1", "Q2", "R1", "C1", "U1", "J1", "D1", "HV_ZONE", "MCU_ZONE"])
WHY = st.text(min_size=10, max_size=40).filter(lambda s: " " not in s)
DIST = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)


def _tier(name: str) -> live.ConstraintTier:
    return getattr(live.ConstraintTier, name)


@st.composite
def constraint_specs(draw):
    """Random (cls_name, kwargs) with enum values given as member *names*."""
    cls_name = draw(st.sampled_from(CONSTRAINT_CLASSES))
    tier = draw(st.sampled_from(TIER_NAMES))
    because = draw(WHY)
    if cls_name == "AdjacentConstraint":
        a, b = draw(REFDES), draw(REFDES)
        return (cls_name, {
            "a": a, "b": b, "max_distance_mm": draw(DIST), "tier": tier, "because": because,
            "metric": draw(st.sampled_from(["EDGE_TO_EDGE", "CENTER_TO_CENTER", "PIN_TO_PIN"])),
            "pin_a": draw(st.none() | st.text(min_size=1, max_size=4)),
            "pin_b": draw(st.none() | st.text(min_size=1, max_size=4)),
        })
    if cls_name == "SeparatedConstraint":
        a, b = draw(REFDES), draw(REFDES)
        return (cls_name, {
            "a": a, "b": b, "min_distance_mm": draw(DIST), "tier": tier, "because": because,
            "metric": draw(st.sampled_from(["EDGE_TO_EDGE", "CENTER_TO_CENTER", "PIN_TO_PIN"])),
        })
    if cls_name == "EnclosingConstraint":
        inner = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=5))
        return (cls_name, {
            "outer": draw(REFDES), "inner": inner, "tier": tier, "because": because,
            "margin_mm": draw(DIST),
        })
    if cls_name == "KeepoutConstraint":
        return (cls_name, {
            "zone_name": draw(REFDES), "tier": tier, "because": because, "margin_mm": draw(DIST),
        })
    if cls_name == "AlignedConstraint":
        comps = draw(st.lists(st.text(min_size=1, max_size=5), min_size=2, max_size=5))
        return (cls_name, {
            "components": comps, "axis": draw(st.sampled_from(["X", "Y", "MAJOR", "MINOR"])),
            "tier": tier, "because": because, "tolerance_mm": draw(DIST),
        })
    if cls_name == "OnSideConstraint":
        comps = draw(st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=5))
        return (cls_name, {
            "components": comps, "side": draw(st.sampled_from(["TOP", "BOTTOM", "LEFT", "RIGHT"])),
            "edge": draw(st.sampled_from(["FLUSH", "NEAR", "OVERHANG"])),
            "tier": tier, "because": because, "max_distance_mm": draw(DIST),
        })
    if cls_name == "AnchoredConstraint":
        if draw(st.booleans()):
            region = draw(st.tuples(DIST, DIST, DIST, DIST))
            position = None
        else:
            region = None
            position = draw(st.tuples(DIST, DIST))
        return (cls_name, {
            "component": draw(REFDES), "tier": tier, "because": because,
            "region": region, "position": position,
        })
    # LoopAreaConstraint
    return (cls_name, {
        "loop_name": draw(st.text(min_size=1, max_size=12)), "max_area_mm2": draw(DIST),
        "tier": tier, "because": because,
    })


def _build(cls_name: str, kwargs: dict):
    """Construct a live instance from a spec (enum names materialised)."""
    enum_keys = {
        "tier": live.ConstraintTier,
        "metric": live.DistanceMetric,
        "axis": live.Axis,
        "side": live.BoardSide,
        "edge": live.EdgeType,
    }
    kw = {}
    for k, v in kwargs.items():
        if k in enum_keys:
            kw[k] = getattr(enum_keys[k], v)
        else:
            kw[k] = v
    return getattr(live, cls_name)(**kw)


def _component_refs(c):
    """The component refs a constraint *names*, per its type."""
    if isinstance(c, (live.AdjacentConstraint, live.SeparatedConstraint)):
        return [c.a, c.b]
    if isinstance(c, live.EnclosingConstraint):
        return [c.outer] + list(c.inner)
    if isinstance(c, live.KeepoutConstraint):
        return [c.zone_name]
    if isinstance(c, (live.AlignedConstraint, live.OnSideConstraint)):
        return list(c.components)
    if isinstance(c, live.AnchoredConstraint):
        return [c.component]
    return []


# ===========================================================================
# R1c -- property-based tests
# ===========================================================================


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_p1_id_is_deterministic(spec):
    """Identical inputs yield the identical id; the id is non-empty."""
    cls_name, kwargs = spec
    c1 = _build(cls_name, kwargs)
    c2 = _build(cls_name, kwargs)
    assert c1.id == c2.id
    assert isinstance(c1.id, str) and len(c1.id) > 0


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_p2_explicit_id_is_preserved(spec):
    """A caller-supplied id wins over auto-generation."""
    cls_name, kwargs = spec
    c = _build(cls_name, {**kwargs, "id": "explicit_id_42"})
    assert c.id == "explicit_id_42"


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_p3_to_dict_serializes_enum_fields_to_values(spec):
    """to_dict carries .value strings/ints for the enum-typed fields."""
    cls_name, kwargs = spec
    c = _build(cls_name, kwargs)
    d = c.to_dict()
    assert d["type"] == c.constraint_type.value
    assert d["tier"] == c.tier.value
    if "metric" in kwargs:
        assert d["metric"] == c.metric.value
    if "axis" in kwargs:
        assert d["axis"] == c.axis.value
    if "side" in kwargs:
        assert d["side"] == c.side.value
    if "edge" in kwargs:
        assert d["edge"] == c.edge.value
    # every serialized string field round-trips through the object's getter
    for key, val in d.items():
        if key in ("type", "metric", "axis", "side", "edge", "tier"):
            continue
        assert getattr(c, key) == val, f"{cls_name}.to_dict()['{key}'] drifted"


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_p4_involves_component_recognizes_named_refs_only(spec):
    """involves_component is True for every named ref and False otherwise."""
    cls_name, kwargs = spec
    c = _build(cls_name, kwargs)
    for ref in _component_refs(c):
        assert c.involves_component(ref), f"{cls_name} missed named ref {ref!r}"
    # A ref that no field could name is always False (LoopArea always False).
    assert c.involves_component("__definitely_not_a_component__") is False


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_p5_escalate_converges_to_hard_in_two_steps(spec):
    """escalate is monotone and reaches HARD within 2 calls; HARD is a fixed point."""
    cls_name, kwargs = spec
    c = _build(cls_name, kwargs)
    start = TIER_RANK[c.tier.name]
    c.escalate()
    step1 = TIER_RANK[c.tier.name]
    assert step1 <= start, "escalate must never loosen"
    c.escalate()
    assert c.tier is live.ConstraintTier.HARD
    c.escalate()
    assert c.tier is live.ConstraintTier.HARD


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_p6_deepcopy_preserves_the_full_contract(spec):
    """deepcopy (used by ConstraintCollection.copy) is an exact clone."""
    cls_name, kwargs = spec
    c = _build(cls_name, kwargs)
    clone = copy.deepcopy(c)
    assert clone == c
    assert repr(clone) == repr(c)
    assert clone.to_dict() == c.to_dict()
    assert clone.id == c.id
    assert clone is not c


# ===========================================================================
# R1d -- metamorphic relations
# ===========================================================================


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_mr1_id_is_invariant_under_escalation(spec):
    """Escalation changes the tier but never the constraint's identity (id)."""
    cls_name, kwargs = spec
    c = _build(cls_name, kwargs)
    id_before = c.id
    c.escalate()
    assert c.id == id_before


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_mr2_to_dict_is_invariant_under_deepcopy(spec):
    """Serializing a deepcopy equals serializing the original."""
    cls_name, kwargs = spec
    c = _build(cls_name, kwargs)
    assert copy.deepcopy(c).to_dict() == c.to_dict()


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_mr3_escalate_commutes_with_deepcopy(spec):
    """deepcopy(c).escalate() and deepcopy(c.escalate()) produce equal objects."""
    cls_name, kwargs = spec
    c1 = _build(cls_name, kwargs)
    c1.escalate()
    c2 = _build(cls_name, kwargs)
    c2_clone = copy.deepcopy(c2)
    c2_clone.escalate()
    assert c2_clone == c1
    # and the original c2 is untouched by escalating its clone
    assert c2.tier.name == kwargs["tier"]


@given(spec=constraint_specs())
@settings(max_examples=200, deadline=None)
def test_mr4_involvement_is_invariant_under_escalation(spec):
    """Escalation only changes the tier; involvement answers stay identical."""
    cls_name, kwargs = spec
    c = _build(cls_name, kwargs)
    before = {ref: c.involves_component(ref) for ref in _component_refs(c)}
    c.escalate()
    for ref, expected in before.items():
        assert c.involves_component(ref) == expected
    assert c.involves_component("__definitely_not_a_component__") is False
