"""Differential test: Phase-A U5 DRC marshalling types in Rust
(temper_drc_rs.DrcBoardSnapshot / TypedConstraintSet / ConstraintValue)
vs the pinned Python marshalers (Wave-4 discipline contract G1/G2).

The three Python marshalers being migrated are:

  | Python marshaler                    | File                | Rust target            |
  |-------------------------------------|---------------------|------------------------|
  | ``_placement_to_board_dict``        | drc_runner.py       | ``DrcBoardSnapshot``   |
  | ``_constraints_to_dict``            | drc_runner.py       | ``TypedConstraintSet`` |
  | ``_constraint_value_to_plain``      | drc_oracle.py       | ``ConstraintValue``    |
  | ``DRCOracle._build_board_dict``     | drc_oracle.py       | ``DrcBoardSnapshot``   |
  | ``DRCOracle._build_constraints_dict`` | drc_oracle.py     | ``TypedConstraintSet`` |

The ``_oracle_*`` blocks below are VERBATIM copies of the pre-migration
implementations AS COMMITTED (drc_runner.py ``_placement_to_board_dict`` /
``_constraints_to_dict``, drc_oracle.py ``_constraint_value_to_plain``
pure-Python fallback body).  Do NOT edit them — they are the reference.

The Rust symbols ``_tdrc.DrcBoardSnapshot`` / ``_tdrc.TypedConstraintSet`` /
``_tdrc.ConstraintValue`` do not exist yet (RED); this file fails to
collect until the Phase-A U5 Rust implementation lands (G1 test-before-code).

Comparison convention: dicts/floats canonicalized to float.hex() strings,
so equality is bit-exact ``==`` (never tolerance).
"""

from __future__ import annotations

import pytest
import temper_drc_rs as _tdrc

# Rust symbols under test — must exist or this file fails to collect (RED).
DRC_BOARD_SNAPSHOT = _tdrc.DrcBoardSnapshot
TYPED_CONSTRAINT_SET = _tdrc.TypedConstraintSet
CONSTRAINT_VALUE = _tdrc.ConstraintValue

from pydantic import BaseModel  # noqa: E402, I001  (mid-file import block)

from temper_placer.validation.drc_types import (  # noqa: E402, I001
    ComponentPlacement,
    Placement,
)


# ---------------------------------------------------------------------------
# Oracle 1 — _placement_to_board_dict (drc_runner.py, verbatim body)
# ---------------------------------------------------------------------------


def _oracle_placement_to_board_dict(placement):
    """Pre-migration ``_placement_to_board_dict``, verbatim (drc_runner.py)."""
    components = []
    for _ref, comp in placement.components.items():
        side = "bottom" if comp.layer and "B" in (comp.layer or "") else "top"
        components.append(
            {
                "ref": comp.ref,
                "x": comp.x,
                "y": comp.y,
                "rot": comp.rotation,
                "side": side,
                "width": comp.width,
                "height": comp.height,
                "net_class": comp.net_class,
                "voltage_domain": comp.voltage_domain,
                "package_type": "smd",
                "power_dissipation_w": None,
                "is_magnetic": False,
                "is_electrolytic": False,
                "vent_direction": None,
                "footprint_polygon": None,
            }
        )

    board_dict = {
        "board": {
            "width_mm": placement.board_width,
            "height_mm": placement.board_height,
            "margin_mm": 3.0,
        },
        "components": components,
        "nets": dict(placement.nets),
        "net_classes": dict(placement.net_classes),
    }

    if placement.via_placement is not None:
        via_list = []
        for via in placement.via_placement.vias:
            via_list.append(
                {
                    "net": via.net_name,
                    "x": via.position[0],
                    "y": via.position[1],
                    "drill": via.drill,
                    "pad": via.diameter,
                    "from_layer": via.from_layer,
                    "to_layer": via.to_layer,
                }
            )
        board_dict["vias"] = via_list

    if placement.trace_placement is not None:
        seg_list = []
        for seg in placement.trace_placement.segments:
            seg_list.append(
                {
                    "net": seg.net_name,
                    "layer": seg.layer,
                    "width": seg.width,
                    "segments": [[seg.start[0], seg.start[1], seg.end[0], seg.end[1]]],
                }
            )
        board_dict["traces"] = seg_list

    return board_dict


# ---------------------------------------------------------------------------
# Oracle 2 — _constraints_to_dict (drc_runner.py, verbatim body)
# ---------------------------------------------------------------------------


def _oracle_constraints_to_dict(constraints):
    """Pre-migration ``_constraints_to_dict``, verbatim (drc_runner.py)."""
    return {
        "clearances": [
            {
                "from_class": r.from_class,
                "to_class": r.to_class,
                "clearance_mm": r.min_mm,
                "description": r.description,
            }
            for r in constraints.clearances
        ],
        "zones": [
            {
                "name": z.name,
                "net_classes": z.net_classes,
            }
            for z in constraints.zones
        ],
        "critical_loops": [
            {
                "name": l.name,
                "nets": l.nets,
                "max_area_mm2": l.max_area_mm2,
                "weight": l.weight,
            }
            for l in constraints.critical_loops
        ],
        "thermal_constraints": [
            {
                "components": t.components,
                "prefer_edge": t.prefer_edge,
                "min_spacing_mm": t.min_spacing_mm,
                "max_distance_from_edge_mm": t.max_distance_from_edge_mm,
                "description": t.description,
            }
            for t in constraints.thermal_constraints
        ],
        "hv_clearance_mm": constraints.hv_clearance_mm,
        "board_width": constraints.board_width,
        "board_height": constraints.board_height,
    }


# ---------------------------------------------------------------------------
# Oracle 3 — _constraint_value_to_plain (drc_oracle.py, verbatim
# pre-migration pure-Python body)
# ---------------------------------------------------------------------------


def _oracle_constraint_value_to_plain(value):
    """Pre-migration ``_constraint_value_to_plain``, verbatim
    (drc_oracle.py's pure-Python fallback body)."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_oracle_constraint_value_to_plain(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Canonical fixtures
# ---------------------------------------------------------------------------


def _float_hex_recursive(obj):
    """Recursively convert floats to hex strings for bit-exact comparison."""
    if isinstance(obj, float):
        return float(obj).hex()
    if isinstance(obj, dict):
        return {k: _float_hex_recursive(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_float_hex_recursive(v) for v in obj]
    return obj


def _canon_violations(violations):
    """Canonicalize run_drc violation dicts for cross-run comparison.

    `affected_items` is sorted: the DRC rules build it from a Rust
    `HashSet<&str>` (e.g. `emc::loop_area::components_on_nets`), whose
    iteration order is a per-instance `RandomState` artifact — the *set* is
    deterministic, the ordering is not. Sorting here asserts the set
    equality that the rules actually guarantee.
    """
    out = []
    for v in violations:
        v = dict(v)
        v["affected_items"] = sorted(v.get("affected_items", []))
        out.append(_float_hex_recursive(v))
    return out


def _canon_board_dict(d):
    """Canonicalize a K1 board dict: sorted keys/lists, float→hex."""
    comps = sorted(d["components"], key=lambda c: c["ref"])
    comps_canon = [
        {k: _float_hex_recursive(v) for k, v in sorted(c.items())} for c in comps
    ]
    return {
        "board": _float_hex_recursive(dict(sorted(d["board"].items()))),
        "components": comps_canon,
        "nets": {k: sorted(v) for k, v in sorted(d["nets"].items())},
        "net_classes": dict(sorted(d["net_classes"].items())),
        "net_class_rules": {
            k: _float_hex_recursive(dict(sorted(v.items())))
            for k, v in sorted(d.get("net_class_rules", {}).items())
        },
        "vias": sorted(
            [_float_hex_recursive(v) for v in d.get("vias", [])],
            key=lambda v: (v["net"], v["x"], v["y"]),
        ),
        "traces": sorted(
            [_float_hex_recursive(t) for t in d.get("traces", [])],
            key=lambda t: (t["net"], t["layer"]),
        ),
    }


def _canon_constraints_dict(d):
    """Canonicalize a constraints dict: sorted lists, float→hex."""
    return _float_hex_recursive(
        {
            "clearances": sorted(d["clearances"], key=lambda r: (r["from_class"], r["to_class"])),
            "zones": sorted(d["zones"], key=lambda z: z["name"]),
            "critical_loops": sorted(d["critical_loops"], key=lambda x: x["name"]),
            "thermal_constraints": sorted(
                d["thermal_constraints"], key=lambda t: tuple(t["components"])
            ),
            "hv_clearance_mm": d["hv_clearance_mm"],
            "board_width": d["board_width"],
            "board_height": d["board_height"],
        }
    )


def _oracle_placement() -> Placement:
    """The canonical Placement input for the board-snapshot oracle."""
    return Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="0402", x=10.0, y=10.0, rotation=0.0,
                layer="F.Cu", width=1.0, height=1.0, net_class="Signal",
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="0402", x=50.0, y=50.0, rotation=0.0,
                layer="B.Cu", width=1.0, height=1.0, net_class="Signal",
            ),
        },
        nets={"N1": ["C1", "C2"]},
        net_classes={"N1": "Signal"},
        board_width=100.0,
        board_height=100.0,
        via_placement=_tdrc.ViaPlacement(
            vias=[
                _tdrc.Via(
                    position=(5.0, 5.0), from_layer="F.Cu", to_layer="B.Cu",
                    diameter=0.6, drill=0.3, net_name="N1",
                ),
            ]
        ),
        trace_placement=_tdrc.TracePlacement(
            segments=[
                _tdrc.TraceSegment(
                    net_name="N1", layer="F.Cu", width=0.25,
                    start=(0.0, 0.0), end=(10.0, 0.0),
                ),
            ]
        ),
    )


def _oracle_constraints():
    """The canonical ConstraintSet input for the constraints oracle."""
    return _tdrc.ConstraintSet(
        clearances=[
            _tdrc.ClearanceRule(from_class="HV", to_class="LV", min_mm=6.0, description="safety"),
        ],
        zones=[
            _tdrc.ZoneDefinition(name="Z1", bounds=(0.0, 0.0, 10.0, 10.0),
                                 net_classes=["HV"], components=["Q1"]),
        ],
        critical_loops=[
            _tdrc.LoopConstraint(name="L1", nets=["N1"], max_area_mm2=100.0,
                                 weight=1.0, description=""),
        ],
        thermal_constraints=[
            _tdrc.ThermalConstraint(components=["Q1"], prefer_edge=True,
                                    min_spacing_mm=5.0,
                                    max_distance_from_edge_mm=20.0,
                                    description=""),
        ],
        component_groups=[
            _tdrc.GroupConstraint(name="G1", components=["Q1", "Q2"],
                                  max_spread_mm=25.0, zone=None,
                                  proximity_rules=[], description=""),
        ],
        net_classes={"N1": "Signal"},
        voltage_domains={},
        hv_clearance_mm=8.0,
        board_width=100.0,
        board_height=100.0,
    )


# ---------------------------------------------------------------------------
# Differential — board snapshot from_state
# ---------------------------------------------------------------------------


def test_board_snapshot_from_state_matches_oracle():
    """G1/G2: DrcBoardSnapshot.from_state(placement).to_dict() must be
    bit-identical to the pinned _placement_to_board_dict output."""
    placement = _oracle_placement()
    py_dict = _oracle_placement_to_board_dict(placement)
    snapshot = DRC_BOARD_SNAPSHOT.from_state(placement)
    assert isinstance(snapshot, _tdrc.DrcBoardSnapshot)
    assert _canon_board_dict(snapshot.to_dict()) == _canon_board_dict(py_dict)


def test_board_snapshot_from_state_empty_placement():
    """Edge: an empty placement (no components/nets) still round-trips."""
    placement = Placement(
        components={},
        nets={},
        net_classes={},
        board_width=10.0,
        board_height=20.0,
    )
    py_dict = _oracle_placement_to_board_dict(placement)
    snapshot = DRC_BOARD_SNAPSHOT.from_state(placement)
    assert _canon_board_dict(snapshot.to_dict()) == _canon_board_dict(py_dict)
    assert snapshot.to_dict()["board"]["width_mm"] == 10.0
    assert snapshot.to_dict()["board"]["margin_mm"] == 3.0


def test_board_snapshot_bottom_side_derivation():
    """The layer→side rule: any layer containing 'B' → bottom, else top."""
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="0402", x=0.0, y=0.0, rotation=0.0,
                layer="B.Cu", width=1.0, height=1.0, net_class="Signal",
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="0402", x=0.0, y=0.0, rotation=0.0,
                layer="In1.Cu", width=1.0, height=1.0, net_class="Signal",
            ),
            "C3": ComponentPlacement(
                ref="C3", footprint="0402", x=0.0, y=0.0, rotation=0.0,
                layer=None, width=1.0, height=1.0, net_class="Signal",
            ),
        },
        nets={},
        net_classes={},
    )
    py_dict = _oracle_placement_to_board_dict(placement)
    snapshot = DRC_BOARD_SNAPSHOT.from_state(placement)
    sides = {c["ref"]: c["side"] for c in snapshot.to_dict()["components"]}
    assert sides["C1"] == "bottom"
    assert sides["C2"] == "top"
    assert sides["C3"] == "top"
    assert _canon_board_dict(snapshot.to_dict()) == _canon_board_dict(py_dict)


# ---------------------------------------------------------------------------
# Differential — typed constraints from_state
# ---------------------------------------------------------------------------


def test_typed_constraints_from_state_matches_oracle():
    """G1/G2: TypedConstraintSet.from_state(constraints).to_dict() must be
    bit-identical to the pinned _constraints_to_dict output."""
    constraints = _oracle_constraints()
    py_dict = _oracle_constraints_to_dict(constraints)
    cset = TYPED_CONSTRAINT_SET.from_state(constraints)
    assert isinstance(cset, _tdrc.TypedConstraintSet)
    assert _canon_constraints_dict(cset.to_dict()) == _canon_constraints_dict(py_dict)


def test_typed_constraints_from_state_empty():
    """Edge: an empty ConstraintSet keeps the oracle's defaults."""
    constraints = _tdrc.ConstraintSet()
    py_dict = _oracle_constraints_to_dict(constraints)
    cset = TYPED_CONSTRAINT_SET.from_state(constraints)
    assert _canon_constraints_dict(cset.to_dict()) == _canon_constraints_dict(py_dict)


# ---------------------------------------------------------------------------
# Differential — constraint value to plain
# ---------------------------------------------------------------------------


def test_constraint_value_from_python_matches_oracle():
    """G1/G2: ConstraintValue.from_python(v).to_python() must equal the
    pinned _constraint_value_to_plain output on models, lists, scalars."""
    from temper_placer._constraint_types import IsolationBarrier

    cases = [
        None,
        True,
        3.14,
        42,
        "hello",
        [1, 2.5, "x", None],
        IsolationBarrier(
            name="B1", x_mm=1.0, y_span=(0.0, 10.0),
            points=[[1.0, 0.0], [1.0, 10.0]], layers="all", clearance_mm=1.0,
        ),
        [
            IsolationBarrier(name="B1", x_mm=1.0, y_span=(0.0, 10.0), points=[], layers="all", clearance_mm=1.0),
            IsolationBarrier(name="B2", x_mm=2.0, y_span=(10.0, 20.0), points=[], layers="all", clearance_mm=2.0),
        ],
        {"nested": [IsolationBarrier(name="B3", x_mm=3.0, y_span=(0.0, 1.0), points=[], layers="all", clearance_mm=3.0)]},
    ]
    for v in cases:
        py_result = _oracle_constraint_value_to_plain(v)
        rust_result = CONSTRAINT_VALUE.from_python(v).to_python()
        assert _float_hex_recursive(rust_result) == _float_hex_recursive(py_result)


# ---------------------------------------------------------------------------
# Differential — placer path: from_netlist / from_parsed_pcb / from_context
#
# The placer-path marshalers were already migrated to the Rust K1-dict
# kernels build_board_dict_py / build_board_dict_from_parsed_pcb_py /
# build_constraints_dict_py (validated against the pinned DRCOracle oracle
# by test_drc_oracle_marshal_rust_differential.py). These tests chain the
# new typed constructors against those validated kernels, so the oracle
# chain is: pinned Python oracle -> validated dict kernel -> typed snapshot.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402, I001  (mid-file import block)
from dataclasses import dataclass  # noqa: E402, I001

import numpy as np  # noqa: E402

from temper_placer.core.design_rules import TEMPER_NET_CLASSES  # noqa: E402, I001


@dataclass
class _FakeClearanceRule:
    net_class_a: str
    net_class_b: str
    min_clearance: float
    because: str = ""


@dataclass
class _FakeComp:
    ref: str
    footprint: str
    width: float
    height: float
    net_class: str
    initial_rotation_quadrant: int | None = None
    initial_side: int | None = None


@dataclass
class _FakeNet:
    name: str
    net_class: str
    pins: list  # list of (ref, pin_number)


def _placer_context(clearance_rules=None, constraints_config=None, width=152.0, height=234.0):
    return SimpleNamespace(
        clearance_rules=clearance_rules or [],
        board=SimpleNamespace(width=width, height=height),
        board_margin=3.0,
        constraints_config=constraints_config,
    )


def test_board_snapshot_from_netlist_matches_validated_kernel():
    """DrcBoardSnapshot.from_netlist(...).to_dict() must reproduce the
    validated build_board_dict_py K1 dict bit-exactly."""
    rng = np.random.default_rng(7)
    positions = rng.uniform(0.0, 100.0, (3, 2))
    comps = [
        _FakeComp("C1", "R_0603", 1.0, 0.5, "Signal", initial_rotation_quadrant=2),
        _FakeComp("C2", "TO-247", 5.0, 4.0, "HV", initial_side=1),
        _FakeComp("MH1", "MountingHole", 3.0, 3.0, "GND"),
    ]
    nets = [
        _FakeNet("N1", "Signal", [("C1", 1), ("C2", 1)]),
        _FakeNet("N2", "HV", [("C2", 2), ("C1", 2)]),
    ]
    netlist = SimpleNamespace(components=comps, nets=nets)
    rules = [_FakeClearanceRule("HV", "Signal", 8.0, "safety")]
    kwargs = {
        "positions": positions,
        "netlist": netlist,
        "board_width": 152.0,
        "board_height": 234.0,
        "board_margin": 3.0,
        "clearance_rules": rules,
    }
    dict_result = _tdrc.build_board_dict_py(**kwargs)
    snapshot = DRC_BOARD_SNAPSHOT.from_netlist(**kwargs)
    assert _canon_board_dict(snapshot.to_dict()) == _canon_board_dict(dict_result)
    sides = {c["ref"]: c["side"] for c in snapshot.to_dict()["components"]}
    assert sides["C2"] == "bottom"
    assert sides["C1"] == "top"
    pkg = {c["ref"]: c["package_type"] for c in snapshot.to_dict()["components"]}
    assert pkg["C2"] == "to247"
    assert pkg["C1"] == "smd"
    mech = {c["ref"]: c["is_mechanical"] for c in snapshot.to_dict()["components"]}
    assert mech["MH1"] is True
    assert mech["C1"] is False


def test_board_snapshot_from_netlist_uses_real_per_class_trace_width():
    """Regression (2026-08-11): `from_netlist` hardcoded
    `trace_width_mm: 0.2` for EVERY net class referenced in
    `clearance_rules`, regardless of the class's real width. This was an
    accidental no-op before #1041/#1042 wired real net classification into
    the Rust parser -- every net resolved to "Signal", whose real width IS
    0.2mm -- but is live and wrong now that GND (1.0mm), HighVoltage
    (3.0mm), etc. are real per-net classes on the board (69 Signal, 14
    HighVoltage, 2 GND, ...). Passing `net_class_defs=TEMPER_NET_CLASSES`
    (the project's own netclass SSOT, `core/design_rules.py`) must produce
    GND's REAL 1.0mm trace width, not the old flat 0.2mm. A pre-fix
    `from_netlist` (hardcoded 0.2 regardless of `net_class_defs`) fails
    this test."""
    positions = np.zeros((1, 2), dtype=np.float64)
    comps = [_FakeComp("C1", "R_0603", 1.0, 0.5, "GND")]
    nets = [_FakeNet("gnd", "GND", [("C1", 1)])]
    netlist = SimpleNamespace(components=comps, nets=nets)
    rules = [_FakeClearanceRule("GND", "Signal", 0.3, "ground return")]

    snapshot = DRC_BOARD_SNAPSHOT.from_netlist(
        positions=positions,
        netlist=netlist,
        board_width=100.0,
        board_height=100.0,
        board_margin=3.0,
        clearance_rules=rules,
        net_class_defs=TEMPER_NET_CLASSES,
    )
    gnd_rule = snapshot.to_dict()["net_class_rules"]["GND"]
    assert gnd_rule["trace_width_mm"] == 1.0, (
        f"GND's real trace width is 1.0mm (TEMPER_NET_CLASSES); got "
        f"{gnd_rule['trace_width_mm']}mm -- the pre-fix hardcode."
    )
    # clearance_mm is sourced from clearance_rules (a separate, already-
    # correct dimension) and must be unaffected by this fix.
    assert gnd_rule["clearance_mm"] == 0.3


def test_board_snapshot_from_netlist_omitting_net_class_defs_keeps_legacy_default():
    """Without `net_class_defs` (legacy callers -- e.g. this file's own
    `test_board_snapshot_from_netlist_matches_validated_kernel` above,
    which pins bit-exactness against `build_board_dict_py`, a frozen
    migration artifact that never learned about real per-class widths),
    the historical flat-0.2mm fallback is preserved exactly. This is what
    keeps that differential test passing unmodified."""
    positions = np.zeros((1, 2), dtype=np.float64)
    comps = [_FakeComp("C1", "R_0603", 1.0, 0.5, "GND")]
    nets = [_FakeNet("gnd", "GND", [("C1", 1)])]
    netlist = SimpleNamespace(components=comps, nets=nets)
    rules = [_FakeClearanceRule("GND", "Signal", 0.3, "ground return")]

    snapshot = DRC_BOARD_SNAPSHOT.from_netlist(
        positions=positions,
        netlist=netlist,
        board_width=100.0,
        board_height=100.0,
        board_margin=3.0,
        clearance_rules=rules,
    )
    assert snapshot.to_dict()["net_class_rules"]["GND"]["trace_width_mm"] == 0.2


def test_board_snapshot_from_netlist_populates_real_safety_fields():
    """Regression (2026-08-11): `from_netlist` (and `from_parsed_pcb`)
    hardcoded `creepage_mm`, `voltage_v`, `max_current_rating`,
    `safety_category`, `required_layer`, and `routing_strategy` to `None`
    for EVERY net class -- a pre-existing gap sibling to the
    `trace_width_mm` hardcode fixed by #1045 (which reported this gap
    rather than fixing it). This was harmless before real net
    classification landed (#1041/#1042, every net resolved to "Signal")
    but is a live safety-argument gap now that HighVoltage
    (creepage_mm=6.0, safety_category="HV") is a real per-net class on a
    board whose entire mains<->SELV isolation argument rests on an 8.0mm
    creepage bar. Passing `net_class_defs=TEMPER_NET_CLASSES` must produce
    HighVoltage's REAL values, not `None`. A pre-fix `from_netlist`
    (hardcoded `None` regardless of `net_class_defs`) fails this test."""
    positions = np.zeros((1, 2), dtype=np.float64)
    comps = [_FakeComp("Q1", "TO-247", 5.0, 4.0, "HighVoltage")]
    nets = [_FakeNet("hv1", "HighVoltage", [("Q1", 1)])]
    netlist = SimpleNamespace(components=comps, nets=nets)
    rules = [_FakeClearanceRule("HighVoltage", "Signal", 8.0, "mains-SELV barrier")]

    snapshot = DRC_BOARD_SNAPSHOT.from_netlist(
        positions=positions,
        netlist=netlist,
        board_width=100.0,
        board_height=100.0,
        board_margin=3.0,
        clearance_rules=rules,
        net_class_defs=TEMPER_NET_CLASSES,
    )
    hv_rule = snapshot.to_dict()["net_class_rules"]["HighVoltage"]
    assert hv_rule["creepage_mm"] == 6.0, (
        f"HighVoltage's real creepage_mm is 6.0 (TEMPER_NET_CLASSES); got "
        f"{hv_rule['creepage_mm']!r} -- the pre-fix None hardcode."
    )
    assert hv_rule["safety_category"] == "HV", (
        f"HighVoltage's real safety_category is 'HV'; got "
        f"{hv_rule['safety_category']!r} -- the pre-fix None hardcode."
    )
    assert hv_rule["voltage_v"] == 400.0
    assert hv_rule["required_layer"] == "B.Cu"
    assert hv_rule["routing_strategy"] == "plane_required"


def test_board_snapshot_from_netlist_omitting_net_class_defs_keeps_safety_fields_none():
    """Without `net_class_defs` (legacy callers), the six safety fields
    stay `None` exactly as before -- this fix must not change behavior for
    callers that don't supply the SSOT mapping (e.g. this file's own
    bit-exactness tests against the frozen dict kernels)."""
    positions = np.zeros((1, 2), dtype=np.float64)
    comps = [_FakeComp("Q1", "TO-247", 5.0, 4.0, "HighVoltage")]
    nets = [_FakeNet("hv1", "HighVoltage", [("Q1", 1)])]
    netlist = SimpleNamespace(components=comps, nets=nets)
    rules = [_FakeClearanceRule("HighVoltage", "Signal", 8.0, "mains-SELV barrier")]

    snapshot = DRC_BOARD_SNAPSHOT.from_netlist(
        positions=positions,
        netlist=netlist,
        board_width=100.0,
        board_height=100.0,
        board_margin=3.0,
        clearance_rules=rules,
    )
    hv_rule = snapshot.to_dict()["net_class_rules"]["HighVoltage"]
    assert hv_rule["creepage_mm"] is None
    assert hv_rule["safety_category"] is None
    assert hv_rule["voltage_v"] is None
    assert hv_rule["max_current_rating"] is None
    assert hv_rule["required_layer"] is None
    assert hv_rule["routing_strategy"] is None


@dataclass
class _FakeParsedComponent:
    ref: str
    footprint: str
    width: float
    height: float
    net_class: str
    initial_position: tuple | None = (1.0, 2.0)
    initial_rotation_quadrant: int | None = None
    initial_side: int | None = None


@dataclass
class _FakeParsedNet:
    name: str
    net_class: str
    pins: list


@dataclass
class _FakeRules:
    trace_width_mm: float
    clearance_mm: float


def test_board_snapshot_from_parsed_pcb_matches_validated_kernel():
    """DrcBoardSnapshot.from_parsed_pcb(...).to_dict() must reproduce the
    validated build_board_dict_from_parsed_pcb_py K1 dict bit-exactly."""
    parsed = SimpleNamespace(
        components=[
            _FakeParsedComponent("Q1", "TO-220", 4.0, 3.0, "HV", initial_rotation_quadrant=1),
            _FakeParsedComponent("R1", "R_0603", 1.0, 0.5, "Signal", initial_position=None),
        ],
        nets=[
            _FakeParsedNet("N1", "HV", [("Q1", 1), ("R1", 1)]),
        ],
        design_rules=SimpleNamespace(
            net_classes={"HV": _FakeRules(1.2, 6.0), "Signal": _FakeRules(0.2, 0.2)}
        ),
        board=SimpleNamespace(width=100.0, height=80.0),
    )
    dict_result = _tdrc.build_board_dict_from_parsed_pcb_py(parsed)
    snapshot = DRC_BOARD_SNAPSHOT.from_parsed_pcb(parsed)
    assert _canon_board_dict(snapshot.to_dict()) == _canon_board_dict(dict_result)
    assert snapshot.to_dict()["board"]["margin_mm"] == 3.0


@dataclass
class _FakeRulesWithSafety:
    trace_width_mm: float
    clearance_mm: float
    creepage_mm: float | None = None
    voltage_v: float | None = None
    max_current_rating: float | None = None
    safety_category: str | None = None
    required_layer: str | None = None
    routing_strategy: str | None = None


def test_board_snapshot_from_parsed_pcb_populates_real_safety_fields():
    """`from_parsed_pcb` sibling of the `from_netlist` regression above:
    the same six safety fields were hardcoded to `None` regardless of what
    `design_rules.net_classes[class_name]` actually carried. Reads them
    for real when present on the rules object."""
    parsed = SimpleNamespace(
        components=[_FakeParsedComponent("Q1", "TO-220", 4.0, 3.0, "HV", initial_rotation_quadrant=1)],
        nets=[_FakeParsedNet("N1", "HV", [("Q1", 1)])],
        design_rules=SimpleNamespace(
            net_classes={
                "HV": _FakeRulesWithSafety(
                    1.2,
                    6.0,
                    creepage_mm=6.0,
                    voltage_v=400.0,
                    safety_category="HV",
                    required_layer="B.Cu",
                    routing_strategy="plane_required",
                ),
            }
        ),
        board=SimpleNamespace(width=100.0, height=80.0),
    )
    snapshot = DRC_BOARD_SNAPSHOT.from_parsed_pcb(parsed)
    hv_rule = snapshot.to_dict()["net_class_rules"]["HV"]
    assert hv_rule["creepage_mm"] == 6.0, (
        f"got {hv_rule['creepage_mm']!r} -- the pre-fix None hardcode."
    )
    assert hv_rule["safety_category"] == "HV", (
        f"got {hv_rule['safety_category']!r} -- the pre-fix None hardcode."
    )
    assert hv_rule["voltage_v"] == 400.0
    assert hv_rule["required_layer"] == "B.Cu"
    assert hv_rule["routing_strategy"] == "plane_required"


def test_typed_constraints_from_context_matches_validated_kernel():
    """TypedConstraintSet.from_context(...).to_dict() must reproduce the
    validated build_constraints_dict_py dict bit-exactly (config values
    converted through the model_dump(mode='json') plain path)."""
    from temper_placer._constraint_types import IsolationBarrier

    rules = [_FakeClearanceRule("HV", "LV", 8.0, "safety")]
    barrier = IsolationBarrier(
        name="IB1", x_mm=50.0, y_span=(0.0, 100.0),
        points=[[50.0, 0.0], [50.0, 100.0]], layers="all", clearance_mm=8.0,
    )
    config = SimpleNamespace(
        isolation_barriers=[barrier],
        zones=None, critical_loops=None, noise_domains=None,
        thermal_properties=None, matched_length_groups=None,
        snubber_requirements=None, bleed_resistor=None,
        skin_effect_derating=None,
    )
    kwargs = {
        "clearance_rules": rules,
        "constraints_config": config,
        "board_width": 152.0,
        "board_height": 234.0,
    }
    dict_result = _tdrc.build_constraints_dict_py(**kwargs)
    cset = TYPED_CONSTRAINT_SET.from_context(**kwargs)
    # The typed union dict carries `thermal_constraints` (the engine's
    # documented default for the field) which build_constraints_dict_py
    # never emitted; drop it for the bit-exact comparison.
    typed_dict = {k: v for k, v in cset.to_dict().items() if k != "thermal_constraints"}
    assert _float_hex_recursive(typed_dict) == _float_hex_recursive(dict_result)
    assert cset.to_dict()["isolation_barriers"][0]["name"] == "IB1"


# ---------------------------------------------------------------------------
# Kernel-path equivalence — typed structs vs the dict wire format (G2)
# ---------------------------------------------------------------------------


def test_run_drc_typed_matches_dict_path():
    """The typed path (DrcBoardSnapshot + TypedConstraintSet straight into
    run_drc) must produce byte-identical violation dicts to the dict wire
    format the same data round-trips through today."""
    placement = _oracle_placement()
    constraints = _oracle_constraints()
    snapshot = DRC_BOARD_SNAPSHOT.from_state(placement)
    cset = TYPED_CONSTRAINT_SET.from_state(constraints)
    typed_violations = _tdrc.run_drc(snapshot, cset)
    dict_violations = _tdrc.run_drc(
        _oracle_placement_to_board_dict(placement),
        _oracle_constraints_to_dict(constraints),
    )
    assert _canon_violations(typed_violations) == _canon_violations(dict_violations)


def test_run_drc_typed_categories_filter_matches_dict_path():
    """Category filtering behaves identically on the typed path."""
    placement = _oracle_placement()
    constraints = _oracle_constraints()
    snapshot = DRC_BOARD_SNAPSHOT.from_state(placement)
    cset = TYPED_CONSTRAINT_SET.from_state(constraints)
    typed = _tdrc.run_drc(snapshot, cset, categories=["drc"])
    dicted = _tdrc.run_drc(
        _oracle_placement_to_board_dict(placement),
        _oracle_constraints_to_dict(constraints),
        categories=["drc"],
    )
    assert _canon_violations(typed) == _canon_violations(dicted)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
