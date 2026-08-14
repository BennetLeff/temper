"""Property-based tests for the Phase-A U5 DRC marshalling types
(Wave-4 discipline contract G4/G5).

Verification unit: the U5 marshal cluster — `ConstraintValue`,
`TypedConstraintSet`, `DrcBoardSnapshot` (both constructors) and the
`CheckRunner` data surface, all exercised through the Python shims that
delegate to the Rust pyclasses.

Module → property map (G4 note: every module reached by >= 1 property):

  | Module                        | Properties |
  |-------------------------------|------------|
  | `ConstraintValue`             | P1, P2     |
  | `TypedConstraintSet`          | P3         |
  | `CheckRunner` (data surface)  | P4         |
  | `DrcBoardSnapshot::from_netlist` | P5      |
  | `DrcBoardSnapshot::from_state`   | P6      |

Reachability is measured, not assumed: P1/P2 draw inputs and assert the
kernel's output against the oracle semantics directly; P3 uses a fixed
tight board (0.5 mm apart components) so clearance rules always fire; P5
draws a varied `board_margin`; P6 always draws >= 1 component. Every
property has a `test_pN_fails_for_<mutant>` companion (G4 vacuity guard)
proving a degenerate kernel violates it.

Metamorphic relations (G5, >= 3) are in the labelled section at the bottom.
"""

from __future__ import annotations

from dataclasses import dataclass  # noqa: E402, I001  (mid-file import block)
from types import SimpleNamespace  # noqa: E402, I001

import numpy as np  # noqa: E402, I001
import pytest  # noqa: E402
import temper_drc_rs as _tdrc  # noqa: E402
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from temper_placer.validation import drc_oracle as _oracle_mod  # noqa: E402
from temper_placer.validation import drc_runner as _runner_mod  # noqa: E402
from temper_placer.validation.drc_result import (  # noqa: E402
    ClearanceCheck,
    ComponentOverlapCheck,
    CreepageCheck,
    LoopAreaCheck,
)
from temper_placer.validation.drc_runner import CheckRunner  # noqa: E402
from temper_placer.validation.drc_types import (  # noqa: E402
    ComponentPlacement,
    Placement,
)

# The verbatim pre-migration `_constraints_to_dict` (pinned in the G1
# differential file) is the oracle reference for P3's kernel-equivalence.
from tests.validation.test_drc_marshal_rust_differential import (  # noqa: E402, I001
    _oracle_constraints_to_dict,
)


def _canon_violations(violations):
    """Sorted-affected_items canonical form (the rules build it from a Rust
    HashSet — set-deterministic, order is a RandomState artifact)."""
    out = []
    for v in violations:
        v = dict(v)
        v["affected_items"] = sorted(v.get("affected_items", []))
        out.append(v)
    return out


# ---------------------------------------------------------------------------
# Input strategies
# ---------------------------------------------------------------------------


@st.composite
def plain_values(draw):
    """A plain value the oracle passes through unchanged (scalar or list)."""
    return draw(
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-100, max_value=100),
            st.floats(min_value=-100.0, max_value=100.0, allow_nan=False),
            st.text(min_size=0, max_size=10),
            st.lists(st.integers(min_value=-5, max_value=5), min_size=0, max_size=5),
        )
    )


@st.composite
def isolation_barrier(draw):
    from temper_placer._constraint_types import IsolationBarrier

    return IsolationBarrier(
        name=draw(st.text(min_size=1, max_size=8)),
        x_mm=draw(st.floats(0.0, 100.0)),
        y_span=(draw(st.floats(0.0, 50.0)), draw(st.floats(50.0, 100.0))),
        points=draw(
            st.lists(
                st.tuples(st.floats(0.0, 100.0), st.floats(0.0, 100.0)),
                min_size=0,
                max_size=3,
            )
        ),
        layers="all",
        clearance_mm=draw(st.floats(0.0, 10.0)),
    )


@st.composite
def placements(draw):
    """A Placement pyclass with >= 1 component."""
    n = draw(st.integers(min_value=1, max_value=4))
    comps = {}
    for i in range(n):
        ref = f"C{i}"
        comps[ref] = ComponentPlacement(
            ref=ref,
            footprint="0402",
            x=draw(st.floats(0.0, 50.0)),
            y=draw(st.floats(0.0, 50.0)),
            rotation=float(draw(st.integers(0, 3)) * 90.0),
            layer=draw(st.sampled_from(["F.Cu", "B.Cu", None])),
            width=draw(st.floats(0.5, 5.0)),
            height=draw(st.floats(0.5, 5.0)),
            net_class="Signal",
        )
    return Placement(
        components=comps,
        nets={"N1": list(comps.keys())},
        net_classes={"N1": "Signal"},
        board_width=draw(st.floats(50.0, 200.0)),
        board_height=draw(st.floats(50.0, 200.0)),
    )


@st.composite
def netlist_context(draw):
    """Duck-typed placer context + numpy positions for from_netlist."""
    n = draw(st.integers(min_value=1, max_value=3))

    @dataclass
    class _Comp:
        ref: str
        footprint: str
        width: float
        height: float
        net_class: str
        initial_rotation_quadrant: int | None
        initial_side: int | None

    comps = [
        _Comp(
            ref=f"C{i}",
            footprint=draw(st.sampled_from(["R_0603", "TO-247", "QFN-32", "MountingHole"])),
            width=1.0,
            height=1.0,
            net_class="Signal",
            initial_rotation_quadrant=draw(st.integers(0, 3)),
            initial_side=draw(st.integers(0, 1)),
        )
        for i in range(n)
    ]
    positions = np.zeros((n, 2), dtype=np.float64)
    for i in range(n):
        positions[i, 0] = draw(st.floats(0.0, 50.0))
        positions[i, 1] = draw(st.floats(0.0, 50.0))
    netlist = SimpleNamespace(components=comps, nets=[])
    ctx = SimpleNamespace(
        netlist=netlist,
        board=SimpleNamespace(width=draw(st.floats(50.0, 200.0)),
                              height=draw(st.floats(50.0, 200.0))),
        # Deliberately never 3.0 (the placer builder's hardcoded fallback)
        # so the margin property is genuinely discriminating.
        board_margin=draw(st.sampled_from([1.0, 2.0, 4.0, 8.0])),
        clearance_rules=[],
    )
    return positions, ctx


@st.composite
def check_sequences(draw):
    pool = [ClearanceCheck(), ComponentOverlapCheck(), CreepageCheck(), LoopAreaCheck()]
    return [draw(st.sampled_from(pool)) for _ in range(draw(st.integers(min_value=1, max_value=6)))]


# ---------------------------------------------------------------------------
# P1 — ConstraintValue round-trips plain values
# ---------------------------------------------------------------------------


@given(plain_values())
@settings(max_examples=50, deadline=None)
def test_p1_plain_value_round_trip(v):
    """P1: `_constraint_value_to_plain(v).to_python() == v` for plain
    values (scalars and flat lists). A kernel returning a constant would
    satisfy the non-plain-value space but not this identity."""
    got = _oracle_mod._constraint_value_to_plain(v).to_python()
    assert got == v


# ---------------------------------------------------------------------------
# P2 — ConstraintValue unwraps pydantic models via model_dump(mode="json")
# ---------------------------------------------------------------------------


@given(isolation_barrier())
@settings(max_examples=50, deadline=None)
def test_p2_model_unwraps_to_json_plain(b):
    """P2: `_constraint_value_to_plain(b).to_python()` equals
    `b.model_dump(mode="json")` for any pydantic IsolationBarrier. A kernel
    returning the model itself (or a constant) violates it."""
    plain = _oracle_mod._constraint_value_to_plain(b).to_python()
    assert plain == b.model_dump(mode="json")


# ---------------------------------------------------------------------------
# P3 — TypedConstraintSet == dict wire format at the kernel boundary
# ---------------------------------------------------------------------------

_TIGHT_BOARD = {
    "board": {"width_mm": 100.0, "height_mm": 100.0},
    "components": [
        {"ref": "C1", "x": 10.0, "y": 10.0, "rot": 0.0, "side": "top",
         "width": 1.0, "height": 1.0, "net_class": "Signal", "package_type": "smd"},
        {"ref": "C2", "x": 10.5, "y": 10.0, "rot": 0.0, "side": "top",
         "width": 1.0, "height": 1.0, "net_class": "Signal", "package_type": "smd"},
    ],
    "nets": {},
    "net_classes": {},
}


@st.composite
def clearance_rules(draw):
    n = draw(st.integers(min_value=1, max_value=4))
    return [
        _tdrc.ClearanceRule(
            from_class="Signal",
            to_class="Signal",
            min_mm=draw(st.floats(0.5, 5.0)),
            description="",
        )
        for _ in range(n)
    ]


@given(clearance_rules())
@settings(max_examples=40, deadline=None)
def test_p3_typed_constraints_match_dict_path(rules):
    """P3: on a fixed tight board, `run_drc(board, TypedConstraintSet)` and
    `run_drc(board, <verbatim oracle constraints dict>)` produce the same
    violations — the typed struct and the pinned pre-migration dict wire
    format are equivalent at the kernel boundary. The board components are
    0.5 mm apart, so any non-empty clearance rule always fires and empty
    constraints never do: the input class genuinely discriminates."""
    cs = _tdrc.ConstraintSet(clearances=rules)
    typed = _runner_mod._constraints_to_dict(cs)
    typed_v = _tdrc.run_drc(_TIGHT_BOARD, typed)
    oracle_v = _tdrc.run_drc(_TIGHT_BOARD, _oracle_constraints_to_dict(cs))
    assert _canon_violations(typed_v) == _canon_violations(oracle_v)
    # And the kernel genuinely consumed the clearances (non-vacuous board).
    assert len(typed_v) >= 1


# ---------------------------------------------------------------------------
# P4 — CheckRunner data surface
# ---------------------------------------------------------------------------


@given(check_sequences())
@settings(max_examples=30, deadline=None)
def test_p4_check_runner_data_surface(checks):
    """P4: CheckRunner.add_checks/clear/check_names/categories/
    get_checks_by_category form a consistent data surface: names and
    categories reflect exactly the registered checks, category queries
    return the same objects, and clear() resets to empty."""
    runner = CheckRunner()
    runner.add_checks(checks)
    assert runner.check_names == [c.name for c in checks]
    assert runner.categories == {c.category for c in checks}
    for category in {c.category for c in checks}:
        got = runner.get_checks_by_category(category)
        assert [c.name for c in got] == [c.name for c in checks if c.category == category]
    runner.clear()
    assert runner.check_names == []
    assert runner.categories == set()


# ---------------------------------------------------------------------------
# P5 — DrcBoardSnapshot.from_netlist (placer path) honours its inputs
# ---------------------------------------------------------------------------


@given(netlist_context())
@settings(max_examples=40, deadline=None)
def test_p5_from_netlist_placer_path_invariants(ctx_args):
    """P5: the placer-path snapshot reproduces the passed board dimensions
    and margin exactly, and every component carries a valid side and
    package type. A kernel ignoring its scalar inputs (hardcoding the 3.0
    margin fallback) violates the margin assertion — the strategy never
    draws 3.0, so the property is genuinely discriminating."""
    positions, ctx = ctx_args
    snapshot = _oracle_mod.DRCOracle(
        runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={}
    )._build_board_dict(positions, ctx)
    bd = snapshot.to_dict()
    assert bd["board"]["width_mm"] == float(ctx.board.width)
    assert bd["board"]["height_mm"] == float(ctx.board.height)
    assert bd["board"]["margin_mm"] == ctx.board_margin
    assert len(bd["components"]) == len(ctx.netlist.components)
    for c in bd["components"]:
        assert c["side"] in ("top", "bottom")
        assert c["package_type"] in ("smd", "tht", "to247", "to220", "bga", "qfn", "qfp", "dpak")


# ---------------------------------------------------------------------------
# P6 — DrcBoardSnapshot.from_state shape invariants
# ---------------------------------------------------------------------------


@given(placements())
@settings(max_examples=40, deadline=None)
def test_p6_from_state_shape_invariants(p):
    """P6: from_state preserves component count, board dimensions and the
    3.0 margin default, and every component lands on a valid side. A
    kernel returning an empty/constant snapshot violates the count
    assertion (the strategy always draws >= 1 component)."""
    bd = _runner_mod._placement_to_board_dict(p).to_dict()
    assert len(bd["components"]) == len(p.components)
    assert bd["board"]["width_mm"] == float(p.board_width)
    assert bd["board"]["height_mm"] == float(p.board_height)
    assert bd["board"]["margin_mm"] == 3.0
    for c in bd["components"]:
        assert c["side"] in ("top", "bottom")


# ---------------------------------------------------------------------------
# G4 vacuity guards — each property must fail for a degenerate kernel
# ---------------------------------------------------------------------------


def _concrete_plain_value():
    return [1, 2.5, "x", None]


def _concrete_barrier():
    from temper_placer._constraint_types import IsolationBarrier

    return IsolationBarrier(
        name="B", x_mm=1.0, y_span=(0.0, 10.0),
        points=[[1.0, 0.0], [1.0, 10.0]], layers="all", clearance_mm=1.0,
    )


def _concrete_rules():
    return [_tdrc.ClearanceRule(from_class="Signal", to_class="Signal", min_mm=1.0, description="")]


def _concrete_checks():
    return [ClearanceCheck(), CreepageCheck()]


def _concrete_netlist_ctx():
    @dataclass
    class _Comp:
        ref: str
        footprint: str
        width: float
        height: float
        net_class: str
        initial_rotation_quadrant: int | None
        initial_side: int | None

    netlist = SimpleNamespace(
        components=[_Comp("C1", "R_0603", 1.0, 1.0, "Signal", 1, 0)],
        nets=[],
    )
    ctx = SimpleNamespace(
        netlist=netlist,
        board=SimpleNamespace(width=100.0, height=200.0),
        board_margin=4.0,
        clearance_rules=[],
    )
    return np.array([[10.0, 20.0]], dtype=np.float64), ctx


def _concrete_placement():
    return Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="0402", x=1.0, y=1.0,
                                     rotation=0.0, layer="F.Cu", width=1.0, height=1.0,
                                     net_class="Signal"),
        },
        nets={"N1": ["C1"]},
        net_classes={"N1": "Signal"},
        board_width=100.0,
        board_height=100.0,
    )


def test_p1_fails_for_constant_none_kernel(monkeypatch):
    monkeypatch.setattr(
        _oracle_mod,
        "_constraint_value_to_plain",
        lambda _v: _tdrc.ConstraintValue.from_python(None),
    )
    with pytest.raises(AssertionError):
        test_p1_plain_value_round_trip.hypothesis.inner_test(_concrete_plain_value())


def test_p2_fails_for_constant_none_kernel(monkeypatch):
    monkeypatch.setattr(
        _oracle_mod,
        "_constraint_value_to_plain",
        lambda _v: _tdrc.ConstraintValue.from_python(None),
    )
    with pytest.raises(AssertionError):
        test_p2_model_unwraps_to_json_plain.hypothesis.inner_test(_concrete_barrier())


def test_p3_fails_for_empty_constraints_kernel(monkeypatch):
    monkeypatch.setattr(
        _runner_mod,
        "_constraints_to_dict",
        lambda _c: _tdrc.TypedConstraintSet.from_state(_tdrc.ConstraintSet()),
    )
    with pytest.raises(AssertionError):
        test_p3_typed_constraints_match_dict_path.hypothesis.inner_test(_concrete_rules())


def test_p4_fails_for_noop_add_checks(monkeypatch):
    monkeypatch.setattr(CheckRunner, "add_checks", lambda _self, _checks: _self)
    with pytest.raises(AssertionError):
        test_p4_check_runner_data_surface.hypothesis.inner_test(_concrete_checks())


def test_p5_fails_for_hardcoded_margin_kernel(monkeypatch):
    def _hardcoded_margin(self, positions, context, parsed_pcb=None):
        return _tdrc.DrcBoardSnapshot.from_netlist(
            positions=positions,
            netlist=context.netlist,
            board_width=float(context.board.width),
            board_height=float(context.board.height),
            board_margin=3.0,
            clearance_rules=context.clearance_rules,
        )

    monkeypatch.setattr(_oracle_mod.DRCOracle, "_build_board_dict", _hardcoded_margin)
    with pytest.raises(AssertionError):
        test_p5_from_netlist_placer_path_invariants.hypothesis.inner_test(_concrete_netlist_ctx())


def test_p6_fails_for_empty_snapshot_kernel(monkeypatch):
    monkeypatch.setattr(
        _runner_mod,
        "_placement_to_board_dict",
        lambda _p: _tdrc.DrcBoardSnapshot.from_state(_tdrc.Placement()),
    )
    with pytest.raises(AssertionError):
        test_p6_from_state_shape_invariants.hypothesis.inner_test(_concrete_placement())


# ---------------------------------------------------------------------------
# G5 metamorphic relations (>= 3), each naming its exactness claim
# ---------------------------------------------------------------------------


def test_mr1_component_list_preserves_dict_insertion_order():
    """MR1 (order preservation, exact): from_state's component list follows
    the Placement.components dict insertion order; permuting the dict order
    permutes the list identically."""
    c1 = ComponentPlacement(ref="C1", footprint="0402", x=1.0, y=1.0, rotation=0.0,
                            layer="F.Cu", width=1.0, height=1.0, net_class="Signal")
    c2 = ComponentPlacement(ref="C2", footprint="0402", x=2.0, y=2.0, rotation=0.0,
                            layer="F.Cu", width=1.0, height=1.0, net_class="Signal")
    p_ab = Placement(components={"C1": c1, "C2": c2}, nets={}, net_classes={})
    p_ba = Placement(components={"C2": c2, "C1": c1}, nets={}, net_classes={})
    refs_ab = [c["ref"] for c in _runner_mod._placement_to_board_dict(p_ab).to_dict()["components"]]
    refs_ba = [c["ref"] for c in _runner_mod._placement_to_board_dict(p_ba).to_dict()["components"]]
    assert refs_ab == ["C1", "C2"]
    assert refs_ba == ["C2", "C1"]


def test_mr2_constraint_value_list_is_structural_recursion():
    """MR2 (structural recursion, exact): converting a list is the pointwise
    conversion of its elements — `from_python([a, b])` decomposes exactly."""
    from temper_placer._constraint_types import IsolationBarrier

    a = IsolationBarrier(name="A", x_mm=1.0, y_span=(0.0, 1.0), points=[], layers="all", clearance_mm=1.0)
    b = IsolationBarrier(name="B", x_mm=2.0, y_span=(1.0, 2.0), points=[], layers="all", clearance_mm=2.0)
    whole = _oracle_mod._constraint_value_to_plain([a, b]).to_python()
    parts = [
        _oracle_mod._constraint_value_to_plain(a).to_python(),
        _oracle_mod._constraint_value_to_plain(b).to_python(),
    ]
    assert whole == parts


def test_mr3_all_none_config_equals_no_config():
    """MR3 (defaults equivalence, exact): a constraints_config whose every
    key is None must produce the same typed set as no config at all."""
    all_none = SimpleNamespace(
        zones=None, critical_loops=None, noise_domains=None,
        isolation_barriers=None, thermal_properties=None,
        matched_length_groups=None, snubber_requirements=None,
        bleed_resistor=None, skin_effect_derating=None,
    )
    kwargs = {"clearance_rules": [], "board_width": 152.0, "board_height": 234.0}
    a = _tdrc.TypedConstraintSet.from_context(constraints_config=None, **kwargs).to_dict()
    b = _tdrc.TypedConstraintSet.from_context(constraints_config=all_none, **kwargs).to_dict()
    assert a == b


def test_mr4_board_scale_doubles_dims_preserves_counts():
    """MR4 (scale, exact for the power-of-two factor 2): doubling the board
    dimensions doubles width/height in the snapshot while component and net
    counts are unchanged."""
    p_small = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="0402", x=1.0, y=1.0, rotation=0.0,
                                     layer="F.Cu", width=1.0, height=1.0, net_class="Signal"),
        },
        nets={"N1": ["C1"]},
        net_classes={"N1": "Signal"},
        board_width=100.0,
        board_height=100.0,
    )
    p_big = Placement(
        components=p_small.components,
        nets=dict(p_small.nets),
        net_classes=dict(p_small.net_classes),
        board_width=200.0,
        board_height=200.0,
    )
    d_small = _runner_mod._placement_to_board_dict(p_small).to_dict()
    d_big = _runner_mod._placement_to_board_dict(p_big).to_dict()
    assert d_big["board"]["width_mm"] == 2 * d_small["board"]["width_mm"]
    assert d_big["board"]["height_mm"] == 2 * d_small["board"]["height_mm"]
    assert len(d_big["components"]) == len(d_small["components"])
    assert len(d_big["nets"]) == len(d_small["nets"])
