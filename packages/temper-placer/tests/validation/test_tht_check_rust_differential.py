"""Differential test: THT hole-clearance check in Rust (temper_drc_rs) vs the
pinned Python oracle (Wave 4, Phase 4 — validation DRC-check slice).

``temper_placer/validation/tht_check.py::validate_hole_clearance`` moves its
pairwise hole-distance compute to ``temper_drc_rs.tht_hole_collisions`` (the
Python module keeps the netlist/pad traversal and delegates the pairwise
check + message building to the Rust kernel). The pre-migration module is
pinned verbatim as the oracle (``_tht_check_py_oracle.py``, commit
``aece7c372``) and every assertion here drives IDENTICAL inputs through both
sides.

Comparison convention: violation message strings are compared with exact
``==`` (they embed ``:.3f``-formatted distances — the message IS the
bit-identical output contract). Floats in property checks are compared via
``float.hex()`` where relevant.

Sections:
- Differential bit-exactness (random + edge-case netlists).
- PBT (hypothesis): five non-vacuous properties.
- Metamorphic relations: three, honestly bounded.
"""

from __future__ import annotations

import math
import random

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation._tht_check_py_oracle as _oracle
from temper_placer.core.netlist import Component, Netlist, Pin

# Rust symbol under test — must exist or this file fails to collect (RED).
THT_HOLE_COLLISIONS = _tdrc.tht_hole_collisions

from temper_placer.validation.tht_check import validate_hole_clearance as shim_validate  # noqa: E402


# ---------------------------------------------------------------------------
# Input construction
# ---------------------------------------------------------------------------

# Float strategies: holes live on a PCB, so keep magnitudes in realistic
# mm ranges and include exact-representable values (integers, halves) plus
# awkward values (subnormals excluded — drill diameters are physical).
_DRILLS = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_COORDS = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False)


def _make_netlist(
    holes: list[tuple[str, str, float, float, float]],
    n_extra: int = 0,
) -> Netlist:
    """Build a Netlist whose components carry injected ``pads`` (duck-typed,
    exactly how the oracle consumes them: ``comp.pads`` + ``pad.drill``)."""
    components = []
    refs = sorted({h[0] for h in holes})
    by_ref: dict[str, list[Pin]] = {r: [] for r in refs}
    for ref, num, px, py, drill in holes:
        by_ref[ref].append(Pin(name=num, number=num, position=(px, py), drill=drill))
    for i in range(len(refs) + n_extra):
        ref = refs[i] if i < len(refs) else f"X{i}"
        comp = Component(ref=ref, footprint="dummy", bounds=(1.0, 1.0))
        # duck-typed pads attribute (see tht_check.py's type: ignore)
        comp.pads = by_ref.get(ref, [])  # type: ignore[attr-defined]
        components.append(comp)
    return Netlist(components=components, nets=[])


def _positions_for(refs: list[str], holes: list[tuple[str, str, float, float, float]]) -> list[tuple[float, float]]:
    """Return one (x, y) per component — the origin of every hole on it
    (the oracle adds pad.position to the component position)."""
    order = []
    for ref in refs:
        xs = [px for (r, _n, px, _py, _d) in holes if r == ref]
        ys = [py for (r, _n, _px, py, _d) in holes if r == ref]
        order.append((xs[0] if xs else 0.0, ys[0] if ys else 0.0))
    return order


def _refs_from(holes: list[tuple[str, str, float, float, float]]) -> list[str]:
    return sorted({h[0] for h in holes})


# ---------------------------------------------------------------------------
# Differential — bit-exact message strings
# ---------------------------------------------------------------------------


def _run_both(holes, min_clearance):
    refs = _refs_from(holes)
    nl = _make_netlist(holes)
    positions = _positions_for(refs, holes)
    oracle = _oracle.validate_hole_clearance(nl, positions, min_clearance)
    shim = shim_validate(nl, positions, min_clearance)
    return oracle, shim


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=4).map(lambda s: f"C{abs(hash(s)) % 997}"),
            st.text(min_size=1, max_size=3).map(lambda s: f"P{abs(hash(s)) % 97}"),
            _COORDS,
            _COORDS,
            _DRILLS,
        ),
        min_size=0,
        max_size=8,
    ),
    st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_differential_random_netlists(holes, min_clearance):
    oracle, shim = _run_both(holes, min_clearance)
    assert oracle == shim


def test_differential_exact_representable_grid():
    """Holes on an exact grid — distances are exactly representable, so both
    arms compute identical values even under strict equality."""
    holes = [
        ("C1", "P1", 0.0, 0.0, 1.0),
        ("C1", "P2", 0.0, 0.0, 1.0),  # coincident holes on same component
        ("C2", "P1", 10.0, 0.0, 1.0),
        ("C3", "P1", 0.0, 5.0, 0.5),
        ("C3", "P2", 20.0, 20.0, 2.0),
    ]
    for mc in (0.0, 0.25, 1.0, 3.3):
        oracle, shim = _run_both(holes, mc)
        assert oracle == shim
        assert len(oracle) == 1  # only the coincident pair at (0,0) violates
    # exact message for mc=0.0 (required = 1.000)
    oracle, shim = _run_both(holes, 0.0)
    assert oracle[0] == "C1.P1 <-> C1.P2: dist=0.000mm (min 1.000mm)"


def test_differential_edge_cases():
    # empty holes
    assert _run_both([], 0.25) == ([], [])
    # single hole
    assert _run_both([("C1", "P1", 1.0, 2.0, 3.0)], 0.25)[0] == []
    # boundary touch: dist == required is NOT a violation (strict <)
    holes = [("C1", "P1", 0.0, 0.0, 1.0), ("C2", "P1", 2.0, 0.0, 1.0)]
    # radii are drill/2 = 0.5; dist = 2.0, required = 0.5 + 0.5 + 1.0 = 2.0
    # → not < → no violation at mc = 1.0
    oracle, shim = _run_both(holes, 1.0)
    assert oracle == shim == []
    # just inside: required = 2.01 > dist 2.0 → violation
    oracle, shim = _run_both(holes, 1.01)
    assert oracle == shim
    assert oracle == ["C1.P1 <-> C2.P1: dist=2.000mm (min 2.010mm)"]
    # SMD pads (drill == 0) are skipped
    holes = [("C1", "P1", 0.0, 0.0, 0.0), ("C2", "P1", 0.0, 0.0, 0.0)]
    assert _run_both(holes, 0.25)[0] == []


def test_differential_awkward_floats():
    """Values whose distances land on :.3f rounding boundaries — the message
    strings must match the oracle bit-for-bit (R1a, no tolerance)."""
    random.seed(1234)
    for _ in range(300):
        holes = [
            ("C1", "P1", random.uniform(-100, 100), random.uniform(-100, 100), random.uniform(0, 5)),
            ("C2", "P1", random.uniform(-100, 100), random.uniform(-100, 100), random.uniform(0, 5)),
            ("C3", "P1", random.uniform(-100, 100), random.uniform(-100, 100), random.uniform(0, 5)),
        ]
        mc = random.uniform(0, 2)
        oracle, shim = _run_both(holes, mc)
        assert oracle == shim


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties of the migrated kernel
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.just("C1"),
            st.text(min_size=1, max_size=2),
            _COORDS,
            _COORDS,
            _DRILLS.filter(lambda d: d > 0.0),
        ),
        min_size=1,
        max_size=6,
    ),
    st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_prop1_pairwise_reconstruction(holes, mc):
    """P1: the violation SET equals exactly the pairs (i<j) whose Euclidean
    distance is strictly below radius_i + radius_j + min_clearance."""
    holes_dedup = [dict(zip(("ref", "pad", "x", "y", "drill"), h)) for h in holes]
    messages = THT_HOLE_COLLISIONS(
        [(h["ref"], h["pad"], h["x"], h["y"], h["drill"] / 2.0) for h in holes_dedup],
        mc,
    )
    expected_pairs = []
    for i in range(len(holes_dedup)):
        for j in range(i + 1, len(holes_dedup)):
            a, b = holes_dedup[i], holes_dedup[j]
            dist = math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2)
            required = a["drill"] / 2.0 + b["drill"] / 2.0 + mc
            if dist < required:
                expected_pairs.append((i, j))
    assert len(messages) == len(expected_pairs)
    for (i, j) in expected_pairs:
        a, b = holes_dedup[i], holes_dedup[j]
        assert any(
            m.startswith(f"{a['ref']}.{a['pad']} <-> {b['ref']}.{b['pad']}:")
            for m in messages
        )


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.tuples(st.just("C1"), st.text(min_size=1), _COORDS, _COORDS, _DRILLS.filter(lambda d: d > 0.0)),
        min_size=1,
        max_size=5,
    ),
)
def test_prop2_monotone_in_clearance(holes):
    """P2: raising min_clearance never decreases the violation count."""
    holes_in = [(h[0], h[1], h[2], h[3], h[4] / 2.0) for h in holes]
    counts = []
    for mc in (0.0, 0.5, 1.0, 2.0, 5.0):
        counts.append(len(THT_HOLE_COLLISIONS(holes_in, mc)))
    assert counts == sorted(counts)


def test_prop3_message_format():
    """P3: every message matches the canonical ``REF.PAD <-> REF.PAD:
    dist=...mm (min ...mm)`` shape with exactly three decimals."""
    holes = [("C1", "P1", 0.0, 0.0, 0.5), ("C2", "P1", 1.0, 1.0, 0.5)]
    msgs = THT_HOLE_COLLISIONS(holes, 0.25)
    assert msgs
    for m in msgs:
        head, _, tail = m.partition(": ")
        assert "<->" in head
        lhs, rhs = head.split("<->")
        assert lhs.count(".") == 1 and rhs.count(".") == 1
        assert "dist=" in tail and "mm (min " in tail and "mm)" in tail
        for tok in (tail.split("dist=")[1].split("mm")[0], tail.split("min ")[1].split("mm)")[0]):
            assert len(tok.split(".")[1]) == 3 if "." in tok else True


def test_prop4_distant_holes_never_violate():
    """P4: holes farther apart than the sum of radii + clearance never appear
    in the output (direct kernel check, not via reconstruction)."""
    # radii passed as the 5th element (drill/2.0)
    holes = [("C1", "P1", 0.0, 0.0, 0.5), ("C2", "P1", 100.0, 100.0, 0.5)]
    assert THT_HOLE_COLLISIONS(holes, 0.25) == []
    holes2 = [("C1", "P1", 0.0, 0.0, 0.5), ("C2", "P1", 1.5, 0.0, 0.5)]
    # dist 1.5 vs required 0.5+0.5+0.25 = 1.25 → 1.5 < 1.25 false → none
    assert THT_HOLE_COLLISIONS(holes2, 0.25) == []
    # with clearance 0.5: required 1.5, dist 1.5 → not < → still none
    assert THT_HOLE_COLLISIONS(holes2, 0.5) == []
    # with clearance 0.6: required 1.6 > 1.5 → violation
    assert len(THT_HOLE_COLLISIONS(holes2, 0.6)) == 1


def test_prop5_zero_size_holes_are_physical():
    """P5: a zero-radius hole (drill 0) still participates when coincident —
    required = 0 + 0 + clearance, so violations appear only for clearance > 0."""
    assert THT_HOLE_COLLISIONS([("C1", "P1", 0.0, 0.0, 0.0), ("C2", "P1", 0.0, 0.0, 0.0)], 0.0) == []
    msgs = THT_HOLE_COLLISIONS([("C1", "P1", 0.0, 0.0, 0.0), ("C2", "P1", 0.0, 0.0, 0.0)], 0.25)
    assert len(msgs) == 1


# ---------------------------------------------------------------------------
# Metamorphic relations — three, honestly bounded
# ---------------------------------------------------------------------------


def test_mr1_reflection_preserves_violations():
    """MR1: reflecting every hole through the origin (x → -x, y → -y) leaves
    the violation set bit-identical (negation is exact in IEEE-754, so
    dx*dx + dy*dy and the distance are bit-identical)."""
    random.seed(99)
    holes = [
        ("C1", "P1", random.uniform(-100, 100), random.uniform(-100, 100), random.uniform(0.5, 5)),
        ("C2", "P1", random.uniform(-100, 100), random.uniform(-100, 100), random.uniform(0.5, 5)),
        ("C3", "P1", random.uniform(-100, 100), random.uniform(-100, 100), random.uniform(0.5, 5)),
    ]
    mc = random.uniform(0, 2)
    a = THT_HOLE_COLLISIONS([(r, p, x, y, d / 2.0) for (r, p, x, y, d) in holes], mc)
    b = THT_HOLE_COLLISIONS([(r, p, -x, -y, d / 2.0) for (r, p, x, y, d) in holes], mc)
    assert a == b


def test_mr2_permutation_preserves_message_set():
    """MR2: permuting the hole order permutes the pairwise comparisons, so the
    SET of messages is invariant under any input permutation (bounded to the
    message set — the ordering of messages within the list may change)."""
    random.seed(7)
    holes = [
        ("C1", "P1", random.uniform(-50, 50), random.uniform(-50, 50), random.uniform(0.5, 4)),
        ("C2", "P1", random.uniform(-50, 50), random.uniform(-50, 50), random.uniform(0.5, 4)),
        ("C3", "P1", random.uniform(-50, 50), random.uniform(-50, 50), random.uniform(0.5, 4)),
        ("C4", "P1", random.uniform(-50, 50), random.uniform(-50, 50), random.uniform(0.5, 4)),
    ]
    mc = 0.3
    base = set(THT_HOLE_COLLISIONS([(r, p, x, y, d / 2.0) for (r, p, x, y, d) in holes], mc))
    for _ in range(5):
        perm = holes[:]
        random.shuffle(perm)
        assert set(THT_HOLE_COLLISIONS([(r, p, x, y, d / 2.0) for (r, p, x, y, d) in perm], mc)) == base


def test_mr3_clearance_additivity_on_coincident_holes():
    """MR3: for coincident holes (dist = 0 exactly), a violation appears iff
    radius_a + radius_b + clearance > 0, and the message's min value equals
    that sum exactly (the ``:.3f`` rendering of an exactly-representable sum)."""
    for r1, r2, mc in ((0.5, 0.5, 0.0), (0.5, 0.5, 0.25), (1.0, 2.0, 0.5)):
        msgs = THT_HOLE_COLLISIONS([("C1", "P1", 0.0, 0.0, r1), ("C2", "P1", 0.0, 0.0, r2)], mc)
        if r1 + r2 + mc > 0:
            assert len(msgs) == 1
            expected = f"min {r1 + r2 + mc:.3f}mm)"
            assert msgs[0].endswith(expected)
            assert msgs[0] == f"C1.P1 <-> C2.P1: dist=0.000mm (min {r1 + r2 + mc:.3f}mm)"
        else:
            assert msgs == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
