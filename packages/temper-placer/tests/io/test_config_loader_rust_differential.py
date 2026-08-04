"""Differential test: Rust config loader (temper_design_bundle_python) vs the
pinned Python oracle.

Wave 4, Phase 3, candidate 5 — the config/reference loaders migration (plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``, candidate
5). The config loader is the pydantic boundary crux: PyYAML
(``yaml.safe_load``) and pydantic (``PlacementConstraints.model_validate``)
stay on the Python side and are called back across the boundary — pydantic is
**not** reimplemented in Rust. Everything downstream of the YAML parse —
field mapping, default evaluation order, coercion order, dict iteration
order, the eager typed-construction error timing — is Rust.

The Rust ``preprocess_config`` / ``load_constraints`` / ``infer_rjc`` /
``create_board_from_constraints`` / ``constraints_to_design_rules`` /
``apply_zones_to_netlist`` / ``apply_fixed_components_to_netlist`` symbols
(in ``temper_design_bundle_python``, from the ``temper-design-bundle``
crate) must reproduce the pre-migration implementation of
``temper_placer/io/config_loader.py`` bit-identically, pinned verbatim as
the oracle (``_config_loader_py_oracle.py``, commit 79ab9bd0e).

Comparison convention (mirrors the landed contract differentials): floats are
compared as exact bit patterns via ``float.hex()``, dicts as sorted items
(insertion order is not part of the parity contract for the pydantic model),
and every leaf carries its concrete ``type`` so ``int``-vs-``float`` cannot
hide behind numeric equality. ``repr()`` is CPython-exact for the typed
objects both arms produce (Zone, NetGraph, pydantic models), so
``(type.__name__, repr(value))`` is a sound canonical form for them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import temper_design_bundle_python as _tdb

import tests.io._config_loader_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
PRECONFIG = _tdb.preprocess_config
LOAD_CONSTRAINTS = _tdb.load_constraints
INFER_RJC = _tdb.infer_rjc
CREATE_BOARD = _tdb.create_board_from_constraints
TO_DESIGN_RULES = _tdb.constraints_to_design_rules
APPLY_ZONES = _tdb.apply_zones_to_netlist
APPLY_FIXED = _tdb.apply_fixed_components_to_netlist

CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"
PRODUCTION_CONFIG = CONFIGS_DIR / "temper_constraints.yaml"

# A synthetic but VALID config exercising the full load_constraints chain
# (kept in sync with the preprocess dict test above where they overlap).
_SYNTHETIC_CONFIG_YAML = """
board:
  width_mm: 120.5
  height_mm: 80.25
  margin_mm: 2.5
  keepouts: [[1.0, 2.0, 3.0, 4.0], [0.5, 0.5, 5.5, 5.5]]
zones:
  - name: HV
    bounds_ratio: [0.0, 0.0, 0.5, 0.5]
    net_classes: [HighVoltage]
  - name: LV
    bounds: [10.0, 20.0, 30.0, 40.0]
    max_size: [5.0, 5.0]
copper_zones:
  - name: GND_POUR
    bounds: [0.0, 0.0, 100.0, 100.0]
    layers: [B.Cu, F.Cu]
ground_domains:
  - name: PGND
    bounds: [0.0, 0.0, 50.0, 50.0]
    star_point: [25.0, 25.0]
constraints:
  - type: adjacent
    a: Q1
    b: Q2
    max_distance_mm: 10.5
    tier: 1
    because: Test constraint
net_assignments:
  Power: [VIN, VOUT]
  GND: [GND, PGND]
feedback:
  max_iterations: 7
  violation_threshold: 3
  expansion_per_violation: 0.75
clearances:
  - from: HV
    to: LV
    clearance_mm: 6.0
    description: isolation
hv_clearance_mm: 8.0
critical_loops:
  - name: commutation
    nets: [PH_A, PH_B]
    pins: [[Q1.1, Q2.1]]
    max_area_mm2: 1500.0
    weight: 2.0
critical_paths:
  gate_h:
    from: U7
    to: Q1
    pins: [U7.3, Q1.1]
    max_length_mm: 30.0
    priority: high
matched_length_groups:
  DDR:
    tolerance_mm: 0.5
noise_isolation:
  iso1:
    sensitive_components: [U1]
    noise_sources: [Q1]
    min_distance_mm: 12.0
star_grounds:
  - net: PGND
    weight: 3.0
    anchor: [10.0, 10.0]
    description: main
thermal:
  - components: [Q1]
    min_spacing_mm: 8.0
    prefer_edge: false
thermal_properties:
  high_power:
    components: [Q1]
    power_dissipation_w: {Q1: 25.0}
    min_separation_mm: 12.0
  heat_sensitive:
    components: [U1]
    max_temp_rise_c: 15.0
  thermal_pads:
    components: [Q1]
    prefer_edge: false
groups:
  - name: power
    components: [Q1, Q2]
    max_spread_mm: 20.0
    zone: HV
    weight: 2.0
    stacked_layout: true
    proximity:
      - pair: [Q1, Q2]
        max_distance_mm: 5.0
        tier: hard
component_groups:
  - name: leader_follower
    leader: U1
    followers: [U2, U3]
    max_distance: 15.0
group_separation:
  - groups: [HV, LV]
    min_distance_mm: 10.0
minimum_spacing:
  - components: [C1, C2]
    min_separation_mm: 1.0
manufacturing_constraints:
  - components: [Q1]
    allowed_orientations: [0, 90]
    side: top
    because: heatsink
fixed_components:
  C1: {x: 1.5, y: 2.5}
  C2: {x: 3.0, y: 4.0}
fixed_positions:
  C4: [10.0, 20.0]
zone_assignments:
  R1: HV
net_classes:
  VIN: Power
net_class_rules:
  Power:
    trace_width_mm: 1.5
    clearance_mm: 0.5
    via_size_mm: 1.0
    via_drill_mm: 0.6
    creepage_mm: 2.0
    max_current_rating: 15.0
    routing_strategy: pour
  Signal:
    allow_neckdown: false
net_priority:
  NET1: 1
differential_pairs:
  - positive_net: D_P
    negative_net: D_N
    separation_mm: 0.4
    target_impedance_ohm: 100.0
    max_skew_mm: 0.2
net_topology:
  NET_I_SENSE:
    star_nodes: [R1.1]
    edges:
      - source: R1.1
        sink: U1.2
        width: 0.5
        clearance: 0.3
        priority: 5
kelvin_sensing:
  - net_name: SENSE
    star_point_pin: R1.1
    force_pins: [U1.1]
    sense_pins: [U1.2]
    force_width_mm: 1.2
    sense_width_mm: 0.3
aesthetics:
  grid_size_mm: 1.0
  align_by_prefix: false
  prefix_exceptions: [Q]
  max_wirelength_tax: 3.0
manufacturing:
  target_margin_mm: 0.15
  etch_tolerance_mm: 0.03
losses:
  overlap: {weight: 2.0, enabled: false}
  boundary: 1.5
escape_clearances:
  - component: Q1
    clearance_mm: 5.0
    priority_sides: [right]
    tier: hard
routing_corridors:
  - name: gate
    from_component: U7
    to_component: Q1
    width_mm: 3.0
signal_hv_clearances:
  - name: gate_hv
    signal_component: U7
    signal_pin: 3
    target_component: Q1
    target_pin: "1"
    hv_component: Q1
    hv_pins: [2, "3"]
    required_clearance_mm: 8.0
placement_proximity:
  - name: prox1
    from_component: U1
    from_pin: 1
    to_component: U2
    to_pin: "2"
    max_distance_mm: 12.0
hv_exclusion_zones:
  - name: q1_hv_zone
    center: [50.0, 50.0]
    size: [10.0, 10.0]
    clearance_mm: 7.0
isolation_slots:
  - name: slot1
    component_ref: Q1
    start_offset: [1.0, 1.0]
    end_offset: [5.0, 5.0]
    width_mm: 2.0
noise_domains:
  - emitters: [Q1]
    victims: [U1]
    max_parallel_run_mm: 8.0
isolation_barriers:
  - name: bar1
    x_mm: 10.0
    y_span: [0.0, 100.0]
    layers: [B.Cu]
snubber_requirements:
  - igbt_pair: [Q1, Q2]
    type: RC
bleed_resistor:
  bus_voltage_v: 400.0
  target_voltage_v: 200.0
  timeout_s: 3.0
skin_effect_derating:
  frequency_hz: 100000.0
  derating_factor: 2.0
slot_generation:
  enabled: true
placement_priority:
  phases: []
routing_priority:
  phases: []
placer:
  iterations: 100
seed_filter:
  enabled: false
  threshold: 0.9
  hv_threshold: 0.6
"""


# ---------------------------------------------------------------------------
# Canonicalization helpers.
# ---------------------------------------------------------------------------


def canon(value):
    """Recursive canonical key: bit-exact floats, sorted dicts, concrete leaf
    types, typed objects via (type name, CPython repr)."""
    import numpy as np

    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, int) and not isinstance(value, bool):
        return ("int", value)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, str):
        return ("str", value)
    if value is None:
        return ("none",)
    if isinstance(value, dict):
        return ("dict", tuple(sorted((k, canon(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(canon(v) for v in value))
    if isinstance(value, (set, frozenset)):
        return (type(value).__name__, tuple(sorted(canon(v) for v in value)))
    if isinstance(value, np.ndarray):
        return ("ndarray", value.dtype.str, value.shape, value.tobytes())
    # pydantic models: canonicalize structurally via model_dump (their repr is
    # exact for the declared fields, but any field holding an arbitrary object
    # — e.g. net_classification — embeds that object's memory address).
    if hasattr(value, "model_dump") and not type(value).__name__ == "NetClassification":
        return (
            type(value).__name__,
            canon(value.model_dump(mode="python")),
        )
    # NetClassification is a Rust pyclass whose repr embeds the instance
    # memory address — each arm builds its own instance, so the repr is
    # nondeterministic. Canonicalize by value instead.
    if type(value).__name__ == "NetClassification":
        return (
            "NetClassification",
            tuple(
                sorted(
                    (name, repr(spec)) for name, spec in value.specs.items()
                )
            ),
            tuple(sorted(value.ground_patterns)),
            tuple(sorted(value.power_patterns)),
            tuple(sorted(value.hv_patterns)),
        )
    # Typed object (Zone, NetGraph, pydantic model, ...): CPython repr is
    # exact for the objects both arms produce (same construction path), and
    # the type name catches int-vs-float repr ambiguity classes.
    return (type(value).__name__, repr(value))


def canon_call(fn, *args, **kwargs):
    """Run fn, returning either ('ok', canon(value)) or ('err', type, message)."""
    try:
        return ("ok", canon(fn(*args, **kwargs)))
    except Exception as e:  # noqa: BLE001 - parity comparison must capture all
        return ("err", type(e).__name__, str(e))


def _raw_config(path: Path):
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# preprocess_config parity (R1a — the transform surface).
# ---------------------------------------------------------------------------


def test_preprocess_matches_oracle_on_production_fixture():
    raw = _raw_config(PRODUCTION_CONFIG)
    assert canon_call(PRECONFIG, raw) == canon_call(_oracle._preprocess_config, raw)


def test_preprocess_matches_oracle_on_minimal_empty():
    for raw in ({}, {"board": {}}, {"zones": []}, {"net_classes": {}}):
        assert canon_call(PRECONFIG, raw) == canon_call(_oracle._preprocess_config, raw)


def test_preprocess_matches_oracle_on_synthetic_full_config():
    raw = {
        "board": {"width_mm": 120.5, "height_mm": 80.25, "margin_mm": 2.5,
                  "keepouts": [[1.0, 2.0, 3.0, 4.0], (0.5, 0.5, 5.5, 5.5)]},
        "zones": [
            {"name": "HV", "bounds_ratio": [0.0, 0.0, 0.5, 0.5],
             "net_classes": ["HighVoltage"], "type": "keepout"},
            {"name": "LV", "bounds": [10, 20, 30, 40], "max_size": [5, 5]},
        ],
        "copper_zones": [
            {"name": "GND_POUR", "bounds": [0, 0, 100, 100], "layers": ["B.Cu", "F.Cu"]},
        ],
        "ground_domains": [
            {"name": "PGND", "bounds": [0, 0, 50, 50], "star_point": [25, 25]},
            {"name": "AGND", "bounds": [50, 0, 100, 50]},
        ],
        "constraints": [
            {"type": "adjacent", "a": "Q1", "b": "Q2", "max_distance_mm": 10.5,
             "tier": 1, "because": "Test constraint"},
        ],
        "net_assignments": {"Power": ["VIN", "VOUT"], "GND": ["GND", "PGND"]},
        "feedback": {"max_iterations": 7, "violation_threshold": 3,
                     "expansion_per_violation": 0.75},
        "clearances": [
            {"from": "HV", "to": "LV", "clearance_mm": 6.0, "description": "iso"},
            {"from": "LV", "to": "GND", "clearance_mm": 0.3},
        ],
        "hv_clearance_mm": 8.0,
        "critical_loops": [
            {"name": "commutation", "nets": ["PH_A", "PH_B"], "pins": [["Q1.1", "Q2.1"]],
             "max_area_mm2": 1500.0, "weight": 2.0},
            {"name": "minimal", "nets": ["N1"]},
        ],
        "critical_paths": {
            "gate_h": {"from": "U7", "to": "Q1", "pins": ["U7.3", "Q1.1"],
                       "max_length_mm": 30.0, "priority": "high"},
            "bare": {"from": "U1", "to": "U2"},
        },
        "matched_length_groups": {"DDR": {"tolerance_mm": 0.5}},
        "noise_isolation": {
            "iso1": {"sensitive_components": ["U1"], "noise_sources": ["Q1"], "min_distance_mm": 12.0},
        },
        "star_grounds": [
            {"net": "PGND", "weight": 3.0, "anchor": [10, 10], "description": "main"},
            {"net": "AGND"},
        ],
        "thermal": [
            {"components": ["Q1"], "min_spacing_mm": 8.0, "prefer_edge": False},
            {"components": ["U1"], "min_separation_mm": 6.0},
        ],
        "thermal_properties": {
            "high_power": {"components": ["Q1"], "power_dissipation_w": {"Q1": 25.0},
                           "min_separation_mm": 12.0},
            "heat_sensitive": {"components": ["U1"], "max_temp_rise_c": 15.0},
            "thermal_pads": {"components": ["Q1"], "prefer_edge": False},
        },
        "groups": [
            {"name": "power", "components": ["Q1", "Q2"], "max_spread_mm": 20.0,
             "zone": "HV", "weight": 2.0, "template_group": "tg", "primary_pin": "Q1.1",
             "stacked_layout": True,
             "proximity": [{"pair": ["Q1", "Q2"], "max_distance_mm": 5.0, "tier": "hard"}]},
        ],
        "component_groups": [
            {"name": "leader_follower", "leader": "U1", "followers": ["U2", "U3"],
             "max_distance": 15.0},
        ],
        "group_separation": [
            {"groups": ["HV", "LV"], "min_distance_mm": 10.0},
            {"groups": ["A"]},  # too few — skipped
        ],
        "minimum_spacing": [
            {"components": ["C1", "C2"], "min_separation_mm": 1.0},
            {"components": ["X"]},  # too few — skipped
        ],
        "manufacturing_constraints": [
            {"components": ["Q1"], "allowed_orientations": [0, 90], "side": "top", "because": "h"},
        ],
        "fixed_components": {"C1": {"x": 1.5, "y": 2.5}, "C2": {"x": 3.0, "y": 4.0}, "C3": {}},
        "fixed_positions": {"C4": [10.0, 20.0], "C5": {"x": 1, "y": 2}, "C6": [1]},
        "zone_assignments": {"R1": "HV"},
        "net_classes": {"VIN": "Power"},
        "net_class_rules": {
            "Power": {"trace_width_mm": 1.5, "clearance_mm": 0.5, "via_size_mm": 1.0,
                      "via_drill_mm": 0.6, "creepage_mm": 2.0, "max_current_rating": 15.0,
                      "routing_strategy": "pour", "via_cost_multiplier": 0.8,
                      "target_impedance": 50.0, "voltage_v": 400.0},
            "Signal": {"allow_neckdown": False, "description": "sig"},
            "Minimal": {},
        },
        "net_priority": {"NET1": 1, 2: 3},
        "differential_pairs": [
            {"positive_net": "D_P", "negative_net": "D_N", "separation_mm": 0.4,
             "target_impedance_ohm": 100.0, "max_skew_mm": 0.2},
            {"net_pos": "A_P", "net_neg": "A_N", "spacing_mm": 0.5},
            {"positive_net": "X"},  # missing neg — skipped
        ],
        "net_topology": {
            "NET_I_SENSE": {"star_nodes": ["R1.1"], "edges": [{"source": "R1.1", "sink": "U1.2",
                                                               "width": 0.5, "clearance": 0.3,
                                                               "priority": 5}]},
        },
        "kelvin_sensing": [
            {"net_name": "SENSE", "star_point_pin": "R1.1", "force_pins": ["U1.1"],
             "sense_pins": ["U1.2", "U1.3"], "force_width_mm": 1.2, "sense_width_mm": 0.3},
        ],
        "aesthetics": {"grid_size_mm": 1.0, "align_by_prefix": False,
                       "prefix_exceptions": ["Q"], "max_wirelength_tax": 3.0},
        "manufacturing": {"target_margin_mm": 0.15, "etch_tolerance_mm": 0.03},
        "losses": {
            "overlap": {"weight": 2.0, "enabled": False},
            "boundary": 1.5,
            "thermal": None,
        },
        "escape_clearances": [
            {"component": "Q1", "clearance_mm": 5.0, "priority_sides": ["right"], "tier": "hard"},
        ],
        "routing_corridors": [
            {"name": "gate", "from_component": "U7", "to_component": "Q1", "width_mm": 3.0},
        ],
        "signal_hv_clearances": [
            {"name": "gate_hv", "signal_component": "U7", "signal_pin": 3,
             "target_component": "Q1", "target_pin": "1", "hv_component": "Q1",
             "hv_pins": [2, "3"], "required_clearance_mm": 8.0},
        ],
        "placement_proximity": [
            {"name": "prox1", "from_component": "U1", "from_pin": 1,
             "to_component": "U2", "to_pin": "2", "max_distance_mm": 12.0},
        ],
        "hv_exclusion_zones": [
            {"name": "q1_hv_zone", "center": [50.0, 50.0], "size": [10.0, 10.0],
             "clearance_mm": 7.0, "excluded_nets": ["NET1"]},
        ],
        "isolation_slots": [
            {"name": "slot1", "component_ref": "Q1", "start_offset": [1.0, 1.0],
             "end_offset": [5.0, 5.0], "width_mm": 2.0, "lv_pin": "1", "hv_pin": "2"},
        ],
        "noise_domains": [
            {"emitters": ["Q1"], "victims": ["U1"], "max_parallel_run_mm": 8.0},
        ],
        "isolation_barriers": [
            {"name": "bar1", "x_mm": 10.0, "y_span": [0.0, 100.0], "layers": ["B.Cu"]},
        ],
        "snubber_requirements": [
            {"igbt_pair": ["Q1", "Q2"], "type": "RC", "across": "collector_emitter"},
        ],
        "bleed_resistor": {"bus_voltage_v": 400.0, "target_voltage_v": 200.0, "timeout_s": 3.0},
        "skin_effect_derating": {"frequency_hz": 100000.0, "derating_factor": 2.0},
        "slot_generation": {"enabled": True},
        "placement_priority": {"phases": []},
        "routing_priority": {"phases": []},
        "placer": {"iterations": 100},
        "seed_filter": {"enabled": False, "threshold": 0.9, "hv_threshold": 0.6},
    }
    assert canon_call(PRECONFIG, raw) == canon_call(_oracle._preprocess_config, raw)


def test_preprocess_loss_weights_mapping_matches_oracle():
    raw = {"loss_weights": {"zone_membership": 1.0, "zone": 2.0, "overlap": 3.0,
                            "unknown_key": 9.0, "boundary": 0.5}}
    assert canon_call(PRECONFIG, raw) == canon_call(_oracle._preprocess_config, raw)


def test_preprocess_preserves_dict_insertion_order():
    """Iteration order of the net_assignments / critical_paths / net_topology
    dicts is observable (list order in the output). A HashMap-based port would
    scramble it; the Rust side must use an insertion-ordered structure."""
    raw = {
        "net_assignments": {"Zeta": ["N_Z"], "Alpha": ["N_A"], "Mid": ["N_M"]},
        "critical_paths": {"c1": {"from": "A", "to": "B"}, "c2": {"from": "C", "to": "D"}},
        "net_topology": {"t1": {}, "t2": {}, "t3": {}},
    }
    proc = PRECONFIG(raw)
    oracle_proc = _oracle._preprocess_config(raw)
    assert list(proc["net_classes"].keys()) == list(oracle_proc["net_classes"].keys())
    assert [p.name for p in proc["critical_paths"]] == [p.name for p in oracle_proc["critical_paths"]]
    assert [g.net_name for g in proc["net_topologies"]] == [g.net_name for g in oracle_proc["net_topologies"]]


# ---------------------------------------------------------------------------
# load_constraints parity (R1a — the full chain, pydantic boundary).
# ---------------------------------------------------------------------------


def test_load_constraints_matches_oracle_on_production_fixture():
    assert canon_call(LOAD_CONSTRAINTS, str(PRODUCTION_CONFIG)) == canon_call(
        _oracle.load_constraints, PRODUCTION_CONFIG
    )


def test_load_constraints_matches_oracle_on_synthetic(tmp_path):
    from tests.io.test_config_loader_rust_differential import _SYNTHETIC_CONFIG_YAML

    path = tmp_path / "config.yaml"
    path.write_text(_SYNTHETIC_CONFIG_YAML, encoding="utf-8")
    assert canon_call(LOAD_CONSTRAINTS, str(path)) == canon_call(_oracle.load_constraints, path)


def test_load_constraints_validation_error_parity(tmp_path):
    """pydantic stays the authority: invalid configs raise ConfigValidationError
    on both arms with identical type name and message text."""
    for content in (
        "loss_weights:\n  overlap: -1.0\n",
        "loss_weights:\n  overlap: 2e6\n",
        "loss_weights:\n  overlap: inf\n",
        "board:\n  width_mm: 99999\n",
    ):
        path = tmp_path / "bad.yaml"
        path.write_text(content, encoding="utf-8")
        py_res = canon_call(_oracle.load_constraints, path)
        rs_res = canon_call(LOAD_CONSTRAINTS, str(path))
        assert py_res[0] == "err" and rs_res[0] == "err"
        assert rs_res[1] == py_res[1], f"{content!r}: type {rs_res} vs {py_res}"
        assert rs_res[2] == py_res[2], f"{content!r}: message mismatch"


# ---------------------------------------------------------------------------
# Downstream helper parity.
# ---------------------------------------------------------------------------


def test_infer_rjc_matches_oracle():
    for pkg in (None, "", "TO-247-3", "TO-220", "DPAK", "D2PAK", "SOT-223", "SOIC-8",
                "TO-263", "TO-252", "QFN-48", "TO-247-3L", "unknown-package", "to-247"):
        assert canon_call(INFER_RJC, pkg) == canon_call(_oracle.infer_rjc, pkg)


def test_create_board_from_constraints_matches_oracle():
    c = _oracle.load_constraints(PRODUCTION_CONFIG)
    assert canon_call(CREATE_BOARD, c) == canon_call(_oracle.create_board_from_constraints, c)


def test_constraints_to_design_rules_matches_oracle():
    c = _oracle.load_constraints(PRODUCTION_CONFIG)
    py_dr = _oracle.constraints_to_design_rules(c)
    rs_dr = TO_DESIGN_RULES(c)
    assert set(rs_dr.net_classes.keys()) == set(py_dr.net_classes.keys())
    for name in py_dr.net_classes:
        assert repr(rs_dr.net_classes[name]) == repr(py_dr.net_classes[name])
    assert repr(rs_dr.net_class_assignments) == repr(py_dr.net_class_assignments)
    assert [repr(p) for p in rs_dr.differential_pairs] == [repr(p) for p in py_dr.differential_pairs]
    assert [repr(g) for g in rs_dr.net_topologies.values()] == [
        repr(g) for g in py_dr.net_topologies.values()
    ]


def test_apply_zones_to_netlist_matches_oracle():
    from tests.io._netlist_builder import build_two_component_netlist

    c = _oracle.load_constraints(PRODUCTION_CONFIG)
    # give the constraints a component group with a zone touching the comps
    from temper_placer._constraint_types import ComponentGroup

    c.component_groups.append(ComponentGroup(name="g", components=["R1"], zone="HV"))
    nl_py = build_two_component_netlist()
    nl_rs = build_two_component_netlist()
    _oracle.apply_zones_to_netlist(nl_py, c)
    APPLY_ZONES(nl_rs, c)
    assert [comp.zone for comp in nl_rs.components] == [comp.zone for comp in nl_py.components]


def test_apply_fixed_components_to_netlist_matches_oracle():
    from tests.io._netlist_builder import build_two_component_netlist

    c = _oracle.load_constraints(PRODUCTION_CONFIG)
    c.fixed_components = ["R1"]
    c.fixed_positions = {"R1": (12.5, 3.25)}
    nl_py = build_two_component_netlist()
    nl_rs = build_two_component_netlist()
    _oracle.apply_fixed_components_to_netlist(nl_py, c)
    APPLY_FIXED(nl_rs, c)
    py_comps = [(comp.ref, comp.fixed, comp.initial_position) for comp in nl_py.components]
    rs_comps = [(comp.ref, comp.fixed, comp.initial_position) for comp in nl_rs.components]
    assert rs_comps == py_comps
