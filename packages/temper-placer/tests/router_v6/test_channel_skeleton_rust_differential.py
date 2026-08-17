"""Differential tests: Rust medial-axis extraction (Wave 4) vs the pinned
pre-migration Python (shapely/GEOS Voronoi) for
``temper_placer/router_v6/channel_skeleton.py``.

Background -- why this file was blocked, and what changed
------------------------------------------------------------
Three prior documents recorded ``channel_skeleton.py`` as BLOCKED, most
recently ``docs/evidence/2026-08-07-channel-skeleton-triage-no-port.md``
(PR #870). The recorded blocker was never the shapely/GEOS Voronoi itself:
the 2026-08-04 spike
(``docs/evidence/2026-08-04-shapely-voronoi-channel-skeleton-spike.md``)
measured an independent (Qhull) Voronoi reproducing the GEOS skeleton to
<1e-9 mm on 12/12 synthetic boards. The actual blocker was in
``constraint_model.py``: SAT channel-edge identity was built from
``enumerate(skeleton.graph.edges)`` (networkx INSERTION ORDER) plus the raw
float ``repr()`` of both endpoints -- unsatisfiable by *any*
reimplementation, bit-exact geometry or not.

``fix/constraint-model-edge-identity`` (branched from directly, since it is
not yet on ``main``) fixes this: ``constraint_model.canonical_channel_edges``
now derives identity from endpoints quantised to 1e-6 mm, ordered by that
quantised key. Geometry agreeing to better than 1e-6 mm therefore yields
identical SAT variable names regardless of implementation.

This migration re-verified the spike's claim (not inherited) before
porting: 12/12 synthetic boards agree at the 1e-6 mm node-set level AND
directly on ``canonical_channel_edges()``-style ids computed independently
over a GEOS-built graph and a Qhull-built graph. The tests below repeat
that check against the ACTUAL Rust implementation (spade, not Qhull).

What this suite compares
-------------------------
* ``ORACLE._extract_medial_axis_single`` -- the pinned, verbatim
  pre-migration Python (GEOS Voronoi via shapely).
* the SHIPPED ``channel_skeleton._extract_medial_axis_single`` -- now a
  thin wrapper delegating to ``temper_geometry.extract_medial_axis_single_py``
  (spade Voronoi, Rust).

Both arms' output lines are fed through the SAME, unmigrated
``_ensure_skeleton_connectivity`` (live import, not re-pinned -- see the
oracle module's docstring) to build directly comparable ``nx.Graph``
skeletons, exactly mirroring what ``extract_channel_skeleton`` does in
production.

The decisive test is not geometric agreement alone -- it is
``test_canonical_channel_edges_identical_rust_vs_python``: the exact
contract that blocked this file for three prior triage passes.
"""

from __future__ import annotations

import ast
import random
import subprocess
from pathlib import Path

import tests.graph_fixtures as nx
import pytest
import temper_geometry as _tg
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

import tests.router_v6._channel_skeleton_py_oracle as ORACLE
from temper_placer.router_v6.channel_skeleton import (
    _ensure_skeleton_connectivity,
)
from temper_placer.router_v6.channel_skeleton import (
    _extract_medial_axis_single as shipped_extract_medial_axis_single,
)
from temper_placer.router_v6.constraint_model import canonical_channel_edges

# ===========================================================================
# G1 evidence: oracle is a verbatim pin
# ===========================================================================

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ORACLE_PIN_SHA = "580b8dce4574cc37108477fd8fd70a46d54d9ddd"


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
    """Every pinned definition is character-identical to the pin commit."""
    original_src = _git_show(
        "packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py"
    )
    with open(ORACLE.__file__, encoding="utf-8") as fh:
        oracle_src = fh.read()

    names = ("_extract_medial_axis", "_extract_medial_axis_single")
    original = _segments_from_source(original_src, names)
    copied = _segments_from_source(oracle_src, names)

    for name in names:
        assert name in copied, f"{name} missing from the oracle module"
        assert name in original, f"{name} missing from the pin commit"
        assert copied[name] == original[name], (
            f"{name} in the oracle is NOT verbatim -- the pin is broken and "
            f"the differential proves nothing"
        )


# ===========================================================================
# Rust symbols checklist
# ===========================================================================


def test_rust_symbols_exist():
    assert hasattr(_tg, "extract_medial_axis_single_py"), (
        "pending Rust: temper_geometry.extract_medial_axis_single_py does not exist"
    )
    assert hasattr(_tg, "extract_medial_axis_py"), (
        "pending Rust: temper_geometry.extract_medial_axis_py does not exist"
    )


# ===========================================================================
# The shipped module actually delegates (not just "a Rust function exists
# somewhere") -- this is what item 1 of the migration brief calls "a test
# asserting the SHIPPED module delegates".
# ===========================================================================


def test_shipped_module_no_longer_imports_geos_voronoi():
    """`channel_skeleton.py` must not import shapely's `voronoi_diagram` at
    module scope any more -- if it does, the shipped code is still running
    GEOS, not Rust, no matter what temper_geometry exports."""
    import temper_placer.router_v6.channel_skeleton as shipped_mod

    assert not hasattr(shipped_mod, "voronoi_diagram"), (
        "channel_skeleton.py still imports shapely.ops.voronoi_diagram -- "
        "the shipped module does not delegate to Rust"
    )
    assert shipped_mod._tg is _tg


def test_shipped_extract_medial_axis_single_calls_the_rust_symbol():
    """Observe the delegation directly: a real invocation of the shipped
    `_extract_medial_axis_single` must call
    `temper_geometry.extract_medial_axis_single_py`."""
    import temper_placer.router_v6.channel_skeleton as shipped_mod

    calls = []
    real_fn = _tg.extract_medial_axis_single_py

    def spy(outer, holes, tol):
        calls.append((len(outer), len(holes), tol))
        return real_fn(outer, holes, tol)

    shipped_mod._tg.extract_medial_axis_single_py = spy
    try:
        poly = box(0.0, 0.0, 20.0, 10.0)
        lines = shipped_mod._extract_medial_axis_single(poly, 0.5)
    finally:
        shipped_mod._tg.extract_medial_axis_single_py = real_fn

    assert calls, (
        "shipped _extract_medial_axis_single never called "
        "temper_geometry.extract_medial_axis_single_py -- delegation is broken"
    )
    assert lines, "delegated call produced no skeleton lines"


# ===========================================================================
# Board corpus -- mirrors the 2026-08-04 spike's generator (RoutingSpace's
# available_area = board.difference(obstacles)) so the comparison is on
# realistic, deliberately degenerate (axis-aligned, cocircular-prone) input.
# ===========================================================================


def _routing_area(seed: int, n_holes: int) -> Polygon:
    rng = random.Random(seed)
    board = box(0.0, 0.0, 40.0, 30.0)
    holes = []
    for _ in range(n_holes):
        cx = rng.uniform(4.0, 36.0)
        cy = rng.uniform(4.0, 26.0)
        w = rng.choice([1.6, 2.0, 3.0])
        h = rng.choice([1.6, 2.0, 3.0])
        holes.append(box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    area = board.difference(unary_union(holes)) if holes else board
    if isinstance(area, Polygon):
        return area
    return max(area.geoms, key=lambda p: p.area)


def _boards(n: int = 12):
    for seed in range(n):
        yield seed, _routing_area(seed, 6 + (seed % 7))


def _build_graph(lines):
    """Mirrors `extract_channel_skeleton`'s node/edge loop plus the
    live `_ensure_skeleton_connectivity` pass, so both arms are compared as
    full skeleton graphs -- exactly what production builds."""
    import temper_design_bundle_python as _tdb

    graph = _tdb.channel_skeleton_contracts.SkeletonGraph()
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i + 1]
            graph.add_node(p1, pos=p1)
            graph.add_node(p2, pos=p2)
            length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            graph.add_edge(p1, p2, weight=length)
    return _ensure_skeleton_connectivity(graph, max_bridge_distance=10.0)


# ===========================================================================
# Geometric agreement -- re-verifies the claim this migration rests on,
# against the ACTUAL Rust (spade) implementation, not the spike's Qhull
# stand-in.
# ===========================================================================


def test_rust_reproduces_geos_node_set_at_1e6mm_quantum():
    failures = []
    for seed, poly in _boards():
        oracle_lines = ORACLE._extract_medial_axis_single(poly, 0.5)
        rust_lines = shipped_extract_medial_axis_single(poly, 0.5)

        g_oracle = _build_graph(oracle_lines)
        g_rust = _build_graph(rust_lines)

        n_oracle = {tuple(round(c, 6) for c in n) for n in g_oracle.nodes}
        n_rust = {tuple(round(c, 6) for c in n) for n in g_rust.nodes}
        if n_oracle != n_rust:
            failures.append((seed, len(n_oracle ^ n_rust)))

    assert not failures, f"node-set mismatches at the 1e-6mm quantum: {failures}"


def test_rust_and_geos_edge_counts_agree():
    failures = []
    for seed, poly in _boards():
        oracle_lines = ORACLE._extract_medial_axis_single(poly, 0.5)
        rust_lines = shipped_extract_medial_axis_single(poly, 0.5)
        g_oracle = _build_graph(oracle_lines)
        g_rust = _build_graph(rust_lines)
        if g_oracle.number_of_edges() != g_rust.number_of_edges():
            failures.append(
                (seed, g_oracle.number_of_edges(), g_rust.number_of_edges())
            )
    assert not failures, f"(seed, oracle_edges, rust_edges) mismatches: {failures}"


# ===========================================================================
# THE DECISIVE TEST
# ===========================================================================


def test_canonical_channel_edges_identical_rust_vs_python():
    """canonical_channel_edges() over the Rust-built skeleton must yield the
    SAME edge ids as over the Python-built one. This is the exact contract
    that blocked this file across three prior triage passes (see module
    docstring) -- geometric agreement alone is not sufficient evidence."""
    mismatches = []
    for seed, poly in _boards():
        oracle_lines = ORACLE._extract_medial_axis_single(poly, 0.5)
        rust_lines = shipped_extract_medial_axis_single(poly, 0.5)

        g_oracle = _build_graph(oracle_lines)
        g_rust = _build_graph(rust_lines)

        ids_oracle = [eid for eid, _u, _v in canonical_channel_edges(g_oracle, "F.Cu")]
        ids_rust = [eid for eid, _u, _v in canonical_channel_edges(g_rust, "F.Cu")]

        if ids_oracle != ids_rust:
            mismatches.append(seed)

    assert not mismatches, (
        f"canonical_channel_edges() diverged between the Rust-built and "
        f"Python-built skeleton on boards: {mismatches}"
    )


def test_canonical_channel_edges_identical_on_simple_box():
    poly = box(0.0, 0.0, 20.0, 10.0)
    oracle_lines = ORACLE._extract_medial_axis_single(poly, 0.5)
    rust_lines = shipped_extract_medial_axis_single(poly, 0.5)

    g_oracle = _build_graph(oracle_lines)
    g_rust = _build_graph(rust_lines)

    ids_oracle = [eid for eid, _u, _v in canonical_channel_edges(g_oracle, "F.Cu")]
    ids_rust = [eid for eid, _u, _v in canonical_channel_edges(g_rust, "F.Cu")]

    assert ids_oracle == ids_rust
    assert len(ids_oracle) > 0


def test_canonical_channel_edges_identical_with_holes():
    """A board with several rectangular obstacles (holes) -- the more
    realistic RoutingSpace.available_area shape, exercising the
    outer-ring-plus-holes interior filter in both arms."""
    poly = _routing_area(seed=3, n_holes=8)
    assert list(poly.interiors), "test fixture expected to have holes"

    oracle_lines = ORACLE._extract_medial_axis_single(poly, 0.5)
    rust_lines = shipped_extract_medial_axis_single(poly, 0.5)

    g_oracle = _build_graph(oracle_lines)
    g_rust = _build_graph(rust_lines)

    ids_oracle = [eid for eid, _u, _v in canonical_channel_edges(g_oracle, "F.Cu")]
    ids_rust = [eid for eid, _u, _v in canonical_channel_edges(g_rust, "F.Cu")]

    assert ids_oracle == ids_rust
    assert len(ids_oracle) > 0
