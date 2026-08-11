"""R1a: behavioural A/B of the Phase E batch E5 net-batching Rust
orchestration (temper-rust-router ``net_batching`` module) against the
pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase E E5: the PORTABLE
batch-loop orchestration of ``router_v6/net_batching.py`` -- net grouping
(``order_nets_for_batching``), batch construction (``_chunks``) and
budget/capacity accounting (``_shrink_channel_widths`` /
``_consume_capacity``) -- moves to ``temper-rust-router`` (pure logic in
``temper-rust-router-core``, pyo3 surface in ``temper-rust-router``); the
module keeps its public API as a delegation shim.  The pre-migration
implementation is pinned VERBATIM as
``tests/router_v6/_net_batching_py_oracle.py`` (byte-identical snapshot at
the dispatch base, origin/main cfc9415c1; content-hash pinned in
``scripts/oracle_hashes.json`` AND in this file's body digest).  Both arms
are driven with IDENTICAL inputs; every assertion is bit-exact (floats via
``float.hex()`` via ``canon``).

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` +
``test_shim_delegates_to_rust`` assert each shim function is genuinely
bound to a ``temper_rust_router`` pyfunction (monkeypatched and observed to
be called), not resolving back onto the oracle.

Covered orchestrations:

- ``net_batching.order_nets_for_batching`` vs ``net_batching::net_batch_order_py``
- ``net_batching._chunks``                    vs ``net_batching::chunk_indices_py``
- ``net_batching._shrink_channel_widths``     vs ``net_batching::shrink_channel_widths_py``
- ``net_batching._consume_capacity``          vs ``net_batching::consume_capacity_py``

The pieces that stay Python (the subprocess driver ``_run_target_in_subprocess`` /
``_batch_worker_entry`` / ``_write_shared_context`` / ``_watch_peak_rss_kb``,
the solve dispatch ``_solve_subset``, ``run_net_batched_stage3`` and the
``NetBatchResult`` evidence records) are NOT differential surface; the
existing ``test_net_batching_subprocess.py`` covers them.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from types import SimpleNamespace

import pytest
import temper_rust_router as _rtr

from temper_placer.core.netlist import Net
from temper_placer.router_v6 import net_batching as _shim
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.topology_extraction import NetTopology
from tests.core._contract_canon import canon
from tests.router_v6 import _net_batching_py_oracle as _oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_net_batching_py_oracle.py")


def test_oracle_body_matches_pinned_digest() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied bodies are content-addressed. If this fails,
    either the oracle was edited (revert it) or a pre-migration module's
    source really changed upstream (re-pin deliberately, in its own commit).
    """
    text = _ORACLE_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == "ff481f6e45a50ade9822e4806426801a9e6520163ae256899f9646cde77d32c8", (
        "the pinned oracle file changed; it must stay verbatim "
        "(see scripts/oracle_hashes.json for the registered hash)"
    )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the Rust kernels must exist, and the shim's Python
    functions must not be the oracle's functions."""
    for name in ("net_batch_order_py", "chunk_indices_py",
                 "shrink_channel_widths_py", "consume_capacity_py"):
        assert hasattr(_rtr, name), (
            f"temper_rust_router.{name} is missing: the Rust port has not "
            "been built (G1 RED). Rebuild via maturin develop after "
            "net_batching.rs lands."
        )
    assert _shim.order_nets_for_batching is not _oracle.order_nets_for_batching
    assert _shim._chunks is not _oracle._chunks
    assert _shim._shrink_channel_widths is not _oracle._shrink_channel_widths
    assert _shim._consume_capacity is not _oracle._consume_capacity


def test_shim_delegates_to_rust(monkeypatch) -> None:
    """Anti-vacuity, stronger: each shim function must actually invoke the
    Rust pyfunction (observed via a counting wrapper), not re-implement the
    oracle in Python."""
    for py_name, shim_fn, args in (
        ("net_batch_order_py", _shim.order_nets_for_batching,
         ([Net(name="A", pins=[])], None)),
        ("chunk_indices_py", _shim._chunks, ([1, 2, 3], 2)),
        ("shrink_channel_widths_py", _shim._shrink_channel_widths,
         ({"F.Cu": _make_widths({"F.Cu": {((0.0, 0.0), (1.0, 0.0)): 2.5}})["F.Cu"]},
          {"e1": 0.5}, {"e1": ("F.Cu", (0.0, 0.0), (1.0, 0.0))})),
        ("consume_capacity_py", _shim._consume_capacity,
         ({}, {"N1": _net_topo("N1", ["e1"])}, [_make_net("N1", 1)],
          _fake_rules({"N1": (0.3, 0.2)}))),
    ):
        calls: list = []
        real = getattr(_rtr, py_name)
        monkeypatch.setattr(_rtr, py_name, lambda *a, **k: (calls.append(a), real(*a, **k))[1])
        shim_fn(*args)
        assert calls, f"{shim_fn.__name__} did not call temper_rust_router.{py_name}"


# ---------------------------------------------------------------------------
# Builders (identical inputs for both arms)
# ---------------------------------------------------------------------------


def _make_net(name: str, pin_count: int, hub_ref: str | None = None) -> Net:
    pins = [(f"U{i}", f"P{j}") for j in range(pin_count)]
    if hub_ref is not None:
        pins.append((hub_ref, "P0"))
    return Net(name=name, pins=pins)


def _make_widths(spec: dict[str, dict[tuple[tuple[float, float], tuple[float, float]], float]]) -> dict[str, ChannelWidths]:
    out = {}
    for layer, edge_widths in spec.items():
        vals = list(edge_widths.values())
        out[layer] = ChannelWidths(
            layer_name=layer,
            node_widths={},
            edge_widths=dict(edge_widths),
            min_width=min(vals) if vals else 0.0,
            max_width=max(vals) if vals else 0.0,
            avg_width=(sum(vals) / len(vals)) if vals else 0.0,
        )
    return out


def _net_topo(name: str, uses_channels: list[str]) -> NetTopology:
    return NetTopology(
        net_name=name,
        path_graph=None,
        uses_channels=list(uses_channels),
        total_length_estimate=0.0,
    )


def _fake_rules(widths: dict[str, tuple[float, float]]) -> SimpleNamespace:
    """Duck-typed design-rules stand-in: get_rules_for_net(name) ->
    (trace_width_mm, clearance_mm) via a SimpleNamespace rule."""
    rules = {}
    for name, (tw, cl) in widths.items():
        rules[name] = SimpleNamespace(trace_width_mm=tw, clearance_mm=cl)
    return SimpleNamespace(
        get_rules_for_net=lambda n: rules.get(n, SimpleNamespace(trace_width_mm=0.25, clearance_mm=0.2))
    )


# ---------------------------------------------------------------------------
# order_nets_for_batching — net grouping
# ---------------------------------------------------------------------------


def _random_nets(rng: random.Random, n: int) -> list[Net]:
    names = set()
    while len(names) < n:
        names.add(f"NET{len(names)}")
    names = sorted(names)
    return [_make_net(name, rng.randint(0, 8)) for name in names]


def _random_nets_with_pairs(rng: random.Random, n_pairs: int) -> list[Net]:
    nets = []
    base = 0
    for p in range(n_pairs):
        nets.append(_make_net(f"PAIR{p}_P", rng.randint(1, 6)))
        nets.append(_make_net(f"PAIR{p}_N", rng.randint(1, 6)))
    for i in range(4):
        nets.append(_make_net(f"SOLO{i}", rng.randint(0, 8)))
    rng.shuffle(nets)
    return nets


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_order_nets_for_batching_matches_oracle(seed: int) -> None:
    rng = random.Random(seed)
    nets = _random_nets(rng, rng.randint(1, 40))
    if seed % 2 == 0:
        nets = _random_nets_with_pairs(rng, rng.randint(1, 4))
    expected = _oracle.order_nets_for_batching(nets, None)
    got = _shim.order_nets_for_batching(nets, None)
    assert got == expected


def test_order_nets_with_hub_blocks_matches_oracle(tmp_path) -> None:
    refs_blocks = {"U1": "mcu", "U2": "safety", "U3": "power_in", "U4": "mcu", "U5": "tank"}
    pcb_path = _write_pcb(tmp_path, refs_blocks)
    nets = [
        _make_net("HUB1", 3, "U1"),
        _make_net("HUB2", 2, "U2"),
        _make_net("LOW1", 1, "U3"),
        _make_net("LOW2", 4, "U5"),
        _make_net("HUB3", 5, "U4"),
    ]
    expected = _oracle.order_nets_for_batching(nets, pcb_path)
    got = _shim.order_nets_for_batching(nets, pcb_path)
    assert got == expected


def test_order_nets_with_diff_pairs_matches_oracle(tmp_path) -> None:
    rng = random.Random(42)
    nets = _random_nets_with_pairs(rng, 3)
    pcb_path = _write_pcb(tmp_path, {"U9": "mcu"})
    expected = _oracle.order_nets_for_batching(nets, pcb_path)
    got = _shim.order_nets_for_batching(nets, pcb_path)
    assert got == expected


def test_order_nets_empty_and_single() -> None:
    assert _shim.order_nets_for_batching([], None) == _oracle.order_nets_for_batching([], None)
    nets = [_make_net("ONLY", 2)]
    assert _shim.order_nets_for_batching(nets, None) == _oracle.order_nets_for_batching(nets, None)


# ---------------------------------------------------------------------------
# _chunks — batch construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [-3, 0, 1, 2, 3, 7, 10, 100])
@pytest.mark.parametrize("n", [0, 1, 5, 23])
def test_chunks_match_oracle(size: int, n: int) -> None:
    order = list(range(n))
    expected = list(_oracle._chunks(order, size))
    got = list(_shim._chunks(order, size))
    assert got == expected


# ---------------------------------------------------------------------------
# _shrink_channel_widths — budget accounting (capacity carry-forward)
# ---------------------------------------------------------------------------


def _random_edges(rng: random.Random, n: int) -> list[tuple[float, float]]:
    pts = set()
    while len(pts) < n:
        pts.add((round(rng.uniform(-10, 10), 3), round(rng.uniform(-10, 10), 3)))
    return sorted(pts)


def _edge_id(layer: str, u: tuple[float, float], v: tuple[float, float]) -> str:
    return f"{layer}:{u}-{v}"


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7])
def test_shrink_channel_widths_matches_oracle(seed: int) -> None:
    rng = random.Random(seed)
    layers = ["F.Cu", "B.Cu"] if seed % 2 == 0 else ["F.Cu"]
    spec = {}
    for layer in layers:
        edges = {}
        for u, v in zip(_random_edges(rng, 8), _random_edges(rng, 8)):
            edges[(u, v)] = round(rng.uniform(0.0, 4.0), 3)
        spec[layer] = edges
    channel_widths = _make_widths(spec)

    edge_lookup = {}
    for layer, edges in spec.items():
        for (u, v) in edges:
            edge_lookup[_edge_id(layer, u, v)] = (layer, u, v)

    consumed = {}
    for eid in list(edge_lookup.keys())[: rng.randint(0, len(edge_lookup))]:
        consumed[eid] = round(rng.uniform(0.0, 5.0), 3)

    expected = _oracle._shrink_channel_widths(channel_widths, consumed, edge_lookup)
    got = _shim._shrink_channel_widths(channel_widths, consumed, edge_lookup)
    assert canon(expected) == canon(got)


def test_shrink_channel_widths_empty_consumed_is_identity() -> None:
    widths = _make_widths({"F.Cu": {((0.0, 0.0), (1.0, 0.0)): 2.5}})
    edge_lookup = {"e1": ("F.Cu", (0.0, 0.0), (1.0, 0.0))}
    expected = _oracle._shrink_channel_widths(widths, {}, edge_lookup)
    got = _shim._shrink_channel_widths(widths, {}, edge_lookup)
    assert got is widths
    assert expected is widths


def test_shrink_channel_widths_reversed_edge_matches_oracle() -> None:
    """A consumed edge whose lookup is the reverse orientation of the
    stored edge key must still match (the oracle's `elif (v, u) in` arm)."""
    widths = _make_widths({"F.Cu": {((1.0, 0.0), (0.0, 0.0)): 2.5}})
    edge_lookup = {"e1": ("F.Cu", (0.0, 0.0), (1.0, 0.0))}
    consumed = {"e1": 0.7}
    expected = _oracle._shrink_channel_widths(widths, consumed, edge_lookup)
    got = _shim._shrink_channel_widths(widths, consumed, edge_lookup)
    assert canon(expected) == canon(got)


def test_shrink_channel_widths_unknown_layer_and_edge_skipped() -> None:
    widths = _make_widths({"F.Cu": {((0.0, 0.0), (1.0, 0.0)): 2.5}})
    edge_lookup = {
        "e1": ("B.Cu", (0.0, 0.0), (1.0, 0.0)),  # layer not in channel_widths
        "e2": ("F.Cu", (5.0, 5.0), (6.0, 6.0)),  # edge not in channel_widths
    }
    consumed = {"e1": 1.0, "e2": 2.0}
    expected = _oracle._shrink_channel_widths(widths, consumed, edge_lookup)
    got = _shim._shrink_channel_widths(widths, consumed, edge_lookup)
    assert canon(expected) == canon(got)


# ---------------------------------------------------------------------------
# _consume_capacity — budget accounting (per-net width consumption)
# ---------------------------------------------------------------------------


def _random_topo(rng: random.Random, names: list[str]) -> dict[str, NetTopology]:
    out = {}
    for name in names:
        out[name] = _net_topo(name, [f"e{ rng.randint(0, 5) }" for _ in range(rng.randint(0, 4))])
    return out


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7])
def test_consume_capacity_matches_oracle(seed: int) -> None:
    rng = random.Random(seed)
    names = [f"N{i}" for i in range(rng.randint(1, 8))]
    topo = _random_topo(rng, names)
    subset = [n for n in names if rng.random() < 0.7]
    nets = [_make_net(n, 1) for n in names]
    rules = {n: (round(rng.uniform(0.1, 1.0), 3), round(rng.uniform(0.05, 0.5), 3)) for n in names}
    design_rules = _fake_rules(rules)

    consumed_o: dict[str, float] = {}
    consumed_s: dict[str, float] = {}
    _oracle._consume_capacity(consumed_o, topo, [n for n in nets if n.name in subset], design_rules)
    _shim._consume_capacity(consumed_s, topo, [n for n in nets if n.name in subset], design_rules)
    assert consumed_o == consumed_s


def test_consume_capacity_incremental_matches_oracle() -> None:
    """The batch loop's real shape: consume over batch A, then batch B. The
    second call must see the first call's results."""
    topo_a = {"N1": _net_topo("N1", ["e1", "e2"]), "N2": _net_topo("N2", ["e1"])}
    topo_b = {"N3": _net_topo("N3", ["e2", "e3"])}
    rules = _fake_rules({"N1": (0.5, 0.2), "N2": (0.3, 0.1), "N3": (0.4, 0.15)})
    nets_a = [_make_net("N1", 1), _make_net("N2", 1)]
    nets_b = [_make_net("N3", 1)]

    c_o: dict[str, float] = {}
    c_s: dict[str, float] = {}
    for topo, nets in ((topo_a, nets_a), (topo_b, nets_b)):
        _oracle._consume_capacity(c_o, topo, nets, rules)
        _shim._consume_capacity(c_s, topo, nets, rules)
    assert c_o == c_s


def test_consume_capacity_none_rules_is_noop() -> None:
    topo = {"N1": _net_topo("N1", ["e1"])}
    nets = [_make_net("N1", 1)]
    c_o: dict[str, float] = {"existing": 1.0}
    c_s: dict[str, float] = {"existing": 1.0}
    _oracle._consume_capacity(c_o, topo, nets, None)
    _shim._consume_capacity(c_s, topo, nets, None)
    assert c_o == c_s == {"existing": 1.0}


def test_consume_capacity_net_not_in_subset_is_skipped() -> None:
    topo = {"N1": _net_topo("N1", ["e1"])}
    rules = _fake_rules({"N1": (0.5, 0.2)})
    # subset does NOT contain N1 -> nothing consumed
    c_o: dict[str, float] = {}
    c_s: dict[str, float] = {}
    _oracle._consume_capacity(c_o, topo, [_make_net("OTHER", 1)], rules)
    _shim._consume_capacity(c_s, topo, [_make_net("OTHER", 1)], rules)
    assert c_o == c_s == {}


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------


def _write_pcb(tmp_path: Path, refs_blocks: dict[str, str]) -> Path:
    parts = []
    for ref, block in refs_blocks.items():
        parts.append(
            f'\n (footprint "{ref}"\n'
            f'   (property "Reference" "{ref}")\n'
            f'   (property "Sheetpath" "{block}.x")\n'
            f' )'
        )
    p = tmp_path / "board.kicad_pcb"
    p.write_text("(kicad_pcb (version 20240108)\n" + "".join(parts) + "\n)", encoding="utf-8")
    return p
