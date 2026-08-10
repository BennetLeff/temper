"""Differential test: Phase-A U9 loop-extraction marshalers in Rust
(temper_design_bundle_python.LoopExtractionInput / LoopExtractionOutput)
vs the pinned Python marshalers (Wave-4 discipline contract G1/G2).

The two wire-format builders being migrated are:

  | Python marshaler                 | File                        | Rust target                 |
  |----------------------------------|-----------------------------|-----------------------------|
  | ``_netlist_to_dict``             | core/loop_extractor_rs.py   | ``LoopExtractionInput``     |
  | ``_dict_to_loop_collection``     | core/loop_extractor_rs.py   | ``LoopExtractionOutput``    |

``_netlist_to_dict`` builds the flat dict that the
``temper_rust_router.auto_extract_loops_rust`` JSON bridge consumes; the
``LoopExtractionInput`` typed struct reproduces it bit-for-bit (including
the `net_class` component key and the `[ref, pin]` net-pin pairs), with
``to_json()`` delegating to CPython ``json.dumps`` so the bridge bytes are
identical. ``_dict_to_loop_collection`` parses the bridge's output dict;
``LoopExtractionOutput`` carries the typed ``ok``/``error``/``loops`` wire
surface with the shim's documented defaults (missing ``loops`` -> empty,
missing ``ok`` -> False, per-loop ``components``/``nets`` -> [] and
``max_area_mm2`` -> 500.0).

The ``_oracle_*`` blocks below are VERBATIM copies of the pre-migration
implementations AS COMMITTED (``core/loop_extractor_rs.py`` at the dispatch
base, origin/main). Do NOT edit them -- they are the reference.

The Rust symbols ``_tdb.LoopExtractionInput`` /
``_tdb.LoopExtractionOutput`` do not exist yet (RED); this file fails to
collect until the Phase-A U9 Rust implementation lands (G1 test-before-code).

Comparison convention: dicts/JSON canonicalized via the type-carrying
``canon`` (bit-exact, never tolerance); floats via ``float.hex()``.
"""

from __future__ import annotations

import json

import temper_design_bundle_python as _tdb

from tests.core._contract_canon import canon

# Rust symbols under test -- must exist or this file fails to collect (RED).
ORACLE_INPUT = _tdb.LoopExtractionInput
ORACLE_OUTPUT = _tdb.LoopExtractionOutput

from temper_placer.core.loop import (  # noqa: E402
    LoopCollection,
    LoopPriority,
    LoopType,
)
from temper_placer.core.loop_extractor_rs import (  # noqa: E402
    _dict_to_loop_collection,
    _netlist_to_dict,
)
from tests.core.test_loop_extractor_auto_extract_rust_differential import (  # noqa: E402
    _CORPUS,
    _RANDOM_CORPUS,
    _full_half_bridge,
)

# ---------------------------------------------------------------------------
# Oracle 1 — _netlist_to_dict (loop_extractor_rs.py, verbatim)
# ---------------------------------------------------------------------------

def _oracle_netlist_to_dict(netlist):
    """Pre-migration ``_netlist_to_dict``, verbatim (loop_extractor_rs.py)."""
    return {
        "components": [
            {
                "ref": c.ref,
                "footprint": c.footprint,
                "mpn": c.attributes.get("MPN", ""),
                "value": c.attributes.get("value", ""),
                "net_class": c.net_class,
                "pins": [{"name": p.name, "net": p.net} for p in c.pins],
            }
            for c in netlist.components
        ],
        "nets": [
            {"name": n.name, "pins": [[ref, name] for ref, name in n.pins]} for n in netlist.nets
        ],
    }


# ---------------------------------------------------------------------------
# Oracle 2 — _dict_to_loop_collection (loop_extractor_rs.py, verbatim)
# ---------------------------------------------------------------------------

_ORACLE_LOOP_TYPE_PRIORITY = {
    LoopType.COMMUTATION: LoopPriority.CRITICAL,
    LoopType.GATE_DRIVE_HIGH: LoopPriority.CRITICAL,
    LoopType.GATE_DRIVE_LOW: LoopPriority.CRITICAL,
    LoopType.BOOTSTRAP: LoopPriority.HIGH,
}

_ORACLE_LOOP_TYPE_EVENTS = {
    LoopType.COMMUTATION: {
        "di_dt": 1.0e9,
        "dv_dt": 5.0e9,
        "frequency_hz": 25000.0,
        "peak_current_a": 30.0,
    },
    LoopType.GATE_DRIVE_HIGH: {
        "di_dt": 1.0e8,
        "frequency_hz": 25000.0,
    },
    LoopType.GATE_DRIVE_LOW: {
        "di_dt": 1.0e8,
        "frequency_hz": 25000.0,
    },
    LoopType.BOOTSTRAP: {
        "frequency_hz": 25000.0,
        "peak_current_a": 0.5,
    },
}

_ORACLE_LOOP_TYPE_RETURN_LAYER = {
    LoopType.COMMUTATION: "L2_GND",
}

_ORACLE_LOOP_TYPE_RETURN_NET = {
    LoopType.COMMUTATION: "PGND",
}


def _oracle_dict_to_loop_collection(data):
    """Pre-migration ``_dict_to_loop_collection``, verbatim (loop_extractor_rs.py)."""
    from temper_placer.core.loop import Loop as PyLoop
    from temper_placer.core.loop import LoopEvent

    loops = []
    for loop_dict in data.get("loops", []):
        components = loop_dict.get("components", [])
        nets = loop_dict.get("nets", [])
        loop_type_str = loop_dict.get("loop_type", "unknown")
        max_area = loop_dict.get("max_area_mm2", 500.0)

        from temper_placer.core.loop import LoopType

        try:
            lt = LoopType(loop_type_str)
        except ValueError:
            lt = LoopType.COMMUTATION

        py_loop = PyLoop(
            name=loop_dict["name"],
            loop_type=lt,
            description=f"Extracted via Rust: {loop_dict['name']}",
            components=components,
            pins=[],  # Pins not available from Rust (no pin-tracing concept yet)
            nets=nets,
            priority=_ORACLE_LOOP_TYPE_PRIORITY.get(lt, LoopPriority.MEDIUM),
            max_area_mm2=max_area,
            events=LoopEvent(**(_ORACLE_LOOP_TYPE_EVENTS.get(lt, {}))),
            return_layer=_ORACLE_LOOP_TYPE_RETURN_LAYER.get(lt, ""),
            return_net=_ORACLE_LOOP_TYPE_RETURN_NET.get(lt, ""),
        )
        loops.append(py_loop)

    return LoopCollection(loops=loops)


# ---------------------------------------------------------------------------
# Bridge-output helpers (the wire shape the typed output must reproduce)
# ---------------------------------------------------------------------------

def _f(value):
    """Bit-exact float key."""
    return None if value is None else float(value).hex()


def _rust_bridge(netlist):
    import temper_rust_router

    result = json.loads(
        temper_rust_router.auto_extract_loops_rust(json.dumps(_netlist_to_dict(netlist)))
    )
    return result


def _wire_loop(name="auto_x", loop_type="commutation", components=None, nets=None, max_area=100.0):
    return {
        "name": name,
        "loop_type": loop_type,
        "components": components if components is not None else ["Q1", "Q2"],
        "nets": nets if nets is not None else ["N_SW", "N_GND"],
        "max_area_mm2": max_area,
    }


def _wire_result(ok=True, error=None, loops=None):
    d = {"ok": ok}
    if error is not None:
        d["error"] = error
    d["loops"] = loops if loops is not None else []
    return d


# ---------------------------------------------------------------------------
# Input marshaler — LoopExtractionInput
# ---------------------------------------------------------------------------

def _dict_canon(d):
    return canon(d)


import pytest  # noqa: E402


@pytest.mark.parametrize("netlist", [c for _, c in _CORPUS], ids=[n for n, _ in _CORPUS])
def test_input_marshaler_dict_bit_identical_to_oracle(netlist):
    """P1: ``LoopExtractionInput.from_netlist(nl).to_dict()`` is bit-identical
    to the pinned pre-migration ``_netlist_to_dict(nl)`` -- same keys, same
    order, same values (all string leaves; type-carrying canon)."""
    got = ORACLE_INPUT.from_netlist(netlist).to_dict()
    assert _dict_canon(got) == _dict_canon(_oracle_netlist_to_dict(netlist))


@pytest.mark.parametrize("netlist", [c for _, c in _CORPUS], ids=[n for n, _ in _CORPUS])
def test_input_marshaler_json_bit_identical_to_json_dumps(netlist):
    """The bridge takes JSON; ``to_json()`` must produce byte-identical bytes
    to the pre-migration ``json.dumps(_netlist_to_dict(nl))`` (CPython's own
    ``dumps``, so separators/ordering are CPython's)."""
    got = ORACLE_INPUT.from_netlist(netlist).to_json()
    assert got == json.dumps(_oracle_netlist_to_dict(netlist))


@pytest.mark.parametrize("seed", range(len(_RANDOM_CORPUS)))
def test_randomized_input_marshaler_bit_identical(seed):
    """30 seeded random half bridges through the typed input marshaler."""
    netlist = _RANDOM_CORPUS[seed]
    got = ORACLE_INPUT.from_netlist(netlist).to_dict()
    assert _dict_canon(got) == _dict_canon(_oracle_netlist_to_dict(netlist))


def test_topology_hints_wire_presence():
    """topology_hints appear as a trailing dict key only when passed; the
    components/nets surface is unchanged either way."""
    nl = _full_half_bridge()
    hints = {"topology": "half_bridge"}
    with_hints = ORACLE_INPUT.from_netlist(nl, hints).to_dict()
    without = ORACLE_INPUT.from_netlist(nl).to_dict()
    assert list(with_hints)[-1] == "topology_hints"
    assert with_hints["topology_hints"] == hints
    assert "topology_hints" not in without
    assert _dict_canon(with_hints["components"]) == _dict_canon(
        _oracle_netlist_to_dict(nl)["components"]
    )
    assert _dict_canon(with_hints["nets"]) == _dict_canon(_oracle_netlist_to_dict(nl)["nets"])


def test_topology_hints_in_typed_json_round_trip():
    """to_json() with hints carries them through the same dict path."""
    nl = _full_half_bridge()
    hints = {"topology": "half_bridge"}
    parsed = json.loads(ORACLE_INPUT.from_netlist(nl, hints).to_json())
    assert parsed["topology_hints"] == hints
    assert parsed["components"] == _oracle_netlist_to_dict(nl)["components"]


# ---------------------------------------------------------------------------
# Output marshaler — LoopExtractionOutput
# ---------------------------------------------------------------------------

def test_output_typed_parse_matches_raw_bridge_dict():
    """The typed output surface (ok/error/loops with name/loop_type/
    components/nets/max_area_mm2) reproduces the raw bridge dict exactly."""
    result = _rust_bridge(_full_half_bridge())
    out = ORACLE_OUTPUT.from_dict(result)
    assert out.ok is result["ok"]
    assert out.error == result.get("error")
    assert len(out.loops) == len(result["loops"])
    for typed, raw in zip(out.loops, result["loops"]):
        assert typed.name == raw["name"]
        assert typed.loop_type == raw["loop_type"]
        assert list(typed.components) == raw["components"]
        assert list(typed.nets) == raw["nets"]
        assert _f(typed.max_area_mm2) == _f(raw["max_area_mm2"])


def test_output_from_json_matches_from_dict():
    result = _rust_bridge(_full_half_bridge())
    from_json = ORACLE_OUTPUT.from_json(json.dumps(result))
    from_dict = ORACLE_OUTPUT.from_dict(result)
    assert from_json.ok == from_dict.ok
    assert from_json.error == from_dict.error
    assert len(from_json.loops) == len(from_dict.loops)
    for a, b in zip(from_json.loops, from_dict.loops):
        assert a.name == b.name
        assert a.loop_type == b.loop_type
        assert _f(a.max_area_mm2) == _f(b.max_area_mm2)


def test_output_error_path_typed_surface():
    err = ORACLE_OUTPUT.from_dict({"ok": False, "error": "NoHalfBridge", "loops": []})
    assert err.ok is False
    assert err.error == "NoHalfBridge"
    assert len(err.loops) == 0

    defaults = ORACLE_OUTPUT.from_dict({})
    assert defaults.ok is False
    assert defaults.error is None
    assert len(defaults.loops) == 0


def test_output_parse_applies_documented_defaults():
    """Per-loop wire defaults the shim's reconstruction relied on: missing
    components/nets -> [], missing max_area_mm2 -> 500.0, missing loop_type
    -> "unknown" (which the reconstruction maps to COMMUTATION)."""
    out = ORACLE_OUTPUT.from_dict(
        _wire_result(loops=[{"name": "auto_x"}])
    )
    assert len(out.loops) == 1
    loop = out.loops[0]
    assert list(loop.components) == []
    assert list(loop.nets) == []
    assert loop.loop_type == "unknown"
    assert _f(loop.max_area_mm2) == _f(500.0)


# ---------------------------------------------------------------------------
# Shim reconstruction through the typed parse vs the pinned oracle
# ---------------------------------------------------------------------------

def _loop_canon(loop):
    return (
        loop.name,
        loop.loop_type.value,
        tuple(loop.components),
        tuple(loop.nets),
        _f(loop.max_area_mm2),
        loop.priority,
        (
            _f(loop.events.di_dt),
            _f(loop.events.dv_dt),
            _f(loop.events.frequency_hz),
            _f(loop.events.peak_current_a),
        ),
        loop.return_layer,
        loop.return_net,
        tuple(loop.pins),
    )


@pytest.mark.parametrize("netlist", [c for _, c in _CORPUS], ids=[n for n, _ in _CORPUS])
def test_shim_reconstruction_through_typed_parse_matches_oracle(netlist):
    """After Phase A the shim's ``_dict_to_loop_collection`` reads the typed
    ``LoopExtractionOutput``; the reconstructed Loop objects must match the
    pinned pre-migration reconstruction field-for-field (PRESERVED +
    RECONSTRUCTED; ``pins`` is a documented LOST field -> always [])."""
    result = _rust_bridge(netlist)
    assert result.get("ok") is True

    recon = _dict_to_loop_collection(result)
    oracle = _oracle_dict_to_loop_collection(result)

    recon_by_name = {loop.name: loop for loop in recon.loops}
    oracle_by_name = {loop.name: loop for loop in oracle.loops}
    assert set(recon_by_name) == set(oracle_by_name)

    for name in oracle_by_name:
        r = recon_by_name[name]
        o = oracle_by_name[name]
        assert r.name == o.name
        assert r.loop_type.value == o.loop_type.value
        assert list(r.components) == list(o.components)
        assert list(r.nets) == list(o.nets)
        assert _f(r.max_area_mm2) == _f(o.max_area_mm2)
        assert r.priority == o.priority
        assert _f(r.events.di_dt) == _f(o.events.di_dt)
        assert _f(r.events.dv_dt) == _f(o.events.dv_dt)
        assert _f(r.events.frequency_hz) == _f(o.events.frequency_hz)
        assert _f(r.events.peak_current_a) == _f(o.events.peak_current_a)
        assert r.return_layer == o.return_layer
        assert r.return_net == o.return_net
        # LOST fields: pins always dropped by the bridge.
        assert r.pins == []


@pytest.mark.parametrize("loop_type", ["commutation", "gate_drive_high", "gate_drive_low", "bootstrap"])
def test_shim_reconstruction_loop_type_mapping_pinned(loop_type):
    """Each bridge loop_type reconstructs to the pinned priority/events/return
    values through the typed parse (the ``_LOOP_TYPE_*`` reconstruction
    contract, exercised end-to-end)."""
    result = _wire_result(loops=[_wire_loop(loop_type=loop_type)])
    recon = _dict_to_loop_collection(result)
    oracle = _oracle_dict_to_loop_collection(result)
    assert _loop_canon(recon.loops[0]) == _loop_canon(oracle.loops[0])


def test_shim_reconstruction_unknown_loop_type_defaults_to_commutation():
    """A loop_type string with no matching LoopType member falls back to
    COMMUTATION (the shim's ``except ValueError`` branch) on both sides."""
    result = _wire_result(loops=[_wire_loop(loop_type="not_a_loop_type")])
    recon = _dict_to_loop_collection(result)
    oracle = _oracle_dict_to_loop_collection(result)
    assert _loop_canon(recon.loops[0]) == _loop_canon(oracle.loops[0])
    assert recon.loops[0].loop_type == LoopType.COMMUTATION
