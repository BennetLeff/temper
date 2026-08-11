"""Differential tests: the Phase E batch E2 `FixedCopperBuilder` orchestration.

Rust Orchestration Engine plan 2026-08-09-001, Phase E batch E2: the
fixed-copper build orchestration in `placer/cp_sat/fixed_copper.py` —
`build_free_component_pads` / `build_fixed_copper_items` / `audit_fixed_copper`
— moves to `temper-design-bundle` as `FixedCopperBuilder::build*` plus the
`PadRectLocal` / `FixedCopperItem` / `FixedCopperAuditViolation` contract
pyclasses (registered as the `temper_design_bundle_python.fixed_copper_builder`
submodule). The ortools encoder boundary (`encode_fixed_copper_constraints` /
`_pad_rotation_tables_with` / `_add_no_overlap`) stays Python (plan D4 KEEP
verdict) — see the module docstring of
`packages/temper-design-bundle/src/fixed_copper_builder.rs` for the precise
split.

The pre-migration implementation is pinned VERBATIM as the oracle
(`tests/placer/cp_sat/_fixed_copper_py_oracle.py`, the Wave-4 kernel-migration
oracle extracted at `1dd54e3f2cc58e9dd6cbc5b3c54d68b4d0374ae9` — a pure-Python
snapshot that predates BOTH the temper-geometry kernel carve-out and this E2
orchestration migration). Both arms are driven with IDENTICAL inputs and the
resulting pads / items / audit violations are compared field-by-field,
bit-exactly (floats projected through `float.hex()`).

Bit-exactness classes exercised (`docs/wave4-discipline-contract.md` §2):

- **B3** (banker's rounding): the item labels `f"({x:.2f},{y:.2f})"` /
  `f"d={d:.2f}"` are byte-identical to Rust `format!("{:.2}")` (the B3
  argument from `constraint_model.rs`, measured over 250,005 adversarial
  samples on this host). A `None` net renders as the literal `"None"` exactly
  like an f-string.
- **Kernel reuse**: the item geometry, pad world rect, exact-clearance and
  edge-half-plane kernels are the already-pinned `temper-geometry`
  `fixed_copper_*_py` functions, driven through FFI by the port — the oracle's
  pure-Python geometry is pinned bit-exactly by
  `test_fixed_copper_rust_differential.py` (150k+ BMC cases), so the
  orchestration differential inherits that proof.
- **Ordering**: `netlist.components` order, `comp.pins` order,
  `parse_result.traces` order, `parse_result.vias` order, `board.zones` order,
  and the pinned-component scan order are all preserved (the Rust side
  iterates the live Python lists, never a copied HashMap).
"""

from __future__ import annotations

import hashlib
import inspect
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.placer.cp_sat._fixed_copper_py_oracle as _orc

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io._kicad_types import TraceData
from temper_placer.placer.cp_sat import fixed_copper as _shim

_ORACLE_BODY_DIGEST = "d2caceafdabb3f7dd698bcaeb111eca2c540788db2485eb5517c05910b74741e"


def test_oracle_body_matches_pinned_digest() -> None:
    """G1: the oracle is a verbatim pre-migration snapshot, never edited to
    agree with the port."""
    text = (
        Path(__file__).with_name("_fixed_copper_py_oracle.py").read_text(encoding="utf-8")
    )
    assert text.lstrip().startswith("# PINNED ORACLE"), "oracle header marker missing"
    body = text[text.index('"""') :]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == _ORACLE_BODY_DIGEST, (
        "oracle drifted from its pinned digest; the oracle must be a verbatim "
        "pre-migration snapshot, never edited to agree with the port"
    )


def test_shim_and_oracle_are_different_implementations() -> None:
    """The shim's orchestration must resolve to the Rust FixedCopperBuilder,
    not back onto the oracle's (or a hand-rolled) Python implementation."""
    import temper_design_bundle_python as _tdb

    assert _shim._fcb is _tdb.fixed_copper_builder, (
        "shim module must bind _fcb to the Rust fixed_copper_builder submodule"
    )
    orc_src = inspect.getsource(_orc.build_free_component_pads)
    assert "temper_design_bundle_python" not in orc_src, (
        "oracle must stay pure Python (pre-migration snapshot)"
    )
    # Runtime proof: shim-built pads/items are design-bundle pyclasses, and
    # oracle-built pads/items are Python dataclasses -- distinct types by
    # construction, so the differential cannot be Rust-vs-Rust.
    inputs = _inputs("mixed")
    pads = _shim_build_pads(*inputs)
    items = _shim_build_items(*inputs)
    pad = pads[next(iter(pads))][0]
    assert type(pad).__module__ == "temper_design_bundle_python.fixed_copper_builder", (
        f"shim returned {type(pad).__module__}, expected the design-bundle pyclass"
    )
    assert type(items[0]).__module__ == "temper_design_bundle_python.fixed_copper_builder"
    o_pads = _orc_build_pads(*inputs)
    o_items = _orc_build_items(*inputs)
    assert type(o_pads[next(iter(o_pads))][0]).__module__.endswith("_fixed_copper_py_oracle")
    assert type(o_items[0]).__module__.endswith("_fixed_copper_py_oracle")


# ---------------------------------------------------------------------------
# Shared fixture construction
# ---------------------------------------------------------------------------


def _pin(number, net, layer="F.Cu", pos=(0.0, 0.0), w=1.0, h=1.0, pth=False, rot=0.0):
    return Pin(
        name=number,
        number=number,
        position=pos,
        net=net,
        width=w,
        height=h,
        shape="rect",
        layer=layer,
        is_pth=pth,
        pad_rotation_deg=rot,
    )


def _zone(name, polygon, layers, net_classes):
    return SimpleNamespace(
        name=name, polygon=list(polygon), layers=list(layers), net_classes=list(net_classes)
    )


def _inputs(name: str):
    """Return the (parse_result, netlist, free_refs, kwargs) tuple for a
    named config. Both arms consume this identically."""
    if name == "empty":
        board = Board(width=10.0, height=10.0, origin=(0.0, 0.0), zones=[])
        pr = SimpleNamespace(traces=[], vias=[], board=board)
        nl = Netlist(components=[], nets=[])
        return pr, nl, set(), {}

    if name == "mixed":
        comps = [
            Component(
                ref="U1",
                footprint="t",
                bounds=(2.0, 2.0),
                pins=[
                    _pin("1", "NET_A", layer="F.Cu", pos=(0.0, 0.0)),
                    _pin("2", "NET_B", layer="B.Cu", pos=(0.0, 1.0), w=0.8, h=0.6, rot=30.0),
                ],
                initial_position=(10.0, 10.0),
                initial_rotation=0,
            ),
            Component(
                ref="U2",
                footprint="t",
                bounds=(2.0, 2.0),
                pins=[
                    _pin("1", "NET_A", layer="F.Cu", pos=(0.5, 0.5), pth=True),
                    _pin("2", "NET_C", layer="In1.Cu", pos=(0.0, 0.0)),
                ],
                initial_position=(5.0, 5.0),
                initial_rotation=1,
            ),
            Component(
                ref="U3",
                footprint="t",
                bounds=(2.0, 2.0),
                pins=[
                    _pin("1", None, layer="F.Cu", pos=(0.0, 0.0)),  # unconnected pad
                ],
                initial_position=(20.0, 20.0),
                initial_rotation=None,
            ),
        ]
        traces = [
            TraceData(start=(25.0, 25.0), end=(25.0, 35.0), width=0.2, layer="F.Cu", net="NET_X"),
            TraceData(start=(0.0, 0.0), end=(4.0, 3.0), width=0.5, layer="B.Cu", net="NET_Y"),
            TraceData(start=(3.0, 3.0), end=(3.0, 3.0), width=0.4, layer="F.Cu", net=None),
            TraceData(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="Silkscreen", net="NET_Z"),
        ]
        vias = [
            SimpleNamespace(
                layers=["F.Cu", "B.Cu"], position=(5.0, 5.0), diameter=0.8, net="NET_X"
            ),
            SimpleNamespace(
                layers=["F.Cu"], position=(7.0, 7.0), diameter=0.6, net=None
            ),
            SimpleNamespace(
                layers=["Silkscreen"], position=(9.0, 9.0), diameter=0.6, net="NET_Q"
            ),
        ]
        zones = [
            _zone("Z_rect", [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)], ["F.Cu"], ["NET_A"]),
            _zone("Z_diag", [(10.0, 10.0), (14.0, 12.0), (12.0, 16.0)], ["B.Cu"], ["NET_B"]),
            _zone("Z_L", [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)],
                  ["In1.Cu"], ["NET_C"]),
            _zone("Z_bad", [(0.0, 0.0)], ["F.Cu"], ["NET_D"]),
            _zone("Z_silk", [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0)], ["Silkscreen"], ["NET_E"]),
        ]
        board = Board(width=100.0, height=100.0, origin=(20.0, 20.0), zones=zones)
        pr = SimpleNamespace(traces=traces, vias=vias, board=board)
        nl = Netlist(components=comps, nets=[Net(name="NET_A", pins=[]), Net(name="NET_B", pins=[])])
        return pr, nl, {"U1", "U3"}, {}

    if name == "copper_layers_bcu":
        pr, nl, free, _ = _inputs("mixed")
        return pr, nl, free, {"copper_layers": frozenset({"B.Cu"})}

    if name == "no_other_pads":
        pr, nl, free, _ = _inputs("mixed")
        return pr, nl, free, {"include_other_pads": False}

    if name == "margin_big":
        pr, nl, free, _ = _inputs("mixed")
        return pr, nl, free, {"margin_mm": 0.3}

    raise AssertionError(f"unknown config {name}")


def _orc_build_pads(pr, nl, free, kwargs):
    return _orc.build_free_component_pads(
        nl, free, **{k: v for k, v in kwargs.items() if k == "copper_layers"}
    )


def _shim_build_pads(pr, nl, free, kwargs):
    return _shim.build_free_component_pads(
        nl, free, **{k: v for k, v in kwargs.items() if k == "copper_layers"}
    )


def _orc_build_items(pr, nl, free, kwargs):
    return _orc.build_fixed_copper_items(pr, nl, free, **kwargs)


def _shim_build_items(pr, nl, free, kwargs):
    return _shim.build_fixed_copper_items(pr, nl, free, **kwargs)


# ---------------------------------------------------------------------------
# Canonicalisers -- bit-exact field-by-field comparison
# ---------------------------------------------------------------------------


def _hx(v):
    if isinstance(v, float):
        if math.isnan(v):
            return ("nan", math.copysign(1.0, v))
        return ("float", v.hex())
    return v


def _layers(layers):
    return tuple(sorted(layers))


def _canon_pad(p):
    return (
        p.number,
        p.net,
        _layers(p.layers),
        _hx(p.center[0]),
        _hx(p.center[1]),
        _hx(p.half[0]),
        _hx(p.half[1]),
    )


def _exact(d):
    out = []
    for key in ("p0", "p1", "width", "center", "diameter", "rect", "polygon"):
        if key in d:
            v = d[key]
            if isinstance(v, (tuple, list)) and key != "polygon":
                out.append((key, tuple(_hx(x) for x in v)))
            elif isinstance(v, (tuple, list)):
                out.append((key, tuple(tuple(_hx(c) for c in pt) for pt in v)))
            else:
                out.append((key, _hx(v)))
    return tuple(out)


def _edges(edges):
    if edges is None:
        return None
    out = []
    for e in edges:
        if e[0] == "n":
            out.append(("n", e[1], e[2], e[3]))
        else:
            out.append((e[0], _hx(e[1]), e[2]))
    return tuple(out)


def _canon_item(i):
    return (
        i.kind,
        i.net,
        _layers(i.layers),
        tuple(_hx(v) for v in i.rect),
        _exact(i.exact),
        _hx(i.slack_mm),
        _hx(i.margin_mm),
        i.label,
        _edges(i.edges),
    )


def _canon_pads(pads_by_ref):
    return tuple(
        (ref, tuple(_canon_pad(p) for p in pads))
        for ref, pads in pads_by_ref.items()
    )


def _canon_items(items):
    return tuple(_canon_item(i) for i in items)


def _canon_violation(v):
    return (
        v.ref,
        v.pad_number,
        v.item_label,
        v.item_kind,
        v.item_net,
        _hx(v.required_mm),
        _hx(v.actual_mm),
        v.reason,
    )


def _canon_violations(violations):
    return tuple(_canon_violation(v) for v in violations)


# The oracle's `exact_clearance_mm` zone branch is SHAPELY (`pad.distance`);
# the port's zone branch is the from-scratch temper-geometry zone kernel,
# which is proven sound-by-BMC (150k+ cases) but NOT bit-for-bit with
# shapely/GEOS — the documented gap in `test_fixed_copper_rust_differential.py`.
# Measured on the production board the zone distances agree to ~7e-15 mm
# (622 ulp at ~0.05 mm), far below the 0.01 mm model grid. The audit
# comparison therefore compares zone `actual_mm` within 1e-9 mm while every
# OTHER field (including the 4-decimal `reason` string, which is stable
# across the zone gap) stays bit-exact.
_ZONE_CLEARANCE_TOL = 1e-9


def _assert_audit_equal(got_violations, expected_violations):
    assert len(got_violations) == len(expected_violations), (
        f"audit violation count differs: {len(got_violations)} vs "
        f"{len(expected_violations)}"
    )
    for g, e in zip(got_violations, expected_violations):
        if g.item_kind == "zone":
            assert abs(g.actual_mm - e.actual_mm) <= _ZONE_CLEARANCE_TOL, (
                f"zone actual_mm diverges beyond {_ZONE_CLEARANCE_TOL}: "
                f"{g.actual_mm.hex()} vs {e.actual_mm.hex()}"
            )
            reduced_g = (g.ref, g.pad_number, g.item_label, g.item_kind, g.item_net,
                         _hx(g.required_mm), "zone-clearance", g.reason)
            reduced_e = (e.ref, e.pad_number, e.item_label, e.item_kind, e.item_net,
                         _hx(e.required_mm), "zone-clearance", e.reason)
            assert reduced_g == reduced_e, (
                f"zone violation fields differ: {reduced_g!r} vs {reduced_e!r}"
            )
        else:
            g_c = _canon_violation(g)
            e_c = _canon_violation(e)
            assert g_c == e_c, f"violation differs: {g_c!r} vs {e_c!r}"


# ---------------------------------------------------------------------------
# Differential cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ["empty", "mixed", "copper_layers_bcu", "no_other_pads", "margin_big"])
def test_pads_bit_identical_to_oracle(config):
    inputs = _inputs(config)
    got = _canon_pads(_shim_build_pads(*inputs))
    expected = _canon_pads(_orc_build_pads(*inputs))
    assert got == expected, (
        f"[{config}] Rust-built pads differ from the pre-migration oracle:\n"
        f"  got:      {got!r}\n"
        f"  expected: {expected!r}"
    )


@pytest.mark.parametrize("config", ["empty", "mixed", "copper_layers_bcu", "no_other_pads", "margin_big"])
def test_items_bit_identical_to_oracle(config):
    inputs = _inputs(config)
    got = _canon_items(_shim_build_items(*inputs))
    expected = _canon_items(_orc_build_items(*inputs))
    assert got == expected, (
        f"[{config}] Rust-built items differ from the pre-migration oracle:\n"
        f"  got:      {got!r}\n"
        f"  expected: {expected!r}"
    )


@pytest.mark.parametrize("config", ["empty", "mixed", "copper_layers_bcu", "no_other_pads", "margin_big"])
def test_audit_bit_identical_to_oracle(config):
    inputs = _inputs(config)
    pads = _shim_build_pads(*inputs)
    items = _shim_build_items(*inputs)
    o_pads = _orc_build_pads(*inputs)
    o_items = _orc_build_items(*inputs)
    positions = {"U1": (10.0, 10.0), "U2": (5.0, 5.0), "U3": (21.0, 21.0)}
    rotations = {"U1": 0, "U2": 1, "U3": 2}
    got = _shim.audit_fixed_copper(pads, items, positions, rotations)
    expected = _orc.audit_fixed_copper(o_pads, o_items, positions, rotations)
    _assert_audit_equal(got, expected)


def test_missing_positions_and_rotations_match_oracle():
    """The audit's missing-position / missing-rotation handling must be
    bit-identical (NaN actual_mm, the 'missing resolved position' reason)."""
    pr, nl, free, kwargs = _inputs("mixed")
    pads = _shim_build_pads(pr, nl, free, kwargs)
    items = _shim_build_items(pr, nl, free, kwargs)
    o_pads = _orc_build_pads(pr, nl, free, kwargs)
    o_items = _orc_build_items(pr, nl, free, kwargs)
    # U1 and U3 have no resolved position; U2 has one but no rotation.
    got = _shim.audit_fixed_copper(pads, items, {"U2": (5.0, 5.0)}, {})
    expected = _orc.audit_fixed_copper(o_pads, o_items, {"U2": (5.0, 5.0)}, {})
    _assert_audit_equal(got, expected)


# ---------------------------------------------------------------------------
# Real production board
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"


def _load_real_board():
    if not _PCB_PATH.exists():
        pytest.skip(f"production board {_PCB_PATH} not available")
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    return parse_kicad_pcb(_PCB_PATH)


def test_real_board_items_and_pads_bit_identical():
    """The strongest differential: the production board through both arms. The
    oracle's pure-Python geometry and the port's kernel-driven orchestration
    must produce byte-identical pads/items."""
    pr = _load_real_board()
    free = {"K2", "K3", "C27"}
    got_pads = _canon_pads(_shim_build_pads(pr, pr.netlist, free, {}))
    exp_pads = _canon_pads(_orc_build_pads(pr, pr.netlist, free, {}))
    assert got_pads == exp_pads, "real-board pads differ from the oracle"
    got_items = _canon_items(_shim_build_items(pr, pr.netlist, free, {}))
    exp_items = _canon_items(_orc_build_items(pr, pr.netlist, free, {}))
    assert len(got_items) > 1000, "falsifier: the real board's item list collapsed"
    assert got_items == exp_items, (
        f"real-board items differ from the oracle ({len(got_items)} vs {len(exp_items)})"
    )


def test_real_board_audit_bit_identical():
    """The R24 item-3 audit on the production board, resolved to the parsed
    initial positions, must produce identical violations in both arms."""
    pr = _load_real_board()
    free = {"K2", "K3", "C27"}
    pads = _shim_build_pads(pr, pr.netlist, free, {})
    items = _shim_build_items(pr, pr.netlist, free, {})
    o_pads = _orc_build_pads(pr, pr.netlist, free, {})
    o_items = _orc_build_items(pr, pr.netlist, free, {})
    positions = {}
    for comp in pr.netlist.components:
        if comp.initial_position is not None:
            positions[comp.ref] = tuple(float(v) for v in comp.initial_position)
    rotations = {ref: int(c.initial_rotation or 0) for c in pr.netlist.components
                 for ref in [c.ref] if c.ref in free}
    got = _shim.audit_fixed_copper(pads, items, positions, rotations)
    expected = _orc.audit_fixed_copper(o_pads, o_items, positions, rotations)
    assert len(got) > 0, "falsifier: the real-board audit must produce violations at initial positions"
    _assert_audit_equal(got, expected)
