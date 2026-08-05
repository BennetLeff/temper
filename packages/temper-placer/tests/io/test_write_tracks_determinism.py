"""The written .kicad_pcb must not depend on CPython's per-process hash salt.

``write_routes_to_pcb`` receives ``routes``/``vias`` as **sets**. Before the
canonical emission order landed, it iterated them directly, so the byte order
of ``(segment ...)`` and ``(via ...)`` lines in the shipped board followed
``PYTHONHASHSEED`` (PEP 456). Measured on the production board
(``pcb/temper.kicad_pcb``, 2338 traces + 48 vias): **32 distinct orders over 32
fresh interpreters**.

Why fresh interpreters: the salt is fixed for a process's lifetime, so
in-process repetition can never observe this. Every cell below re-executes the
writer in a subprocess with an explicit ``PYTHONHASHSEED``.

Comparison is exact (full digest of the emitted sequence), never tolerance
based -- PR #730 found this same defect class as a 1-ULP coordinate move that
any approximate comparison would have called equal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SEEDS = tuple(range(32))

# The fixture is built so the three candidate orders all disagree. A future
# "fix" that sorts by net *name*, or that trusts insertion order, fails the
# pinning tests below rather than silently replacing the chosen order.
#
#   net index (chosen) : GND(1) < VBUS(2) < AVDD(3)
#   net name (lexical) : AVDD   < GND     < VBUS
NETS = (("GND", 1), ("VBUS", 2), ("AVDD", 3))

# Layers likewise: stackup order is F.Cu < In1.Cu < In2.Cu < B.Cu, which is not
# the lexicographic order B.Cu < F.Cu < In1.Cu < In2.Cu.
LAYERS = ("B.Cu", "In2.Cu", "F.Cu", "In1.Cu")


def _emitted_items(pcb_text: str) -> list[str]:
    """The board's ``segment``/``via`` lines, in file order, tstamps removed.

    The tstamp is stripped so this measures *order* alone and cannot be
    confounded by per-object identity tokens.
    """
    lines = [
        ln.strip()
        for ln in pcb_text.splitlines()
        if ln.lstrip().startswith("(segment ") or ln.lstrip().startswith("(via ")
    ]
    return [re.sub(r"\((?:tstamp|uuid) [^)]*\)", "", ln) for ln in lines]


_CHILD = textwrap.dedent(
    """
    import hashlib, json, re, sys
    from pathlib import Path
    from kiutils.board import Board as KiBoard
    from kiutils.items.common import Net
    from temper_placer.core.board import Trace, Via
    from temper_placer.io._write_tracks import write_routes_to_pcb

    spec = json.loads(Path(sys.argv[1]).read_text())
    tmp = Path(sys.argv[2])

    template = tmp / "template.kicad_pcb"
    board = KiBoard.create_new()
    board.nets = [Net(number=0, name="")] + [
        Net(number=n, name=name) for name, n in spec["nets"]
    ]
    board.to_file(str(template))

    routes = frozenset(
        Trace(start=tuple(r[0]), end=tuple(r[1]), width=r[2], layer=r[3], net=r[4])
        for r in spec["routes"]
    )
    vias = frozenset(
        Via(position=tuple(v[0]), drill=v[1], width=v[2], layers=tuple(v[3]), net=v[4])
        for v in spec["vias"]
    )

    out = tmp / "out.kicad_pcb"
    write_routes_to_pcb(template, out, routes, vias, clear_existing=True)

    lines = [
        ln.strip()
        for ln in out.read_text().splitlines()
        if ln.lstrip().startswith("(segment ") or ln.lstrip().startswith("(via ")
    ]
    stripped = [re.sub(r"\\((?:tstamp|uuid) [^)]*\\)", "", ln) for ln in lines]
    print(json.dumps({"n": len(stripped), "items": stripped}))
    """
)


@pytest.fixture(scope="module")
def spec() -> dict:
    """Routes and vias spanning several nets and layers, in a scrambled order."""
    routes = []
    for i, (net, _) in enumerate(NETS):
        for j, layer in enumerate(LAYERS):
            x = float(10 + 3 * i + j)
            routes.append([[x, 20.0], [x, 25.0], 0.25, layer, net])
            routes.append([[x, 25.0], [x + 1.0, 25.0], 0.25, layer, net])
    vias = [
        [[float(40 + 2 * i), 30.0], 0.3, 0.6, ["F.Cu", "B.Cu"], net]
        for i, (net, _) in enumerate(NETS)
    ]
    return {"nets": [list(n) for n in NETS], "routes": routes, "vias": vias}


def _run_under_seed(spec: dict, seed: int, tmp_path: Path) -> dict:
    work = tmp_path / f"seed_{seed}"
    work.mkdir(parents=True, exist_ok=True)
    spec_file = work / "spec.json"
    spec_file.write_text(json.dumps(spec))

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, str(spec_file), str(work)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"seed={seed} child failed:\n{proc.stderr[-3000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def per_seed(spec, tmp_path_factory) -> list[dict]:
    tmp = tmp_path_factory.mktemp("write_tracks_determinism")
    return [_run_under_seed(spec, s, tmp) for s in SEEDS]


def test_emission_order_is_not_vacuous(per_seed):
    """Guard: the determinism cells must not pass by comparing empty output."""
    expected = 2 * len(NETS) * len(LAYERS) + len(NETS)
    for seed, result in zip(SEEDS, per_seed, strict=True):
        assert result["n"] == expected, (
            f"seed={seed} emitted {result['n']} items, expected {expected}; "
            "a determinism test over an empty board proves nothing"
        )


def test_emission_order_is_independent_of_pythonhashseed(per_seed):
    """The whole point: identical route set -> identical file order, every process."""
    digests = [
        hashlib.sha256("\n".join(r["items"]).encode()).hexdigest() for r in per_seed
    ]
    distinct = set(digests)
    if len(distinct) != 1:
        disagree = sum(1 for d in digests[1:] if d != digests[0])
        pytest.fail(
            "write_routes_to_pcb emission order depends on PYTHONHASHSEED: "
            f"{len(distinct)} distinct orders over {len(SEEDS)} fresh interpreters "
            f"({disagree} of {len(SEEDS) - 1} other seeds disagree with seed=0). "
            "Site: packages/temper-placer/src/temper_placer/io/_write_tracks.py, "
            "write_routes_to_pcb -- the `routes` and `vias` sets are being "
            "iterated directly instead of sorted by _trace_emission_key / "
            "_via_emission_key."
        )


def test_segments_are_grouped_by_board_net_index_not_net_name(per_seed):
    """Pins *which* order won: board net index, not lexicographic net name.

    Net names are chosen so the two disagree (index GND<VBUS<AVDD, lexical
    AVDD<GND<VBUS). A later `sorted()` by name fails here.
    """
    items = per_seed[0]["items"]
    segments = [ln for ln in items if ln.startswith("(segment ")]
    seen: list[int] = []
    for line in segments:
        match = re.search(r"\(net (\d+)\)", line)
        assert match is not None, f"segment carries no net field: {line}"
        net = int(match.group(1))
        if not seen or seen[-1] != net:
            seen.append(net)

    assert seen == sorted(seen), (
        f"segments are not grouped by ascending board net index: {seen}"
    )
    assert len(seen) == len(set(seen)), (
        f"a net's copper is split into non-contiguous runs: {seen}"
    )
    assert seen == [n for _, n in NETS], (
        f"expected net-index order {[n for _, n in NETS]}, got {seen}; "
        "if this is lexicographic net-name order the writer sorted by the "
        "wrong key"
    )


def test_layers_within_a_net_follow_stackup_not_alphabetical_order(per_seed):
    """Pins the layer key: physical stackup position, not layer-name spelling."""
    items = per_seed[0]["items"]
    first_net = NETS[0][1]
    layers: list[str] = []
    for line in items:
        if not line.startswith("(segment "):
            continue
        if int(re.search(r"\(net (\d+)\)", line).group(1)) != first_net:
            continue
        layer = re.search(r"\(layer \"([^\"]+)\"\)", line).group(1)
        if not layers or layers[-1] != layer:
            layers.append(layer)

    assert layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], (
        f"layers within a net are not in stackup order: {layers}; "
        "alphabetical order would be ['B.Cu', 'F.Cu', 'In1.Cu', 'In2.Cu']"
    )


def test_emission_order_is_total_over_the_route_set(spec):
    """No two distinct elements may share a sort key, or a tie is left to chance."""
    from temper_placer.core.board import Trace, Via
    from temper_placer.io._write_tracks import _trace_emission_key, _via_emission_key

    index = {name: number for name, number in NETS}

    routes = [
        Trace(start=tuple(r[0]), end=tuple(r[1]), width=r[2], layer=r[3], net=r[4])
        for r in spec["routes"]
    ]
    keys = [_trace_emission_key(r, index) for r in routes]
    assert len(set(keys)) == len(routes), "trace emission key is not total"

    vias = [
        Via(position=tuple(v[0]), drill=v[1], width=v[2], layers=tuple(v[3]), net=v[4])
        for v in spec["vias"]
    ]
    via_keys = [_via_emission_key(v, index) for v in vias]
    assert len(set(via_keys)) == len(vias), "via emission key is not total"
