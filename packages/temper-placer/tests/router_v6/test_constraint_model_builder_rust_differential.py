"""Differential tests: the Phase E batch E1 `ModelBuilder` orchestration.

Rust Orchestration Engine plan 2026-08-09-001, Phase E batch E1: the
model-building orchestration in `router_v6/constraint_model.py` --
`ModelBuilder` and every `_create_*` method, which assemble the
`ConstraintModel` of `NetChannelVar`/`ViaVar` variables and
`CapacityConstraint`/`DiffPairConstraint`/`LayerConstraint` objects from
the board/netlist/skeletons -- moves to `temper-design-bundle` as
`ModelBuilder::build()` (a pyclass mirror registered as the
`temper_design_bundle_python.model_builder` submodule). The ortools
encoder boundary and the PCL compiler stay Python (see the module
docstring of `packages/temper-design-bundle/src/model_builder.rs` for the
precise split).

The pre-migration implementation is pinned VERBATIM as the oracle
(`tests/router_v6/_constraint_model_builder_py_oracle.py`, a byte-exact
snapshot of the module as committed at `8dce8f8a^`, the parent of the
Wave-4 kernel-migration commit; only the non-migrating
`Stage`/`BoardState` tail is omitted). Both arms are driven with IDENTICAL
inputs and the resulting models are compared field-by-field, bit-exactly
(floats projected through `float.hex()`; variable/constraint identity by
the exported `name` string, which encodes net index + channel edge id).

Bit-exactness classes exercised (`docs/wave4-discipline-contract.md` §2):

- **B3** (banker's rounding): the via-anchor `node_id`
  `f"VIA_N{i}_{node[0]:.2f}_{node[1]:.2f}"` is byte-identical to a Rust
  `format!("{:.2}")` -- measured over 250,005 adversarial samples on this
  host (see the constraint_model.rs B3 note for the argument; the exact
  two-decimal tie is unreachable for binary floats).
- **B1/B5/B7** (host-libm via dlsym, builtin-`max`, `**` = libm `pow`):
  the pruning predicate kernels are the already-pinned
  `temper_design_bundle_python.constraint_model` kernels, driven through
  FFI by the port; the oracle's pure-Python copies are pinned by
  `test_constraint_model_rust_differential.py`.
- **Ordering**: `skeletons.items()` insertion order, net list order,
  `bundle_id_for_net` insertion order, and networkx edge iteration order
  are all preserved (the Rust side iterates the live Python dicts/lists,
  never a copied HashMap).
"""

from __future__ import annotations

import hashlib
import inspect
import math
from pathlib import Path

import tests.graph_fixtures as nx
import pytest

import tests.router_v6._constraint_model_builder_py_oracle as _orc

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import ModelBuilder as ShimModelBuilder
from temper_placer.router_v6 import constraint_model as cm_module
from temper_placer.router_v6.diff_pair_inference import DiffPair
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules, ParsedPCB

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_ORACLE_BODY_DIGEST = "bc5f1538695ab30e1feff32e52bc64f74951947ff6ca0f21b4ebb5584f55e14f"
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_body_matches_pinned_digest() -> None:
    text = (Path(__file__).with_name("_constraint_model_builder_py_oracle.py")).read_text(
        encoding="utf-8"
    )
    assert _BODY_MARKER in text, "oracle header marker missing"
    body = text.rsplit(_BODY_MARKER, 1)[1]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == _ORACLE_BODY_DIGEST, (
        "oracle drifted from its pinned digest; the oracle must be a verbatim "
        "pre-migration snapshot, never edited to agree with the port"
    )


def test_shim_and_oracle_are_different_implementations() -> None:
    """The shim's `ModelBuilder.build()` must resolve to the Rust builder,
    not back onto the oracle's (or a hand-rolled) Python implementation."""
    shim_src = inspect.getsource(ShimModelBuilder.build)
    assert "self._rust.build()" in shim_src, (
        "shim ModelBuilder.build() does not delegate to the Rust model builder"
    )
    import temper_design_bundle_python as _tdb

    assert cm_module._mb is _tdb.model_builder, (
        "shim module must bind _mb to the Rust model_builder submodule"
    )
    orc_src = inspect.getsource(_orc.ModelBuilder.build)
    assert "temper_design_bundle_python" not in orc_src, (
        "oracle must stay pure Python (pre-migration snapshot)"
    )
    # Runtime proof: the shim-built model is a design-bundle pyclass, and
    # the oracle-built model is a Python dataclass -- distinct types by
    # construction, so the differential cannot be Rust-vs-Rust.
    model = _shim_build(*_inputs("simple"))
    assert type(model).__module__ == "temper_design_bundle_python.model_builder", (
        f"shim returned {type(model).__module__}, expected the design-bundle pyclass"
    )
    o_model = _orc_build(*_inputs("simple"))
    assert type(o_model).__module__ == "tests.router_v6._constraint_model_builder_py_oracle"


# ---------------------------------------------------------------------------
# Shared fixture construction
# ---------------------------------------------------------------------------


def _sk(layer_name: str, edges) -> ChannelSkeleton:
    g = nx.Graph()
    for u, v in edges:
        g.add_edge(u, v)
    return ChannelSkeleton(graph=g, layer_name=layer_name, total_length=10.0)


def _rules() -> DesignRules:
    classes = {
        "W0.1": NetClassRules(
            name="W0.1", clearance_mm=0.0, trace_width_mm=0.1, via_diameter_mm=0.3,
            via_drill_mm=0.15,
        ),
        "W0.2": NetClassRules(
            name="W0.2", clearance_mm=0.0, trace_width_mm=0.2, via_diameter_mm=0.3,
            via_drill_mm=0.15,
        ),
    }
    return DesignRules(
        net_classes=classes,
        net_class_assignments={"AAA": "W0.1", "BBB": "W0.2", "CCC": "W0.1", "DDD": "W0.2"},
        default_clearance_mm=0.0,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15,
    )


def _manifest(bundle_id_for_net: dict[int, int]):
    from dataclasses import dataclass, field

    @dataclass
    class _MockManifest:
        bundle_id_for_net: dict = field(default_factory=dict)
        unbundled_net_indices: list = field(default_factory=list)

    return _MockManifest(bundle_id_for_net=dict(bundle_id_for_net), unbundled_net_indices=[])


def _inputs(name: str):
    """Return the (skeletons, nets, channel_widths, design_rules, diff_pairs,
    pcb, kwargs) tuple for a named config. Both arms consume this identically."""
    if name == "simple":
        skeletons = {
            "L1": _sk("L1", [((0, 0), (10, 0)), ((0, 10), (10, 10))]),
            "L2": _sk("L2", [((0, 0), (0, 10))]),
        }
        nets = [Net(name="AAA", pins=[]), Net(name="BBB", pins=[])]
        return skeletons, nets, None, None, None, None, {}

    if name == "via_vars":
        skeletons, nets, _, _, _, _, kwargs = _inputs("simple")
        return skeletons, nets, None, None, None, None, {"enable_via_vars": True}

    if name == "capacity":
        skeletons = {"L1": _sk("L1", [((0.0, 0.0), (10.0, 0.0))])}
        nets = [Net(name=n, pins=[]) for n in ("AAA", "BBB", "CCC", "DDD")]
        widths = {
            "L1": ChannelWidths(
                layer_name="L1",
                node_widths={},
                edge_widths={((0.0, 0.0), (10.0, 0.0)): 0.5},
                min_width=0.5,
                max_width=0.5,
                avg_width=0.5,
            )
        }
        return skeletons, nets, widths, _rules(), None, None, {}

    if name == "diff_pair":
        skeletons, nets, widths, rules, _, _, kwargs = _inputs("capacity")
        pairs = [DiffPair(base_name="AB", p_net="AAA", n_net="BBB")]
        return skeletons, nets, widths, rules, pairs, None, {}

    if name == "layer_constraints":
        skeletons = {
            "F.Cu": _sk("F.Cu", [((0.0, 0.0), (10.0, 0.0))]),
            "B.Cu": _sk("B.Cu", [((0.0, 0.0), (0.0, 10.0))]),
        }
        nets = [Net(name="N1", pins=[])]
        pin = Pin(name="1", number="1", position=(0.0, 0.0), net="N1", layer="F.Cu", is_pth=False)
        comp = Component(
            ref="U1", footprint="FP", bounds=(1.0, 1.0), pins=[pin], initial_position=(0.0, 0.0)
        )
        pcb = ParsedPCB(
            components=[comp],
            nets=nets,
            zones=[],
            board=None,
            design_rules=None,
            stackup=None,
            source_path=None,
        )
        return skeletons, nets, None, None, None, pcb, {}

    if name == "pruning":
        skeletons = {
            "L1": _sk("L1", [((0.0, 0.0), (10.0, 0.0)), ((500.0, 0.0), (510.0, 0.0))]),
        }
        nets = [Net(name="N1", pins=[]), Net(name="N2", pins=[])]
        pins1 = [Pin(name="1", number="1", position=(0.0, 0.0), net="N1", layer="F.Cu", is_pth=True)]
        pins2 = [Pin(name="1", number="1", position=(1000.0, 0.0), net="N2", layer="F.Cu", is_pth=True)]
        comps = [
            Component(ref="U1", footprint="FP", bounds=(1.0, 1.0), pins=pins1,
                      initial_position=(0.0, 0.0)),
            Component(ref="U2", footprint="FP", bounds=(1.0, 1.0), pins=pins2,
                      initial_position=(1000.0, 0.0)),
        ]
        pcb = ParsedPCB(
            components=comps,
            nets=nets,
            zones=[],
            board=None,
            design_rules=None,
            stackup=None,
            source_path=None,
        )
        return skeletons, nets, None, None, None, pcb, {"enable_geographic_pruning": True}

    if name == "pruning_empty_raises":
        skeletons = {"L1": _sk("L1", [((0.0, 0.0), (10.0, 0.0))])}
        nets = [Net(name="SIG1", pins=[])]
        pcb = ParsedPCB(
            components=[],
            nets=nets,
            zones=[],
            board=None,
            design_rules=None,
            stackup=None,
            source_path=None,
        )
        return skeletons, nets, None, None, None, pcb, {"enable_geographic_pruning": True}

    if name == "bundling":
        skeletons = {"L1": _sk("L1", [((0.0, 0.0), (10.0, 0.0))])}
        nets = [Net(name=n, pins=[]) for n in ("AAA", "BBB", "CCC", "DDD")]
        widths = {
            "L1": ChannelWidths(
                layer_name="L1",
                node_widths={},
                edge_widths={((0.0, 0.0), (10.0, 0.0)): 10.0},
                min_width=10.0,
                max_width=10.0,
                avg_width=10.0,
            )
        }
        # bundle 0 = {net 0, net 1}; bundle 1 = {net 2, net 3}. Net 1's index
        # numerically coincides with bundle 1's id (the Sec 3.3 collision
        # shape) -- bundle vars must stay in bundle_channel_vars.
        return (
            skeletons,
            nets,
            widths,
            _rules(),
            None,
            None,
            {
                "enable_bundling": True,
                "bundle_manifest": _manifest({0: 0, 1: 0, 2: 1, 3: 1}),
            },
        )

    if name == "bundling_diff_pair_skipped":
        skeletons, nets, widths, rules, _, _, kwargs = _inputs("bundling")
        pairs = [DiffPair(base_name="AB", p_net="AAA", n_net="BBB")]
        return skeletons, nets, widths, rules, pairs, None, kwargs

    raise AssertionError(f"unknown config {name}")


def _orc_build(skeletons, nets, widths, rules, pairs, pcb, kwargs):
    return _orc.ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=widths,
        design_rules=rules,
        diff_pairs=pairs,
        pcb=pcb,
        **kwargs,
    ).build()


def _shim_build(skeletons, nets, widths, rules, pairs, pcb, kwargs):
    return ShimModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=widths,
        design_rules=rules,
        diff_pairs=pairs,
        pcb=pcb,
        **kwargs,
    ).build()


# ---------------------------------------------------------------------------
# Canonicalisers -- bit-exact field-by-field model comparison
# ---------------------------------------------------------------------------


def _hx(v):
    if isinstance(v, float):
        if math.isnan(v):
            return ("nan", math.copysign(1.0, v))
        return ("float", v.hex())
    return v


def _canon_var(v):
    t = type(v).__name__
    if t == "NetChannelVar":
        return (t, v.name, v.var_type, v.net_idx, v.channel_id)
    if t == "NetLayerVar":
        return (t, v.name, v.var_type, v.net_idx, v.segment_id)
    if t == "ViaVar":
        return (t, v.name, v.var_type, v.net_idx, v.location_id)
    if t == "OrderVar":
        return (t, v.name, v.var_type, v.net1_idx, v.net2_idx, v.channel_id)
    return (t, v.name, v.var_type)


def _canon_con(c):
    t = type(c).__name__
    base = (t, c.name, c.description)
    if t == "CapacityConstraint":
        terms = tuple((v.name, _hx(w)) for v, w in c.terms)
        return base + (c.channel_id, _hx(c.capacity), _hx(c.slack_factor), terms)
    if t == "DiffPairConstraint":
        p_name = getattr(c.p_var, "name", c.p_var)
        n_name = getattr(c.n_var, "name", c.n_var)
        return base + (c.channel_id, c.p_net_idx, c.n_net_idx, p_name, n_name)
    if t == "LayerConstraint":
        return base + (c.net_idx, c.channel_id, c.allowed)
    if t == "ChannelSeparationConstraint":
        return base + (
            c.channel_id,
            tuple(c.group_a_indices),
            tuple(c.group_b_indices),
            c.min_slots,
        )
    return base


def _canon_model(m):
    return (
        tuple(_canon_var(v) for v in m.variables),
        tuple(_canon_con(c) for c in m.constraints),
        tuple(sorted((k, _canon_var(v)) for k, v in m.net_channel_vars.items())),
        tuple(sorted((k, _canon_var(v)) for k, v in m.bundle_channel_vars.items())),
        tuple(sorted((k, _canon_var(v)) for k, v in m.via_vars.items())),
    )


# ---------------------------------------------------------------------------
# Differential cases
# ---------------------------------------------------------------------------

_ALL_CONFIGS = [
    "simple",
    "via_vars",
    "capacity",
    "diff_pair",
    "layer_constraints",
    "pruning",
    "bundling",
    "bundling_diff_pair_skipped",
]


@pytest.mark.parametrize("config", _ALL_CONFIGS)
def test_model_bit_identical_to_oracle(config):
    inputs = _inputs(config)
    o_model = _orc_build(*inputs)
    s_model = _shim_build(*inputs)
    got = _canon_model(s_model)
    expected = _canon_model(o_model)
    assert got == expected, (
        f"[{config}] Rust-built model differs from the pre-migration oracle:\n"
        f"  variables: {len(s_model.variables)} vs {len(o_model.variables)}\n"
        f"  constraints: {len(s_model.constraints)} vs {len(o_model.constraints)}\n"
        f"  got:      {got!r}\n"
        f"  expected: {expected!r}"
    )


def test_pruning_empty_raises_identical_message():
    inputs = _inputs("pruning_empty_raises")
    with pytest.raises(_orc.ConstraintModelEmptyError) as o_exc:
        _orc_build(*inputs)
    from temper_placer.router_v6.constraint_model import ConstraintModelEmptyError

    with pytest.raises(ConstraintModelEmptyError) as s_exc:
        _shim_build(*inputs)
    assert str(s_exc.value) == str(o_exc.value)


def test_empty_skeletons_and_empty_nets_do_not_raise():
    """The R10 precondition is scoped to skeletons AND nets both non-empty;
    either side empty must produce an empty model without raising (the
    Stage-2.3 / Stage-0 shapes, guarded elsewhere)."""
    skeletons, nets, _, _, _, _, kwargs = _inputs("simple")
    o1 = _orc_build({}, nets, None, None, None, None, kwargs)
    s1 = _shim_build({}, nets, None, None, None, None, kwargs)
    assert _canon_model(s1) == _canon_model(o1) == ((), (), (), (), ())
    o2 = _orc_build(skeletons, [], None, None, None, None, kwargs)
    s2 = _shim_build(skeletons, [], None, None, None, None, kwargs)
    assert _canon_model(s2) == _canon_model(o2) == ((), (), (), (), ())
