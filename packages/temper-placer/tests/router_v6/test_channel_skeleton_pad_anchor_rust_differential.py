"""Differential: Rust pad anchoring (``temper_geometry.pad_anchor_plan_py``)
vs the pinned pre-migration Python, on ``pcb/temper.kicad_pcb``.

What moved, and why it moved now
-----------------------------------
``extract_channel_skeleton``'s "OPTION F FIX" block anchors every netted
component pad into the channel skeleton: skip the pad if some skeleton node
is already within 0.1mm of it, otherwise find the nearest skeleton node and
add an edge to it. Two nested brute-force scans over Python coordinate
tuples.

Both the medial-axis port (``channel_skeleton.rs``'s module doc) and the
oracle that accompanied it (``_channel_skeleton_py_oracle.py``) declared
this block out of scope, describing it as "dict/list bookkeeping over
``ParsedPCB.components``/``pins``, orchestration". A cProfile of a full
production route (301.04s wall, board digest ``6d4e17337bcf2633``, 4553
segments) shows what that description missed:

    channel_skeleton.py:56  extract_channel_skeleton   22.3s SELF, 6 calls
    channel_skeleton.py:159 <genexpr>                  15.2s, 97,412,627 calls

The self time is the nearest-node scan (written inline, so charged to the
enclosing function rather than to a callee); the genexpr is the dedup scan.
~37s of a 301s route, from six calls. The bookkeeping framing was accurate
about the lists and dicts and missed the two O(pads x nodes) sweeps between
them.

Measured after the port, on this tree's real routing spaces, both arms fed
the identical node snapshot: **73.42s of Python became 6.145s of Rust, 12x,
bit-exact on all six layers** (F.Cu 22.76s -> 1.716s over 115,513 nodes;
B.Cu 9.67s -> 1.131s; In1/In2 4.65/4.98s -> 0.488/0.491s; In3 15.16s ->
1.153s; In4 16.20s -> 1.167s; 523 pads throughout). That is roughly double
the profile's 37.5s -- the profiled run carried board digest
`6d4e17337bcf2633`, and this tree's skeletons are larger than its
97,412,627 genexpr evaluations imply (523 x 415,198 = ~217M comparisons
here). Both numbers are real; they are different board states, and the
measured one is the one that applies to this branch.

Why the port is deliberately still brute force
-------------------------------------------------
This is search-and-classification, not an emitted outline: "which skeleton
node is nearest" has one right answer, and a different-but-also-legal answer
is exactly what a differential exists to catch. The obvious optimisation --
reuse the ``rstar`` R*-tree already in this crate (``radius_pairs.rs``) --
is NOT taken, because the Python resolves ties to the EARLIEST node in
``skeleton_nodes`` order via a strict ``<``, and a tree's nearest-neighbour
order is its own. A verbatim transcription is bit-exact by construction and
already removes the great majority of the cost.

Two float findings this port turned up (both measured, both load-bearing)
---------------------------------------------------------------------------
1. ``d ** 2`` is NOT ``d * d``. CPython's ``**`` is libm ``pow``, and on
   ordinary board coordinates it disagrees with the multiplication by one
   ulp -- ``98.07985406973864 ** 2 == 9619.657774341229`` while
   ``98.07985406973864 * 98.07985406973864 == 9619.657774341227``. In an
   argmin over distances one ulp is enough to flip a near tie and re-anchor
   a pad to a different node. The Rust therefore calls ``host_math::pow``.
2. ``math.sqrt(s)`` is NOT ``s ** 0.5``. IEEE-754 requires ``sqrt`` to be
   correctly rounded and requires nothing of ``pow``; at
   ``s = 55489.646545994874`` they differ. Both spellings appear in
   ``channel_skeleton.py`` -- boundary sampling uses ``** 0.5``, pad
   anchoring uses ``math.sqrt`` -- so ``channel_skeleton.rs`` uses
   ``host_math::pow(_, 0.5)`` for the former and ``f64::sqrt`` for the
   latter. Both counterexamples are pinned as Rust unit tests in that file
   (``multiplication_is_not_a_valid_substitute_for_pow_at_board_scale``,
   ``math_sqrt_and_pow_half_are_not_interchangeable``).

What this suite compares
---------------------------
* ``ORACLE.extract_channel_skeleton`` -- the pinned, verbatim
  pre-migration Python, running its own two scans.
* the SHIPPED ``channel_skeleton.extract_channel_skeleton`` -- now
  delegating those scans to ``temper_geometry.pad_anchor_plan_py``.

Both arms call the SAME live ``_extract_medial_axis`` (already Rust) and the
SAME live ``_ensure_skeleton_connectivity``, so the only thing that can
differ between them is the pad anchoring. Inputs are the production board's
real routing spaces and real pad positions -- not synthetic fixtures --
because a differential only proves what you feed it, and the tie-breaking
and 0.1mm-dedup behaviour under test only get exercised at real skeleton
density (~41k nodes on an outer layer).
"""

from __future__ import annotations

import ast
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest
import temper_geometry as _tg

import tests.router_v6._channel_skeleton_pad_anchor_py_oracle as ORACLE
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.router_v6.channel_skeleton import (
    extract_channel_skeleton as shipped_extract_channel_skeleton,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PCB = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_ORACLE_PIN_SHA = "19ddbbbc8079641edbfd9fc1270a568ca54843d3"
_ORACLE_SOURCE = "packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py"

# The two literals the shipped call site passes into the Rust kernel. Named
# here so this file's own kernel-level checks cannot silently drift to a
# wider dedup box or a longer connect radius than production uses -- either
# would be a threshold change wearing a test's clothes.
_DEDUP_TOL_MM = 0.1
_MAX_CONNECT_MM = 50.0


# ===========================================================================
# G1 evidence: the oracle is a verbatim pin
# ===========================================================================


def _segments_from_source(src: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        nm = getattr(node, "name", None)
        if nm in names:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            out[nm] = "\n".join(lines[start : node.end_lineno])
    return out


def _git_show(rel: str) -> str:
    try:
        return subprocess.run(
            ["git", "show", f"{_ORACLE_PIN_SHA}:{rel}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")


def test_oracle_is_verbatim_copy():
    """The pinned definition is character-identical to the pin commit."""
    original = _segments_from_source(
        _git_show(_ORACLE_SOURCE), ("extract_channel_skeleton",)
    )
    with open(ORACLE.__file__, encoding="utf-8") as fh:
        copied = _segments_from_source(fh.read(), ("extract_channel_skeleton",))

    assert "extract_channel_skeleton" in original, "name missing from the pin commit"
    assert "extract_channel_skeleton" in copied, "name missing from the oracle module"
    assert copied["extract_channel_skeleton"] == original["extract_channel_skeleton"], (
        "the oracle is NOT verbatim -- the pin is broken and the "
        "differential proves nothing"
    )


def test_oracle_still_contains_the_scans_it_is_pinning():
    """Anti-vacuity for the pin itself.

    A verbatim-copy check passes just as happily against a pinned function
    that never contained the code under test. This asserts the two loops
    this migration replaces are actually present in the oracle's source, so
    "the oracle agrees with Rust" cannot be true merely because the oracle
    does nothing.
    """
    import inspect

    src = inspect.getsource(ORACLE.extract_channel_skeleton)
    assert "for n in skeleton_nodes" in src, "the dedup generator is not in the oracle"
    assert "for node in skeleton_nodes" in src, (
        "the nearest-node scan is not in the oracle"
    )
    assert "math.sqrt" in src, "the distance formula is not in the oracle"
    assert "< 0.1" in src and "< 50.0" in src, (
        "the dedup / max-connect thresholds are not in the oracle"
    )


def test_shipped_no_longer_contains_the_python_scans():
    """The Python was DELETED, not left in place beside the Rust.

    AGENTS.md: "never leave both in place in agreement -- two homes that
    agree today drift tomorrow". This fails if the migration ever regresses
    to keeping a Python fallback.

    Checked against the parsed AST, not the source text: the shipped
    function's comments *quote* the loops they describe, and a substring
    check cannot tell a live loop from a comment about a deleted one. (It
    could not -- this assertion failed on its own explanatory comment
    before being rewritten this way.)
    """
    import inspect
    import textwrap

    from temper_placer.router_v6 import channel_skeleton as shipped_mod

    fn = ast.parse(
        textwrap.dedent(inspect.getsource(shipped_mod.extract_channel_skeleton))
    ).body[0]

    for node in ast.walk(fn):
        if isinstance(node, (ast.For, ast.comprehension)):
            it = node.iter
            assert not (isinstance(it, ast.Name) and it.id == "skeleton_nodes"), (
                "a Python scan over skeleton_nodes is back in the shipped "
                "module -- the O(pads x nodes) sweep this migration removed"
            )
        if isinstance(node, ast.Attribute) and node.attr == "sqrt":
            raise AssertionError(
                "the Python distance formula is back in the shipped module"
            )

    called = {
        n.func.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "pad_anchor_plan_py" in called, (
        "the shipped module no longer calls the Rust kernel"
    )


def test_rust_symbol_exists():
    assert hasattr(_tg, "pad_anchor_plan_py"), (
        "pending Rust: temper_geometry.pad_anchor_plan_py does not exist"
    )


# ===========================================================================
# Real production board
# ===========================================================================


@pytest.fixture(scope="module")
def board():
    """The production board's real ParsedPCB and real per-layer routing spaces."""
    if not _PCB.exists():  # pragma: no cover
        pytest.skip(f"{_PCB} not present")
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.routing_space import compute_routing_space

    pcb = parse_kicad_pcb_v6(_PCB, use_declared_layer_roles=True)
    spaces = compute_routing_space(pcb)
    assert spaces, "the production board produced no routing spaces"
    return pcb, spaces


def _pad_positions(pcb) -> list[tuple[float, float]]:
    """The pad-position list the pinned Python builds, extracted so the
    kernel-level checks below feed the Rust exactly the production input."""
    out: list[tuple[float, float]] = []
    for comp in pcb.components:
        if not comp.initial_position or not hasattr(comp, "pins"):
            continue
        for pin in comp.pins:
            if pin.net:
                out.append(pin_world_position(pin, comp))
    return out


def _oracle_plan(
    pad_positions: list[tuple[float, float]],
    skeleton_nodes: list[tuple[float, float]],
) -> list[tuple[int, int, float]]:
    """The pinned Python's two scans, transcribed to emit the same
    ``(pad_index, node_index, dist)`` plan the Rust returns.

    Deliberately NOT imported from the oracle module: the oracle pins the
    whole ``extract_channel_skeleton``, whose scans are entangled with graph
    mutation. This isolates the decision, and
    ``test_end_to_end_graph_identical_on_real_board`` independently proves
    the entangled version agrees too, so a transcription error here cannot
    make the suite vacuous on its own.
    """
    plan: list[tuple[int, int, float]] = []
    for pad_index, pad_pos in enumerate(pad_positions):
        if any(
            abs(pad_pos[0] - n[0]) < 0.1 and abs(pad_pos[1] - n[1]) < 0.1
            for n in skeleton_nodes
        ):
            continue
        nearest_index = None
        min_dist = float("inf")
        for i, node in enumerate(skeleton_nodes):
            dist = math.sqrt((pad_pos[0] - node[0]) ** 2 + (pad_pos[1] - node[1]) ** 2)
            if dist < min_dist:
                min_dist = dist
                nearest_index = i
        if nearest_index is not None and min_dist < 50.0:
            plan.append((pad_index, nearest_index, min_dist))
    return plan


def _rust_plan(
    pad_positions: list[tuple[float, float]],
    skeleton_nodes: list[tuple[float, float]],
) -> list[tuple[int, int, float]]:
    pads_arr = np.ascontiguousarray(pad_positions, dtype=np.float64)
    nodes_arr = np.ascontiguousarray(skeleton_nodes, dtype=np.float64)
    return _tg.pad_anchor_plan_py(
        pads_arr.tobytes(),
        len(pad_positions),
        nodes_arr.tobytes(),
        len(skeleton_nodes),
        _DEDUP_TOL_MM,
        _MAX_CONNECT_MM,
    )


def test_connectivity_pass_cannot_change_the_node_set():
    """Justifies the fixture below skipping ``_ensure_skeleton_connectivity``.

    The pad loop consumes ``list(G.nodes)`` taken AFTER island bridging, so
    a fixture that skipped bridging would only be feeding production's real
    input if bridging cannot change the node set. It cannot, and the reason
    is structural rather than empirical:

    * ``_ensure_skeleton_connectivity`` mutates ``G`` through exactly one
      call, ``G.add_edge(a, b, weight=d)``.
    * ``a`` and ``b`` are ``nodes[i]`` / ``nodes[j]``, drawn from the
      ``nodes = list(G.nodes)`` snapshot it took from ``G`` itself.
    * ``SkeletonGraph.add_edge`` resolves endpoints via
      ``get_or_create_node``, which for an already-present node returns its
      existing index.

    So every endpoint it can ever pass is already a node. Asserted here
    against the AST rather than trusted from a comment -- if someone later
    adds an ``add_node`` or bridges to a computed midpoint, the fixture
    silently stops representing production and this test says so.

    Skipping bridging matters because it is by far the most expensive part
    of the stage (a radius query over ~44M node pairs plus a vectorized
    shapely predicate over ~2.6M candidate segments per outer layer, tens of
    GB of RSS) and contributes nothing to what is under test here. The
    end-to-end test below runs the real thing, bridging included, so nothing
    is taken on faith.
    """
    import inspect
    import textwrap

    from temper_placer.router_v6 import channel_skeleton as mod

    fn = ast.parse(
        textwrap.dedent(inspect.getsource(mod._ensure_skeleton_connectivity))
    ).body[0]

    mutations = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"add_edge", "add_node"}
    ]
    assert mutations, (
        "no graph mutation found at all -- either the function changed shape "
        "or this scan is broken; either way the fixture's premise is unproven"
    )
    # Names bound, anywhere in the function, to an element of the `nodes`
    # snapshot -- the source writes `a, b = nodes[i], nodes[j]` and then
    # `G.add_edge(a, b, ...)`, so the endpoints reach `add_edge` through a
    # local rather than as a literal subscript.
    def _is_node_index(expr: ast.expr) -> bool:
        return (
            isinstance(expr, ast.Subscript)
            and isinstance(expr.value, ast.Name)
            and expr.value.id == "nodes"
        )

    from_nodes: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            targets = tgt.elts if isinstance(tgt, ast.Tuple) else [tgt]
            values = (
                node.value.elts
                if isinstance(node.value, ast.Tuple)
                and len(node.value.elts) == len(targets)
                else [node.value] * len(targets)
            )
            for t, v in zip(targets, values, strict=True):
                if isinstance(t, ast.Name) and _is_node_index(v):
                    from_nodes.add(t.id)

    assert from_nodes, (
        "nothing in _ensure_skeleton_connectivity is bound from the `nodes` "
        "snapshot -- the fixture's premise is unproven"
    )

    for call in mutations:
        assert call.func.attr != "add_node", (
            "_ensure_skeleton_connectivity now adds NODES; the fixture below "
            "no longer sees production's node set and must run the bridging "
            "pass again"
        )
        for arg in call.args[:2]:
            ok = _is_node_index(arg) or (
                isinstance(arg, ast.Name) and arg.id in from_nodes
            )
            assert ok, (
                f"add_edge endpoint {ast.dump(arg)} does not come from the "
                f"`nodes` snapshot, so bridging may now create a node the "
                f"fixture below would never see"
            )


@pytest.fixture(scope="module")
def real_layer_inputs(board):
    """Real skeleton nodes (pre-anchoring) and real pad positions, per layer.

    This is exactly the ``list(G.nodes)`` snapshot the pad loop consumes in
    production. Island bridging is skipped -- see
    ``test_connectivity_pass_cannot_change_the_node_set``, which proves from
    the AST that bridging only ever adds edges between nodes that already
    exist, so it cannot alter what this fixture produces. It is skipped
    because it dominates the stage's cost and none of it reaches the code
    under test.
    """
    from temper_placer.router_v6 import channel_skeleton as mod

    pcb, spaces = board
    pads = _pad_positions(pcb)
    assert pads, "the production board produced no netted pads"

    out = {}
    for layer_name, rs in sorted(spaces.items()):
        area = rs.available_area
        if area.is_empty:
            continue
        G = mod.SkeletonGraph()
        for line in mod._extract_medial_axis(area, 0.5):
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                p1, p2 = coords[i], coords[i + 1]
                G.add_node(p1, pos=p1)
                G.add_node(p2, pos=p2)
                dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                G.add_edge(p1, p2, weight=(dx**2 + dy**2) ** 0.5)
        if G.number_of_nodes() == 0:
            continue
        out[layer_name] = (pads, list(G.nodes))
    assert out, "no layer produced a non-empty skeleton on the production board"
    return out


def test_the_real_board_actually_exercises_the_hot_path(real_layer_inputs):
    """Anti-vacuity for the fixture.

    The behaviours under test (0.1mm dedup, tie-breaking, the 50mm cutoff)
    only appear at real skeleton density. If this board ever presented a
    handful of nodes, every assertion below would pass trivially. Pin the
    scale the profile measured: six-figure comparison counts, tens of
    thousands of nodes on the outer layers.
    """
    total_comparisons = 0
    for _layer, (pads, nodes) in real_layer_inputs.items():
        total_comparisons += len(pads) * len(nodes)
    assert len(real_layer_inputs) >= 4, (
        f"expected the 4-layer board's routable layers, got "
        f"{sorted(real_layer_inputs)}"
    )
    assert total_comparisons > 10_000_000, (
        f"the fixture is too small to exercise the scan this migration "
        f"replaced ({total_comparisons} pad x node comparisons)"
    )


def test_pad_anchor_plan_identical_on_real_board(real_layer_inputs):
    """Bit-exact agreement on the production board, per layer.

    Compares the whole decision: which pads are anchored, in which order,
    to which node INDEX (not merely to a node at the same distance -- ties
    are real here and index order is the contract), and at exactly which
    float distance.
    """
    for layer_name, (pads, nodes) in sorted(real_layer_inputs.items()):
        want = _oracle_plan(pads, nodes)
        got = _rust_plan(pads, nodes)

        assert [p for p, _, _ in got] == [p for p, _, _ in want], (
            f"{layer_name}: different pads anchored, or in a different order"
        )
        assert [n for _, n, _ in got] == [n for _, n, _ in want], (
            f"{layer_name}: a pad anchored to a different skeleton node -- "
            f"tie-breaking or the distance formula diverged"
        )
        for (_, _, d_got), (_, _, d_want) in zip(got, want, strict=True):
            assert d_got.hex() == d_want.hex(), (
                f"{layer_name}: distance differs in the last bits "
                f"({d_got!r} vs {d_want!r})"
            )


def test_end_to_end_graph_identical_on_real_board(board, monkeypatch):
    """The entangled version: full ``extract_channel_skeleton``, both arms.

    Proves the migration end to end -- same nodes, same edges, same edge
    weights, and the same ``total_length`` accumulated in the same order
    (float addition is not associative, so an equal-set-but-reordered replay
    would show up here as a last-bits difference).

    Island bridging is stubbed out, IN BOTH ARMS IDENTICALLY
    -----------------------------------------------------------
    ``_ensure_skeleton_connectivity`` is replaced with a pass-through for
    the duration of this test. Three facts make that safe, and each is
    independently checked rather than asserted in prose:

    * Bridging adds only EDGES, between nodes that already exist --
      ``test_connectivity_pass_cannot_change_the_node_set`` proves this from
      the AST. The pad-anchoring block reads ``list(G.nodes)`` and nothing
      else, so its input is bit-identical either way.
    * ``extract_channel_skeleton`` does not fold bridge lengths into
      ``total_length`` (bridging happens before the pad loop and returns a
      graph, not a length), so the quantity compared below is untouched.
    * The stub is installed on BOTH the shipped module and the oracle
      module, so the two arms remain exactly comparable; the assertion
      below is about the difference between them, and a change applied
      identically to both cannot manufacture agreement.

    Why it is stubbed rather than run: with bridging live this test does not
    finish inside the repo's 1200s per-test ceiling. Bridging is by far the
    most expensive thing the stage does -- a radius query over tens of
    millions of node pairs plus a vectorized shapely predicate over ~2.6M
    candidate segments per outer layer, at tens of GB of RSS -- and it is
    run twice per layer here, once per arm. It is also, for this
    differential, entirely inert. Paying 20+ minutes and an OOM risk to
    recompute a shared constant on both sides of an equality is not rigour.

    This is a cost reduction, not a relaxation: no assertion was removed, no
    layer was skipped, and the geometry is still the production board's.
    """
    from temper_placer.router_v6 import channel_skeleton as shipped_mod

    calls = {"n": 0}

    def _passthrough(G, max_bridge_distance=5.0, available_area=None):
        calls["n"] += 1
        return G

    monkeypatch.setattr(shipped_mod, "_ensure_skeleton_connectivity", _passthrough)
    monkeypatch.setattr(ORACLE, "_ensure_skeleton_connectivity", _passthrough)

    pcb, spaces = board
    compared = 0
    for layer_name, rs in sorted(spaces.items()):
        want = ORACLE.extract_channel_skeleton(rs, pcb=pcb)
        got = shipped_extract_channel_skeleton(rs, pcb=pcb)

        assert got.node_count == want.node_count, f"{layer_name}: node count"
        assert got.edge_count == want.edge_count, f"{layer_name}: edge count"
        assert set(got.graph.nodes) == set(want.graph.nodes), f"{layer_name}: node set"
        assert got.total_length.hex() == want.total_length.hex(), (
            f"{layer_name}: total_length differs in the last bits "
            f"({got.total_length!r} vs {want.total_length!r})"
        )
        compared += 1

    assert compared >= 4, (
        f"expected to compare every routable layer of the 4-layer board, "
        f"compared {compared}"
    )
    # Anti-vacuity for the stub itself: if the patch had not taken effect on
    # BOTH arms -- e.g. because one of them stopped resolving the name
    # through its module global -- the two sides would no longer be running
    # the same pipeline, and the comparison above would be measuring the
    # wrong thing while still passing.
    assert calls["n"] == 2 * compared, (
        f"the bridging stub was invoked {calls['n']} times for {compared} "
        f"layers x 2 arms -- one arm is not going through it, so the two "
        f"sides are no longer comparable"
    )


def test_rust_honours_the_production_thresholds(real_layer_inputs):
    """The kernel must not be quietly widening the dedup box or the connect
    radius. Shrinking a keepout is a threshold change by another route, and
    so is loosening one here: re-run with tighter constants and assert the
    result genuinely changes, proving the parameters are live rather than
    ignored.
    """
    layer_name, (pads, nodes) = sorted(real_layer_inputs.items())[0]
    baseline = _rust_plan(pads, nodes)

    pads_arr = np.ascontiguousarray(pads, dtype=np.float64).tobytes()
    nodes_arr = np.ascontiguousarray(nodes, dtype=np.float64).tobytes()

    tighter_connect = _tg.pad_anchor_plan_py(
        pads_arr, len(pads), nodes_arr, len(nodes), _DEDUP_TOL_MM, 0.5
    )
    assert len(tighter_connect) < len(baseline), (
        f"{layer_name}: max_connect is not being honoured -- a 0.5mm radius "
        f"anchored just as many pads as 50mm"
    )

    wider_dedup = _tg.pad_anchor_plan_py(
        pads_arr, len(pads), nodes_arr, len(nodes), 5.0, _MAX_CONNECT_MM
    )
    assert len(wider_dedup) < len(baseline), (
        f"{layer_name}: dedup_tol is not being honoured -- a 5mm box deduped "
        f"no more pads than a 0.1mm box"
    )
