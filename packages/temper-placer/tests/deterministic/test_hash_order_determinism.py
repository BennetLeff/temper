"""Router output must not depend on PYTHONHASHSEED — runtime half of the gate.

The static half (``scripts/check_hash_order_determinism.py``) reads code and
cannot follow a hash-chosen order across a call boundary. This half runs the
real entry points in **fresh interpreters** under many explicit
``PYTHONHASHSEED`` values and compares their output byte-for-byte. Neither half
subsumes the other, and a determinism defect that survives both has to be
invisible in the source *and* silent at runtime.

Why fresh interpreters: CPython fixes the hash salt once per process
(PEP 456), so no amount of in-process repetition can observe the effect. Every
cell below spawns ``SEED_COUNT`` subprocesses.

Why ``repr()`` and not ``pytest.approx``: PR #730 found this class as a *1-ULP*
coordinate move (``59.50946904060019`` vs ``59.509469040600194``), produced by
float addition happening in a different order. A tolerance-based comparison
would have been green and blind. Comparison here is exact.

This file lives under ``tests/deterministic/`` on purpose: CI runs this package
as ``cd packages/temper-placer && pytest ... tests/deterministic/ ...``, an
invocation whose ``confcutdir`` never loads a repo-root ``conftest.py``. The
gate must be present under the invocation CI actually uses, not only under the
one a developer happens to type — so the static checker is *also* invoked from
here (``test_static_gate_passes``), and the CI wiring itself is asserted
(``test_static_gate_is_wired_into_ci``) so neither half can be quietly dropped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# 32 seeds per cell is this program's precedent (PR #730).
SEED_COUNT = 32

REPO_ROOT = Path(__file__).resolve().parents[4]
GATE = REPO_ROOT / "scripts" / "check_hash_order_determinism.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"


def _run_under_seed(snippet: str, seed: int) -> str:
    """Run ``snippet`` in a fresh interpreter with PYTHONHASHSEED=seed.

    The child inherits this process's ``sys.path`` explicitly so the test works
    both against an installed package (CI) and against a source checkout on
    ``PYTHONPATH`` (developer machines).
    """
    preamble = f"import sys; sys.path[:0] = {sys.path!r}\n"
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    proc = subprocess.run(
        [sys.executable, "-c", preamble + snippet],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    if proc.returncode != 0:
        raise AssertionError(f"child interpreter failed at PYTHONHASHSEED={seed}:\n{proc.stderr}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    assert lines, f"child produced no RESULT line at seed={seed}:\n{proc.stdout}"
    return lines[-1][len("RESULT ") :]


def _assert_seed_independent(snippet: str, what: str) -> str:
    """Assert every seed yields byte-identical output; return that output."""
    by_seed = {seed: _run_under_seed(snippet, seed) for seed in range(SEED_COUNT)}
    baseline = by_seed[0]
    disagreeing = sorted(s for s, out in by_seed.items() if out != baseline)
    assert not disagreeing, (
        f"{what} depends on PYTHONHASHSEED: {len(disagreeing)} of "
        f"{SEED_COUNT - 1} other seeds disagree with seed=0.\n"
        f"  seed=0                -> {baseline}\n"
        f"  seed={disagreeing[0]:<16} -> {by_seed[disagreeing[0]]}"
    )
    return baseline


# ---------------------------------------------------------------------------
# Defect 7 (issue #752): thermal_relief._add_smd_thermal_reliefs iterated a
# frozenset[str] of plane nets, so the emitted report's order was the salt's.
# ---------------------------------------------------------------------------

_THERMAL_SNIPPET = '''
from dataclasses import dataclass

from temper_placer.core.board import Board
from temper_placer.core.netlist import Net
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.thermal_relief import _add_smd_thermal_reliefs


@dataclass
class Pad:
    x: float
    y: float
    pad_type: str = "smd"
    width: float = 0.8
    height: float = 0.6


NET_NAMES = ["GND", "VCC", "VDD", "PGND", "AGND", "VEE", "VBAT", "DGND"]
# Netlist order is deliberately neither insertion order of the frozenset nor
# lexicographic order, so a `sorted()` "fix" would not reproduce this baseline.
NETLIST_ORDER = ["VBAT", "GND", "DGND", "VCC", "AGND", "VEE", "PGND", "VDD"]
PADS = {n: [Pad(float(i), float(i) + 0.5)] for i, n in enumerate(NET_NAMES)}


class FakeNetlist:
    nets = [Net(n, []) for n in NETLIST_ORDER]

    def get_pads_for_net(self, net_name):
        return PADS.get(net_name, [])


class BoardWithNetlist:
    """Real Board geometry, duck-typed netlist (the shape this code expects)."""

    def __init__(self):
        self._board = Board(width=100.0, height=100.0)
        self.netlist = FakeNetlist()

    def __getattr__(self, name):
        return getattr(self._board, name)


reliefs = []
_add_smd_thermal_reliefs(
    board=BoardWithNetlist(),
    _routing_results=RoutingResults(compiled_routes=[], failed_nets=[]),
    _resolved_plane_layers=["In1.Cu"],
    resolved_plane_nets=frozenset(NET_NAMES),
    spoke_count=4,
    spoke_width=0.254,
    clearance_gap=0.254,
    thermal_reliefs=reliefs,
)
print("RESULT " + repr([(r.net_name, r.pad_position, r.spoke_segments) for r in reliefs]))
'''


def test_smd_thermal_relief_order_is_seed_independent():
    out = _assert_seed_independent(
        _THERMAL_SNIPPET, "thermal_relief._add_smd_thermal_reliefs output order"
    )
    # Non-vacuity: the cell must have produced real reliefs, not an empty list
    # that trivially agrees with itself.
    assert out.count("'") >= 8, f"cell produced no thermal reliefs: {out}"


def test_smd_thermal_relief_uses_netlist_order():
    """Pin *which* order became canonical, so a later `sorted()` fails here.

    Netlist order, not lexicographic order: it is the convention
    ``heuristics.structural.identify_thermal_components`` already uses ("Return
    components in netlist order") and the index basis the rest of the pipeline
    shares. The fixture's netlist order differs from both hash order and
    alphabetical order, so only the intended fix reproduces it.
    """
    names_snippet = _THERMAL_SNIPPET.replace(
        'print("RESULT " + repr([(r.net_name, r.pad_position, r.spoke_segments) '
        "for r in reliefs]))",
        'print("RESULT " + repr([r.net_name for r in reliefs]))',
    )
    assert names_snippet != _THERMAL_SNIPPET, "snippet substitution failed"
    out = _run_under_seed(names_snippet, 0)
    assert out == repr(["VBAT", "GND", "DGND", "VCC", "AGND", "VEE", "PGND", "VDD"]), out


# ---------------------------------------------------------------------------
# Defect 6 (issue #752): channel_mapping returned a *geometric coordinate*
# derived from hash(channel_id), and a waypoint list sliced out of networkx
# insertion order.
# ---------------------------------------------------------------------------

_CHANNEL_SNIPPET = """
import tests.graph_fixtures as nx

from temper_placer.router_v6.channel_mapping import (
    _is_near_skeleton,
    _nearest_skeleton_node,
    _nearest_terminal_order,
)
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton

PTS = [(float(i), float(i) * 2.0) for i in range(8)]


def skeleton():
    g = nx.Graph()
    for a, b in zip(PTS, PTS[1:]):
        g.add_edge(a, b, weight=1.0)
    return ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=7.0)


sk = skeleton()
print("RESULT " + repr({
    # A far coordinate snaps to the nearest skeleton node (Wave 4: the
    # coordinate resolution that used to live in _parse_channel_coordinate /
    # _extract_waypoints now delegates to temper-geometry's
    # nearest_skeleton_node_py / is_near_skeleton_py / nearest_terminal_order_py).
    "snapped": _nearest_skeleton_node((100.0, 100.0), sk),
    # A coordinate near the skeleton is detected as such.
    "near": _is_near_skeleton((0.5, 1.0), sk),
    # The greedy nearest-terminal ordering over a pad list (the fallback path).
    "fallback": _nearest_terminal_order((0.0, 0.0), [(5.0, 10.0), (1.0, 2.0), (3.0, 6.0)]),
}))
"""


def test_channel_coordinate_is_seed_independent():
    out = _assert_seed_independent(_CHANNEL_SNIPPET, "channel_mapping coordinate resolution")
    # Non-vacuity: the snap, the near check, and the ordering must all have
    # produced geometry.
    assert "'snapped': (7.0, 14.0)" in out, out
    assert "'near': True" in out, out
    assert "'fallback': [(" in out, out


def test_channel_coordinate_snaps_to_nearest_node():
    """The snapped coordinate must be the *nearest* node, not an arbitrary one.

    (100.0, 100.0) is closest to (7.0, 14.0) among the fixture's eight nodes.
    The pre-fix code returned ``nodes[hash(channel_id) % len(nodes)]``, which
    landed on a different node in almost every process.
    """
    out = _run_under_seed(_CHANNEL_SNIPPET, 0)
    assert "'snapped': (7.0, 14.0)" in out, out


def test_channel_waypoint_fallback_is_insertion_order_independent():
    """The fallback must depend on the node *set*, not on how it was built."""
    snippet = """
import random

import tests.graph_fixtures as nx

from temper_placer.router_v6.channel_mapping import _nearest_skeleton_node
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton

PTS = [(float(i), float(i) * 2.0) for i in range(8)]


def skeleton(perm_seed):
    edges = list(zip(PTS, PTS[1:]))
    rnd = random.Random(perm_seed)
    edges = [(b, a) if rnd.random() < 0.5 else (a, b) for a, b in edges]
    rnd.shuffle(edges)
    g = nx.Graph()
    for a, b in edges:
        g.add_edge(a, b, weight=1.0)
    return ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=7.0)


outs = {repr(_nearest_skeleton_node((100.0, 100.0), skeleton(p))) for p in range(16)}
print("RESULT " + repr(sorted(outs)))
"""
    out = _run_under_seed(snippet, 0)
    assert out.count("(7.0, 14.0)") == 1, (
        f"_nearest_skeleton_node still depends on networkx insertion order: {out}"
    )
    assert "(7.0, 14.0)" in out, f"snap produced no node: {out}"


# ---------------------------------------------------------------------------
# The static half, invoked from inside the package CI actually runs.
# ---------------------------------------------------------------------------


def test_static_gate_exists():
    assert GATE.is_file(), (
        f"{GATE} is missing. The runtime cells above only cover entry points "
        "someone remembered to add; the static half is what covers code that "
        "does not exist yet."
    )


def test_static_gate_passes():
    """Run the static gate under this package's own pytest invocation.

    A gate wired only into a repo-root job is one `paths:` filter away from
    never running on a change to this package.
    """
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"scripts/check_hash_order_determinism.py failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_static_gate_fails_closed_on_an_empty_scope():
    """A gate that scans nothing must not report success."""
    proc = subprocess.run(
        [sys.executable, str(GATE), "--root", str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    assert proc.returncode != 0, "gate passed with an empty scope (vacuous)"
    assert "scope evaporated" in proc.stderr


def test_static_gate_is_wired_into_ci():
    """Removing the CI step must fail a test, and removing the test leaves the step.

    Neither half of the gate can be disabled by deleting the other: this test
    fails if the workflow step goes away, and the workflow step still runs if
    this file is deselected.
    """
    if not WORKFLOW.is_file():  # pragma: no cover - only when run outside the repo
        pytest.skip(f"{WORKFLOW} not present")
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/check_hash_order_determinism.py" in text, (
        "the salted-hash order gate is not invoked by .github/workflows/"
        "python-tests.yml. A gate that CI does not run is a gate that does not "
        "exist."
    )


def test_inventory_is_exact_and_has_no_wildcards():
    """The ledger must name sites, not patterns.

    A pattern entry would silence a whole file or package -- the denylist
    failure mode this gate is built to avoid.
    """
    inventory = REPO_ROOT / ".hash-order-inventory"
    assert inventory.is_file(), f"{inventory} is missing"
    entries = [
        line.split("#", 1)[0].strip() for line in inventory.read_text(encoding="utf-8").splitlines()
    ]
    entries = [e for e in entries if e]
    assert entries, "inventory is empty; the gate has nothing to ratchet against"
    for entry in entries:
        assert "*" not in entry and "?" not in entry, f"wildcard in inventory: {entry}"
        key, _, count = entry.rpartition(" ")
        assert key.count("::") == 2, f"malformed inventory entry: {entry}"
        assert count.isdigit(), f"malformed inventory count: {entry}"


def test_fixed_sites_are_absent_from_the_inventory():
    """Issue #752 defects 6 and 7 are fixed, so they must not be carried as debt."""
    inventory = (REPO_ROOT / ".hash-order-inventory").read_text(encoding="utf-8")
    for module in ("router_v6/channel_mapping.py", "router_v6/thermal_relief.py"):
        assert module not in inventory, (
            f"{module} is back in the inventory -- its fix regressed, or a new "
            "site was added and silenced instead of fixed."
        )


def test_gate_output_names_file_line_and_construct():
    """A finding must be actionable without opening the checker."""
    proc = subprocess.run(
        [sys.executable, str(GATE), "--no-inventory"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    assert proc.returncode == 1
    first = next(line for line in proc.stdout.splitlines() if line.startswith("packages/"))
    path, lineno, rest = first.split(":", 2)
    assert path.endswith(".py")
    assert lineno.isdigit()
    assert rest.strip().startswith("["), f"no construct name in {first!r}"


def test_gate_finding_count_is_reported():
    """Sanity: the audit mode reports a machine-readable total."""
    proc = subprocess.run(
        [sys.executable, str(GATE), "--no-inventory"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    tail = proc.stdout.strip().splitlines()[-1]
    assert "finding(s) in" in tail, tail
    assert int(tail.split()[0]) > 0
    json.dumps({"findings": int(tail.split()[0])})  # serialisable, for later reporting
