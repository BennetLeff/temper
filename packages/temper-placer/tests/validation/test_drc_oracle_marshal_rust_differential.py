"""Differential test: drc_oracle marshal kernels in Rust (temper_drc_rs)
vs the pinned Python oracle (Wave 4, marshalling boundary fanout).

``temper_placer/validation/drc_oracle.py`` moves its pydantic→plain
conversion and K1-schema dict builders to ``temper_drc_rs``:

- ``_constraint_value_to_plain`` → ``temper_drc_rs.constraint_value_to_plain_py``
- ``DRCOracle._build_board_dict`` → ``temper_drc_rs.build_board_dict_py``
- ``DRCOracle._build_board_dict_from_parsed_pcb`` →
  ``temper_drc_rs.build_board_dict_from_parsed_pcb_py``
- ``DRCOracle._build_constraints_dict`` →
  ``temper_drc_rs.build_constraints_dict_py``

The pydantic ``PlacementConstraints`` model stays Python (JUSTIFIED-KEEP);
only the conversion of its values to the flat wire format migrates.

Comparison convention: dicts compared recursively via ``==``; floats
compared via ``float.hex()`` for bit-exactness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import temper_drc_rs as _tdrc

from temper_placer._constraint_types import IsolationBarrier
from temper_placer.validation.drc_oracle import (
    DRCOracle,
    _constraint_value_to_plain as py_constraint_value_to_plain,
)

# ---------------------------------------------------------------------------
# Rust symbols under test — must exist or this file fails to collect (RED).
# ---------------------------------------------------------------------------

CONSTRAINT_VALUE_TO_PLAIN = _tdrc.constraint_value_to_plain_py
BUILD_BOARD_DICT = _tdrc.build_board_dict_py
BUILD_BOARD_DICT_FROM_PARSED_PCB = _tdrc.build_board_dict_from_parsed_pcb_py
BUILD_CONSTRAINTS_DICT = _tdrc.build_constraints_dict_py


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _float_hex_recursive(obj: Any) -> Any:
    """Recursively convert all floats in a nested structure to their hex
    representation so bit-exact comparison can use ``==``."""
    if isinstance(obj, float):
        return float(obj).hex()
    if isinstance(obj, dict):
        return {k: _float_hex_recursive(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_float_hex_recursive(v) for v in obj]
    return obj


def _dicts_equal_bit_exact(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Compare two nested dicts for bit-exact equality, converting floats
    to hex strings along the way so infinitesimal fp differences are visible."""
    return _float_hex_recursive(a) == _float_hex_recursive(b)


# ---------------------------------------------------------------------------
# constraint_value_to_plain — differential
# ---------------------------------------------------------------------------


class _TestModel(IsolationBarrier):
    """A pydantic model with all the field types we care about."""


def test_constraint_value_to_plain_pydantic_model():
    """A pydantic BaseModel becomes a plain dict via model_dump(mode='json')."""
    barrier = IsolationBarrier(
        name="TEST",
        x_mm=94.703,
        y_span=(0.0, 274.0),
        points=[[94.703, 0.0], [60.0, 100.0]],
        layers="all",
        clearance_mm=8.0,
    )
    py_result = py_constraint_value_to_plain(barrier)
    rs_result = CONSTRAINT_VALUE_TO_PLAIN(barrier)
    assert py_result == rs_result
    # tuple → list coercion
    assert isinstance(rs_result["y_span"], list)
    assert isinstance(rs_result["points"], list)
    assert all(isinstance(p, list) for p in rs_result["points"])


def test_constraint_value_to_plain_list_of_models():
    """A list of pydantic models becomes a list of plain dicts."""
    barriers = [
        IsolationBarrier(name="B1", x_mm=1.0, y_span=(0.0, 10.0), points=[], layers="all", clearance_mm=1.0),
        IsolationBarrier(name="B2", x_mm=2.0, y_span=(10.0, 20.0), points=[], layers="all", clearance_mm=2.0),
    ]
    py_result = py_constraint_value_to_plain(barriers)
    rs_result = CONSTRAINT_VALUE_TO_PLAIN(barriers)
    assert py_result == rs_result
    assert [p["name"] for p in rs_result] == ["B1", "B2"]


def test_constraint_value_to_plain_scalars_pass_through():
    """Non-model values are returned unchanged."""
    assert CONSTRAINT_VALUE_TO_PLAIN(None) is None
    assert CONSTRAINT_VALUE_TO_PLAIN(3.14) == 3.14
    assert CONSTRAINT_VALUE_TO_PLAIN("hello") == "hello"
    assert CONSTRAINT_VALUE_TO_PLAIN(42) == 42
    assert CONSTRAINT_VALUE_TO_PLAIN(True) is True


def test_constraint_value_to_plain_nested():
    """Nested structures (list of models, tuples inside models) are recursively converted."""
    barrier = IsolationBarrier(
        name="NESTED",
        x_mm=0.0,
        y_span=(1.0, 2.0),
        points=[],
        layers="all",
        clearance_mm=3.0,
    )
    nested = [barrier, [barrier], {"key": barrier}]
    py_result = py_constraint_value_to_plain(nested)
    rs_result = CONSTRAINT_VALUE_TO_PLAIN(nested)
    assert py_result == rs_result


# ---------------------------------------------------------------------------
# build_constraints_dict — differential
# ---------------------------------------------------------------------------


def _mock_context(clearance_rules=None, constraints_config=None, width=152.0, height=234.0):
    """Build a duck-typed context object for _build_constraints_dict."""
    return SimpleNamespace(
        clearance_rules=clearance_rules or [],
        board=SimpleNamespace(width=width, height=height),
        constraints_config=constraints_config,
    )


@dataclass
class _FakeClearanceRule:
    net_class_a: str
    net_class_b: str
    min_clearance: float
    because: str = ""


def test_build_constraints_dict_empty():
    """Empty clearance rules + no constraints_config → default dict."""
    ctx = _mock_context()
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_constraints_dict(ctx).to_dict()
    # Phase-A U5 union dict: carries the engine's documented default
    # `thermal_constraints` key, which build_constraints_dict_py never emits.
    py_result.pop("thermal_constraints", None)
    rs_result = BUILD_CONSTRAINTS_DICT(
        clearance_rules=[],
        constraints_config=None,
        board_width=152.0,
        board_height=234.0,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)


def test_build_constraints_dict_with_clearance_rules():
    """Clearance rules are mapped to the K1 clearances list."""
    rules = [
        _FakeClearanceRule("HV", "LV", 8.0, "safety"),
        _FakeClearanceRule("HV", "Signal", 4.0),
    ]
    ctx = _mock_context(clearance_rules=rules)
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_constraints_dict(ctx).to_dict()
    py_result.pop("thermal_constraints", None)
    rs_result = BUILD_CONSTRAINTS_DICT(
        clearance_rules=rules,
        constraints_config=None,
        board_width=152.0,
        board_height=234.0,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)
    assert len(rs_result["clearances"]) == 2
    assert rs_result["clearances"][0]["from_class"] == "HV"
    assert rs_result["clearances"][0]["clearance_mm"] == 8.0


def test_build_constraints_dict_with_isolation_barriers():
    """Isolation barriers from constraints_config are merged via constraint_value_to_plain."""
    barrier = IsolationBarrier(
        name="IB1",
        x_mm=50.0,
        y_span=(0.0, 100.0),
        points=[[50.0, 0.0], [50.0, 100.0]],
        layers="all",
        clearance_mm=8.0,
    )
    config = SimpleNamespace(
        isolation_barriers=[barrier],
        zones=None,
        critical_loops=None,
        noise_domains=None,
        thermal_properties=None,
        matched_length_groups=None,
        snubber_requirements=None,
        bleed_resistor=None,
        skin_effect_derating=None,
    )
    ctx = _mock_context(constraints_config=config)
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_constraints_dict(ctx).to_dict()
    py_result.pop("thermal_constraints", None)
    rs_result = BUILD_CONSTRAINTS_DICT(
        clearance_rules=[],
        constraints_config=config,
        board_width=152.0,
        board_height=234.0,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)
    assert rs_result["isolation_barriers"][0]["name"] == "IB1"


# ---------------------------------------------------------------------------
# build_board_dict — differential
# ---------------------------------------------------------------------------

def _make_numpy_positions(n: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(0, 100, (n, 2))


@dataclass
class _FakeComponent:
    ref: str
    footprint: str
    width: float
    height: float
    net_class: str = "Signal"
    initial_rotation: int | None = None
    initial_side: int | None = None


@dataclass
class _FakePin:
    ref: str
    pin: str


@dataclass
class _FakeNet:
    name: str
    pins: list[tuple[str, str]]  # list of (ref, pin_number)
    net_class: str = "Signal"


def test_build_board_dict_empty():
    """Empty netlist → minimal K1 board dict."""
    positions = _make_numpy_positions(0)
    netlist = SimpleNamespace(components=[], nets=[])
    rules: list[Any] = []
    ctx = SimpleNamespace(
        netlist=netlist,
        board=SimpleNamespace(width=100.0, height=200.0),
        board_margin=5.0,
        clearance_rules=rules,
    )
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict(positions, ctx).to_dict()
    rs_result = BUILD_BOARD_DICT(
        positions=positions,
        netlist=netlist,
        board_width=100.0,
        board_height=200.0,
        board_margin=5.0,
        clearance_rules=rules,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)
    assert rs_result["components"] == []
    assert rs_result["nets"] == {}
    assert rs_result["board"] == {"width_mm": 100.0, "height_mm": 200.0, "margin_mm": 5.0}


def test_build_board_dict_with_components():
    """Components are mapped to K1 component dicts."""
    positions = np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float64)
    comps = [
        _FakeComponent(ref="C1", footprint="R_0603", width=1.6, height=0.8),
        _FakeComponent(ref="C2", footprint="SOIC-8", width=5.0, height=6.0),
    ]
    nets: list[Any] = []
    netlist = SimpleNamespace(components=comps, nets=nets)
    rules: list[Any] = []
    ctx = SimpleNamespace(
        netlist=netlist,
        board=SimpleNamespace(width=100.0, height=200.0),
        board_margin=5.0,
        clearance_rules=rules,
    )
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict(positions, ctx).to_dict()
    rs_result = BUILD_BOARD_DICT(
        positions=positions,
        netlist=netlist,
        board_width=100.0,
        board_height=200.0,
        board_margin=5.0,
        clearance_rules=rules,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)
    comps_out = rs_result["components"]
    assert len(comps_out) == 2
    assert comps_out[0]["ref"] == "C1"
    assert comps_out[0]["x"] == 10.0
    assert comps_out[0]["y"] == 20.0
    assert comps_out[0]["side"] == "top"
    assert comps_out[1]["ref"] == "C2"


def test_build_board_dict_with_rotation_and_side():
    """Rotation (quantized 0-3 → degrees) and side (0=top, 1=bottom)."""
    positions = np.array([[5.0, 5.0]], dtype=np.float64)
    # rotation=2 means 180°, side=1 means bottom
    comps = [
        _FakeComponent(ref="U1", footprint="TQFP-64", width=10.0, height=10.0,
                       initial_rotation=2, initial_side=1),
    ]
    netlist = SimpleNamespace(components=comps, nets=[])
    rules: list[Any] = []
    ctx = SimpleNamespace(netlist=netlist, board=SimpleNamespace(width=100.0, height=200.0),
                          board_margin=3.0, clearance_rules=rules)
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict(positions, ctx).to_dict()
    rs_result = BUILD_BOARD_DICT(
        positions=positions, netlist=netlist, board_width=100.0, board_height=200.0,
        board_margin=3.0, clearance_rules=rules,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)
    c = rs_result["components"][0]
    assert c["rot"] == 180.0
    assert c["side"] == "bottom"


def test_build_board_dict_with_nets():
    """Nets are mapped to K1 nets + net_classes dicts, with deduplicated refs."""
    positions = np.array([[0.0, 0.0], [10.0, 10.0], [20.0, 20.0]], dtype=np.float64)
    comps = [
        _FakeComponent(ref="C1", footprint="R_0603", width=1.0, height=1.0),
        _FakeComponent(ref="C2", footprint="R_0603", width=1.0, height=1.0),
        _FakeComponent(ref="C3", footprint="R_0603", width=1.0, height=1.0),
    ]
    nets = [
        _FakeNet(name="NET1", pins=[("C1", "1"), ("C2", "1")], net_class="Signal"),
        _FakeNet(name="NET2", pins=[("C2", "2"), ("C3", "1")], net_class="Power"),
        # Duplicate ref in same net should be deduplicated
        _FakeNet(name="NET3", pins=[("C1", "2"), ("C1", "2")], net_class="Signal"),
    ]
    netlist = SimpleNamespace(components=comps, nets=nets)
    rules: list[Any] = []
    ctx = SimpleNamespace(netlist=netlist, board=SimpleNamespace(width=100.0, height=100.0),
                          board_margin=3.0, clearance_rules=rules)
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict(positions, ctx).to_dict()
    rs_result = BUILD_BOARD_DICT(
        positions=positions, netlist=netlist, board_width=100.0, board_height=100.0,
        board_margin=3.0, clearance_rules=rules,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)
    assert set(rs_result["nets"]["NET1"]) == {"C1", "C2"}
    assert set(rs_result["nets"]["NET2"]) == {"C2", "C3"}
    assert rs_result["nets"]["NET3"] == ["C1"]  # deduplicated
    assert rs_result["net_classes"]["NET1"] == "Signal"
    assert rs_result["net_classes"]["NET2"] == "Power"


def test_build_board_dict_with_clearance_rules():
    """Clearance rules populate net_class_rules."""
    positions = np.array([[0.0, 0.0]], dtype=np.float64)
    comps = [_FakeComponent(ref="C1", footprint="R_0603", width=1.0, height=1.0)]
    netlist = SimpleNamespace(components=comps, nets=[])
    rules = [
        _FakeClearanceRule("HV", "LV", 8.0),
        _FakeClearanceRule("HV", "Signal", 4.0),
    ]
    ctx = SimpleNamespace(netlist=netlist, board=SimpleNamespace(width=100.0, height=100.0),
                          board_margin=3.0, clearance_rules=rules)
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict(positions, ctx).to_dict()
    rs_result = BUILD_BOARD_DICT(
        positions=positions, netlist=netlist, board_width=100.0, board_height=100.0,
        board_margin=3.0, clearance_rules=rules,
    )
    # `oracle._build_board_dict` (production) calls the typed
    # `DrcBoardSnapshot.from_netlist` with `net_class_defs=TEMPER_NET_CLASSES`
    # (drc_oracle.py), so "Signal" -- a real TEMPER_NET_CLASSES entry -- now
    # gets its real `creepage_mm`/`voltage_v`/`safety_category` (0.0, 0.0,
    # "LV") instead of the pre-fix `None` hardcode. `BUILD_BOARD_DICT`
    # (`build_board_dict_py`) is the frozen migration-parity kernel: it takes
    # no `net_class_defs` parameter and structurally cannot produce these
    # (docs/plans -- "Do NOT edit the semantics"). This was already a latent
    # gap for `trace_width_mm` (#1045) that stayed invisible here only
    # because Signal's real 0.2mm width happens to equal the frozen 0.2mm
    # hardcode; creepage_mm/voltage_v/safety_category have no such
    # coincidence, so the six safety fields are excluded from the bit-exact
    # comparison (mirroring `thermal_constraints` being dropped in
    # test_typed_constraints_from_context_matches_validated_kernel above).
    safety_fields = (
        "creepage_mm", "voltage_v", "max_current_rating",
        "safety_category", "required_layer", "routing_strategy",
    )

    def _drop_safety_fields(result: dict) -> dict:
        ncr = {
            cls: {k: v for k, v in rule.items() if k not in safety_fields}
            for cls, rule in result["net_class_rules"].items()
        }
        return {**result, "net_class_rules": ncr}

    assert _dicts_equal_bit_exact(
        _drop_safety_fields(py_result), _drop_safety_fields(rs_result)
    )
    ncr = rs_result["net_class_rules"]
    assert "HV" in ncr
    assert "LV" in ncr
    assert ncr["HV"]["clearance_mm"] == 8.0
    # The real values ARE present on the production (typed) path even
    # though the frozen dict kernel above never learned about them.
    assert py_result["net_class_rules"]["Signal"]["creepage_mm"] == 0.0
    assert py_result["net_class_rules"]["Signal"]["safety_category"] == "LV"


def test_build_board_dict_mechanical_ref():
    """Components with ref starting with 'MH' are flagged as mechanical."""
    positions = np.array([[5.0, 5.0]], dtype=np.float64)
    comps = [_FakeComponent(ref="MH1", footprint="MountingHole", width=3.0, height=3.0)]
    netlist = SimpleNamespace(components=comps, nets=[])
    rules: list[Any] = []
    ctx = SimpleNamespace(netlist=netlist, board=SimpleNamespace(width=100.0, height=100.0),
                          board_margin=3.0, clearance_rules=rules)
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict(positions, ctx).to_dict()
    rs_result = BUILD_BOARD_DICT(
        positions=positions, netlist=netlist, board_width=100.0, board_height=100.0,
        board_margin=3.0, clearance_rules=rules,
    )
    assert _dicts_equal_bit_exact(py_result, rs_result)
    assert rs_result["components"][0]["is_mechanical"] is True


# ---------------------------------------------------------------------------
# build_board_dict_from_parsed_pcb — differential
# ---------------------------------------------------------------------------


@dataclass
class _FakeParsedPcbComponent:
    ref: str
    footprint: str
    width: float
    height: float
    net_class: str = "Signal"
    initial_position: tuple[float, float] | None = None
    initial_rotation: int | None = None
    initial_side: int | None = None


@dataclass
class _FakeParsedPcbNet:
    name: str
    pins: list[tuple[str, str]]
    net_class: str = "Signal"


@dataclass
class _FakeNetClassRules:
    trace_width_mm: float = 0.2
    clearance_mm: float = 0.2


def test_build_board_dict_from_parsed_pcb_empty():
    """Empty parsed PCB → minimal K1 board dict."""
    pcb = SimpleNamespace(
        components=[],
        nets=[],
        board=SimpleNamespace(width=100.0, height=200.0),
        design_rules=SimpleNamespace(net_classes={}),
    )
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict_from_parsed_pcb(pcb).to_dict()
    rs_result = BUILD_BOARD_DICT_FROM_PARSED_PCB(pcb)
    assert _dicts_equal_bit_exact(py_result, rs_result)


def test_build_board_dict_from_parsed_pcb_with_components():
    """Parsed PCB components → K1 component dicts."""
    comps = [
        _FakeParsedPcbComponent(ref="C1", footprint="R_0603", width=1.6, height=0.8,
                                initial_position=(10.0, 20.0)),
        _FakeParsedPcbComponent(ref="C2", footprint="SOIC-8", width=5.0, height=6.0,
                                initial_position=None),  # defaults to (0,0)
    ]
    pcb = SimpleNamespace(
        components=comps,
        nets=[],
        board=SimpleNamespace(width=100.0, height=200.0),
        design_rules=SimpleNamespace(net_classes={}),
    )
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict_from_parsed_pcb(pcb).to_dict()
    rs_result = BUILD_BOARD_DICT_FROM_PARSED_PCB(pcb)
    assert _dicts_equal_bit_exact(py_result, rs_result)
    comps_out = rs_result["components"]
    assert len(comps_out) == 2
    assert comps_out[0]["x"] == 10.0
    assert comps_out[1]["x"] == 0.0  # default


def test_build_board_dict_from_parsed_pcb_with_nets():
    """Parsed PCB nets → K1 nets dict."""
    comps = [
        _FakeParsedPcbComponent(ref="C1", footprint="R", width=1.0, height=1.0),
        _FakeParsedPcbComponent(ref="C2", footprint="C", width=2.0, height=2.0),
    ]
    nets = [
        _FakeParsedPcbNet(name="VCC", pins=[("C1", "1"), ("C2", "1")], net_class="Power"),
    ]
    pcb = SimpleNamespace(
        components=comps,
        nets=nets,
        board=SimpleNamespace(width=100.0, height=100.0),
        design_rules=SimpleNamespace(net_classes={}),
    )
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict_from_parsed_pcb(pcb).to_dict()
    rs_result = BUILD_BOARD_DICT_FROM_PARSED_PCB(pcb)
    assert _dicts_equal_bit_exact(py_result, rs_result)
    assert set(rs_result["nets"]["VCC"]) == {"C1", "C2"}
    assert rs_result["net_classes"]["VCC"] == "Power"


def test_build_board_dict_from_parsed_pcb_with_design_rules():
    """Parsed design rules → K1 net_class_rules."""
    comps = [_FakeParsedPcbComponent(ref="C1", footprint="R", width=1.0, height=1.0)]
    pcb = SimpleNamespace(
        components=comps,
        nets=[],
        board=SimpleNamespace(width=100.0, height=100.0),
        design_rules=SimpleNamespace(net_classes={
            "HV": _FakeNetClassRules(trace_width_mm=0.5, clearance_mm=8.0),
            "Signal": _FakeNetClassRules(trace_width_mm=0.2, clearance_mm=0.2),
        }),
    )
    oracle = DRCOracle(runner=None, constraints=None, net_class_map={}, footprint_map={}, layer_map={})
    py_result = oracle._build_board_dict_from_parsed_pcb(pcb).to_dict()
    rs_result = BUILD_BOARD_DICT_FROM_PARSED_PCB(pcb)
    assert _dicts_equal_bit_exact(py_result, rs_result)
    assert rs_result["net_class_rules"]["HV"]["trace_width_mm"] == 0.5
    assert rs_result["net_class_rules"]["HV"]["clearance_mm"] == 8.0


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties
# ---------------------------------------------------------------------------


def test_prop1_constraint_value_to_plain_idempotent_on_plain():
    """P1: constraint_value_to_plain is idempotent on plain (non-model) values."""
    assert CONSTRAINT_VALUE_TO_PLAIN(CONSTRAINT_VALUE_TO_PLAIN(None)) is None
    assert CONSTRAINT_VALUE_TO_PLAIN(CONSTRAINT_VALUE_TO_PLAIN(3.14)) == 3.14
    plain = {"key": [1, 2, 3]}
    assert CONSTRAINT_VALUE_TO_PLAIN(plain) == plain


def test_prop2_constraint_value_to_plain_list_length_preserved():
    """P2: list length is preserved through conversion."""
    from hypothesis import given, settings
    from hypothesis import strategies as st
    @settings(max_examples=30, deadline=None)
    @given(st.lists(st.integers(min_value=0, max_value=100), min_size=0, max_size=20))
    def check(lst):
        result = CONSTRAINT_VALUE_TO_PLAIN(lst)
        assert len(result) == len(lst)
    check()


def test_prop3_build_board_dict_component_count_preserved():
    """P3: the number of components out equals the number in."""
    positions = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], dtype=np.float64)
    comps = [_FakeComponent(ref=f"C{i}", footprint="R", width=1.0, height=1.0) for i in range(3)]
    netlist = SimpleNamespace(components=comps, nets=[])
    result = BUILD_BOARD_DICT(positions=positions, netlist=netlist, board_width=100.0,
                              board_height=100.0, board_margin=3.0, clearance_rules=[])
    assert len(result["components"]) == 3


def test_prop4_build_constraints_dict_always_has_all_keys():
    """P4: the returned dict always contains all expected top-level keys."""
    result = BUILD_CONSTRAINTS_DICT(clearance_rules=[], constraints_config=None,
                                    board_width=100.0, board_height=100.0)
    expected_keys = {"clearances", "zones", "critical_loops", "noise_domains",
                     "isolation_barriers", "thermal_properties", "matched_length_groups",
                     "snubber_requirements", "bleed_resistor", "skin_effect_derating",
                     "hv_clearance_mm", "board_width", "board_height"}
    assert set(result.keys()) == expected_keys


def test_prop5_build_board_dict_board_dims_float():
    """P5: board dimensions are floats, not ints (Python float conversion)."""
    result = BUILD_BOARD_DICT(positions=np.zeros((0, 2)), netlist=SimpleNamespace(components=[], nets=[]),
                              board_width=100, board_height=200, board_margin=5,
                              clearance_rules=[])
    assert isinstance(result["board"]["width_mm"], float)
    assert isinstance(result["board"]["height_mm"], float)
    assert isinstance(result["board"]["margin_mm"], float)


# ---------------------------------------------------------------------------
# Metamorphic relations — three, honestly bounded
# ---------------------------------------------------------------------------


def test_mr1_constraint_value_to_plain_additive():
    """MR1: conversion result length equals input length for lists."""
    items = [1, "a", 3.14, None, True]
    result = CONSTRAINT_VALUE_TO_PLAIN(items)
    assert len(result) == len(items)
    assert result == items  # all scalars pass through


def test_mr2_build_board_dict_net_count_matches():
    """MR2: every input net produces an entry in the output nets dict."""
    comps = [_FakeComponent(ref=f"C{i}", footprint="R", width=1.0, height=1.0) for i in range(4)]
    nets = [
        _FakeNet(name=f"NET{i}", pins=[(f"C{i}", "1")], net_class="Signal")
        for i in range(3)
    ]
    netlist = SimpleNamespace(components=comps, nets=nets)
    result = BUILD_BOARD_DICT(positions=np.zeros((4, 2)), netlist=netlist,
                              board_width=100.0, board_height=100.0, board_margin=3.0,
                              clearance_rules=[])
    assert len(result["nets"]) == 3
    assert len(result["net_classes"]) == 3


def test_mr3_parsed_pcb_board_dims_match():
    """MR3: parsed PCB board dimensions are propagated to the output."""
    pcb = SimpleNamespace(
        components=[_FakeParsedPcbComponent(ref="C1", footprint="R", width=1.0, height=1.0)],
        nets=[],
        board=SimpleNamespace(width=123.45, height=67.89),
        design_rules=SimpleNamespace(net_classes={}),
    )
    result = BUILD_BOARD_DICT_FROM_PARSED_PCB(pcb)
    assert result["board"]["width_mm"] == 123.45
    assert result["board"]["height_mm"] == 67.89


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
