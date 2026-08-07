"""R1a differential: heuristics/style.py's two placement kernels
(``StarGroundTopologyHeuristic._place_radially``,
``SignalFlowPreservationHeuristic._place_by_flow``) vs their pinned oracle.

**THIS SUITE IS DELIBERATELY RED** until (a) the Rust extension exports
``radial_sector_positions_py``/``signal_chain_positions_py`` (already true --
see ``packages/temper-geometry/src/style_geometry.rs``) and (b) the SHIPPED
``heuristics/style.py`` module actually calls them. Every comparison below
resolves its Rust arm through ``tests.router_v6._pending_rust`` (pattern:
``test_organizational_rust_differential.py`` / ``test_structural_rust_differential.py``),
and the delegation tests at the bottom (pattern:
``tests/io/test_write_board_geometry_rust_differential.py``,
``tests/router_v6/test_occupancy_grid_rust_differential.py``) monkeypatch the
Rust symbols to raise and call the SHIPPED entry points directly -- this is
the part that is red right now: the numeric differential tests already pass
(the kernel is built and bit-exact against the oracle), but the delegation
tests fail because ``style.py`` has zero ``temper_geometry`` references, so
monkeypatching the Rust symbol has no effect and the shipped code returns
normally instead of propagating the raise.

Oracle/kernel correspondence
-----------------------------
Earlier triage of this migration (a coordinator checkpoint, not verified)
claimed the pinned oracle only covered ``identify_ground_domains``,
``extract_signal_chains``, and ``_trace_signal_path`` -- the three
classification helpers -- while the Rust kernel implements the placement
math in ``_place_radially``/``_place_by_flow``, which would make the two
not correspond.

Re-derived directly against this worktree's oracle file
(``_style_py_oracle.py``): that claim does not hold. The oracle pins the
**entire** ``style.py`` module verbatim (confirmed byte-for-byte against
``git show 550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5:.../style.py``, see
``test_oracle_is_verbatim_copy`` below), which includes both
``_place_radially`` and ``_place_by_flow`` in full, plus the three
classification helpers the module docstring calls out as "load-bearing for
``apply()`` to run standalone" -- exactly the same whole-module-pin
rationale already used for ``organizational.py``'s oracle (no single
standalone function to pin narrowly, unlike ``structural.py``'s
``create_keepout_mask``). The Rust kernel's own module doc
(``style_geometry.rs``) independently states the same split: classification
stays Python, ``_place_radially``/``_place_by_flow`` move to Rust. No
re-pinning or kernel-narrowing was needed -- oracle and kernel already
correspond. This file is the differential that proves it numerically.

Arms
----
* **oracle** -- ``tests/heuristics/_style_py_oracle.py``, verbatim ``git
  show`` copy of the whole ``style.py`` module at
  ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5``.
* **rust** -- ``temper_geometry``'s ``radial_sector_positions_py`` /
  ``signal_chain_positions_py``, reached through adapter functions below
  that reimplement each ``_place_*`` method's orchestration (grouping by
  domain/chain, ``context.is_position_valid``, ``ComponentPlacement``
  construction) exactly as the wired ``style.py`` does once Phase B lands --
  mirroring ``test_organizational_rust_differential.py``'s adapter block.

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``).
No tolerance anywhere.

Traps this file exercises
--------------------------
* ``_place_by_flow``'s ``max_pos`` must be computed from the chain's FULL
  node list, before the per-node ``current_placements``/``fixed``
  skip-checks run -- :func:`test_signal_flow_max_pos_uses_full_list_trap`
  pins a fixed component holding the chain's maximum position and asserts
  the surviving node's x-position reflects the *unfiltered* max, not the
  max of the subset that actually gets placed.
* ``_place_radially``'s single-item domain hits the ``t = ... else 0.5``
  branch, not a divide-by-zero -- :func:`test_star_ground_single_item_domain`.
* Domain/chain grouping in both methods is built from **list-order**
  iteration (``netlist.components``, ``domains.items()`` on a dict built
  from that list, ``chain_groups.items()`` on a dict built from
  position-sorted node lists) -- never a ``set`` -- so there is no
  PYTHONHASHSEED-dependent ordering to re-project through
  ``order_refs_by_netlist`` here, matching the oracle module's own docstring
  note. The adapters below preserve that iteration exactly (same dict
  literals, same insertion order) rather than introducing a new grouping
  structure that could reorder it.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

import tests.heuristics._style_py_oracle as ORACLE
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
from temper_placer.io.config_loader import PlacementConstraints
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm
# exists. Each function here is what the corresponding method in the wired
# `style.py` does: extract primitives, call the Rust kernel, rebuild the
# same orchestration (validity check, ComponentPlacement dict) the oracle's
# pinned method performs around its own inline math.
# ===========================================================================

_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "radial_sector_positions_py",
    "signal_chain_positions_py",
)


def _rust_place_radially(domains, star_point, board, context):
    """Mirrors ``StarGroundTopologyHeuristic._place_radially`` once wired."""
    radial_sector_positions = rust(_RUST_MODULE, "radial_sector_positions_py")
    placements: dict[str, ComponentPlacement] = {}
    sx, sy = star_point

    domain_angles = {
        "PGND": (3.14159 * 0.25, 3.14159 * 0.75),
        "DGND": (-3.14159 * 0.25, 3.14159 * 0.25),
        "AGND": (-3.14159 * 0.75, -3.14159 * 0.25),
    }

    domain_components: dict[str, list[str]] = {"PGND": [], "DGND": [], "AGND": []}
    for ref, domain in domains.items():
        if ref not in context.current_placements and not context.netlist.get_component(ref).fixed:
            domain_components[domain].append(ref)

    for domain, refs in domain_components.items():
        if not refs:
            continue

        angle_start, angle_end = domain_angles[domain]
        min_radius = 15.0
        max_radius = min(board.width, board.height) * 0.4

        positions = radial_sector_positions(len(refs), sx, sy, angle_start, angle_end, min_radius, max_radius)
        for ref, (pos_x, pos_y) in zip(refs, positions, strict=True):
            comp = context.netlist.get_component(ref)
            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[ref] = ComponentPlacement(
                    ref=ref, position=(pos_x, pos_y), rotation=0, confidence=0.5,
                    placed_by="star_ground_topology",
                )
    return placements


def _rust_place_by_flow(chains, board, context):
    """Mirrors ``SignalFlowPreservationHeuristic._place_by_flow`` once wired."""
    signal_chain_positions = rust(_RUST_MODULE, "signal_chain_positions_py")
    placements: dict[str, ComponentPlacement] = {}
    ox, oy = board.origin
    margin = context.constraints.board_margin_mm

    chain_groups: dict[str, list] = {}
    for node in chains:
        if node.chain_name not in chain_groups:
            chain_groups[node.chain_name] = []
        chain_groups[node.chain_name].append(node)

    for _chain_name, nodes in chain_groups.items():
        nodes.sort(key=lambda n: n.position)

    chain_names = list(chain_groups.keys())
    # Full, unfiltered per-node positions -- max_pos inside the kernel must
    # see every node in the chain, not just the ones that survive the
    # per-node skip-checks below (see module doc's trap note).
    chain_positions = [[n.position for n in chain_groups[name]] for name in chain_names]

    per_chain = signal_chain_positions(chain_positions, ox, oy, board.width, board.height, margin)

    for chain_idx, chain_name in enumerate(chain_names):
        nodes = chain_groups[chain_name]
        for node, (pos_x, pos_y) in zip(nodes, per_chain[chain_idx], strict=True):
            if node.ref in context.current_placements:
                continue
            if context.netlist.get_component(node.ref).fixed:
                continue
            comp = context.netlist.get_component(node.ref)
            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[node.ref] = ComponentPlacement(
                    ref=node.ref, position=(pos_x, pos_y), rotation=0, confidence=0.4,
                    placed_by="signal_flow_preservation",
                )
    return placements


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5"
_ORACLE_PATH = "packages/temper-placer/src/temper_placer/heuristics/style.py"


def _repo_root() -> Path:
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )


def _tail_after_module_docstring(src: str) -> str:
    """Everything in ``src`` after its own module docstring, unchanged.

    Uses the AST (not a text search for a marker) because
    ``from __future__ import annotations`` also appears in the oracle's own
    explanatory docstring text -- a naive ``str.index`` finds that mention
    first, not the real import line. (Same helper as
    ``test_organizational_rust_differential.py``.)
    """
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        start_line = tree.body[0].end_lineno  # 1-indexed, inclusive
        return "".join(lines[start_line:]).lstrip("\n")
    return src


def test_oracle_is_verbatim_copy():
    """Everything past the oracle's own docstring is byte-identical to the
    pin -- and, by construction, includes both ``_place_radially`` and
    ``_place_by_flow`` in full, not just the three classification helpers.
    """
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{_ORACLE_PIN_SHA}^{{commit}}"],
            capture_output=True, check=True, cwd=_repo_root(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")

    pinned_src = subprocess.run(
        ["git", "show", f"{_ORACLE_PIN_SHA}:{_ORACLE_PATH}"],
        capture_output=True, text=True, check=True, cwd=_repo_root(),
    ).stdout
    oracle_src = Path(ORACLE.__file__).read_text(encoding="utf-8")

    pinned_tail = _tail_after_module_docstring(pinned_src)
    oracle_tail = _tail_after_module_docstring(oracle_src)
    assert oracle_tail == pinned_tail


def test_oracle_covers_both_placement_methods():
    """Guards the correspondence claim directly: the oracle module object
    must expose both classes whose placement methods the kernel implements,
    not just the classification helpers a narrower pin would have kept.
    """
    assert hasattr(ORACLE, "StarGroundTopologyHeuristic")
    assert hasattr(ORACLE.StarGroundTopologyHeuristic, "_place_radially")
    assert hasattr(ORACLE, "SignalFlowPreservationHeuristic")
    assert hasattr(ORACLE.SignalFlowPreservationHeuristic, "_place_by_flow")


def test_rust_symbols_exist():
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert missing == [], f"still owed: {missing}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _board(width=100.0, height=80.0, origin=(0.0, 0.0)) -> Board:
    return Board(width=width, height=height, origin=origin)


def _constraints(board_margin_mm: float = 5.0) -> PlacementConstraints:
    return PlacementConstraints(board_margin_mm=board_margin_mm)


# ---------------------------------------------------------------------------
# Site 1: StarGroundTopologyHeuristic (radial sector placement)
# ---------------------------------------------------------------------------


def _star_ground_case():
    components = [
        Component(ref="Q1", footprint="SOT23", bounds=(1.2, 1.2)),
        Component(ref="L1", footprint="IND", bounds=(3.0, 3.0)),
        Component(ref="U1_MCU", footprint="QFN", bounds=(5.0, 5.0)),
        Component(ref="Y1", footprint="XTAL", bounds=(2.0, 1.2)),
        Component(ref="U1_OPAMP", footprint="SOIC", bounds=(3.0, 3.0)),
        Component(ref="R1_SENSE", footprint="R_0402", bounds=(1.0, 0.5)),
        Component(ref="R2_SENSE", footprint="R_0402", bounds=(1.0, 0.5)),
    ]
    netlist = Netlist(components=components, nets=[])
    board = _board(width=120.0, height=90.0)
    constraints = _constraints(board_margin_mm=4.0)
    return netlist, board, constraints


def test_star_ground_matches_oracle():
    netlist, board, constraints = _star_ground_case()
    domains = ORACLE.identify_ground_domains(netlist, constraints)

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_heuristic = ORACLE.StarGroundTopologyHeuristic()
    star_point = oracle_heuristic._get_star_point(board, constraints)
    oracle_placements = oracle_heuristic._place_radially(
        domains=domains, star_point=star_point, board=board, context=ctx_oracle
    )

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_radially(domains=domains, star_point=star_point, board=board, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)


def test_star_ground_nonvacuous():
    netlist, board, constraints = _star_ground_case()
    domains = ORACLE.identify_ground_domains(netlist, constraints)
    assert domains == {
        "Q1": "PGND", "L1": "PGND", "U1_MCU": "DGND", "Y1": "DGND",
        "U1_OPAMP": "AGND", "R1_SENSE": "AGND", "R2_SENSE": "AGND",
    }, "fixture should classify all three domains, with PGND at n=2"
    heuristic = ORACLE.StarGroundTopologyHeuristic()
    star_point = heuristic._get_star_point(board, constraints)
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    placements = heuristic._place_radially(domains=domains, star_point=star_point, board=board, context=ctx)
    # NOT all 7: L1 lands outside the valid region at its sector radius --
    # inherent to the oracle's algorithm on this fixture, not a porting
    # defect (mirrors organizational's power-flow "not all placed" note).
    assert len(placements) == 6
    assert "L1" not in placements


def _star_ground_single_item_case():
    components = [Component(ref="U1_MCU", footprint="QFN", bounds=(3.0, 3.0))]
    netlist = Netlist(components=components, nets=[])
    board = _board(width=80.0, height=60.0)
    constraints = _constraints(board_margin_mm=4.0)
    return netlist, board, constraints


def test_star_ground_single_item_domain():
    """n=1 in a domain hits ``t = i/(n-1) if n > 1 else 0.5``, not a
    divide-by-zero -- exercised through the real oracle/kernel pair, not
    just the Rust unit tests in ``style_geometry.rs``."""
    netlist, board, constraints = _star_ground_single_item_case()
    domains = ORACLE.identify_ground_domains(netlist, constraints)
    assert domains == {"U1_MCU": "DGND"}

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_heuristic = ORACLE.StarGroundTopologyHeuristic()
    star_point = oracle_heuristic._get_star_point(board, constraints)
    oracle_placements = oracle_heuristic._place_radially(
        domains=domains, star_point=star_point, board=board, context=ctx_oracle
    )

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_radially(domains=domains, star_point=star_point, board=board, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)
    assert len(oracle_placements) == 1


# ---------------------------------------------------------------------------
# Site 2: SignalFlowPreservationHeuristic (chain-position placement)
# ---------------------------------------------------------------------------


def _signal_flow_case():
    components = [
        Component(ref="J1_IN", footprint="CONN", bounds=(3.0, 3.0)),
        Component(ref="J2_SENS", footprint="CONN", bounds=(2.0, 2.0)),
        Component(ref="R1", footprint="R_0402", bounds=(1.0, 1.0)),
        Component(ref="U1_MCU", footprint="QFN", bounds=(5.0, 5.0)),
    ]
    nets = [
        Net(name="SIG1", pins=[("J1_IN", "1"), ("R1", "1")], net_class="Signal"),
        Net(name="SIG2", pins=[("R1", "2"), ("U1_MCU", "1")], net_class="Signal"),
    ]
    netlist = Netlist(components=components, nets=nets)
    board = _board(width=100.0, height=60.0)
    constraints = _constraints(board_margin_mm=5.0)
    return netlist, board, constraints


def test_signal_flow_matches_oracle():
    netlist, board, constraints = _signal_flow_case()
    chains = ORACLE.extract_signal_chains(netlist, constraints)

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_placements = ORACLE.SignalFlowPreservationHeuristic()._place_by_flow(
        chains=chains, board=board, context=ctx_oracle
    )

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_by_flow(chains=chains, board=board, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)


def test_signal_flow_nonvacuous():
    netlist, board, constraints = _signal_flow_case()
    chains = ORACLE.extract_signal_chains(netlist, constraints)
    assert [(n.ref, n.chain_name, n.position) for n in chains] == [
        ("J1_IN", "chain_0", 0), ("R1", "chain_0", 1), ("U1_MCU", "chain_0", 2),
        ("J2_SENS", "chain_1", 0),
    ], "fixture should trace a 3-node chain from J1_IN and a 1-node chain from J2_SENS"
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    placements = ORACLE.SignalFlowPreservationHeuristic()._place_by_flow(chains=chains, board=board, context=ctx)
    # J1_IN (t=0) and U1_MCU (t=1) both land exactly on a margin boundary
    # and get rejected by is_position_valid; only R1 (t=0.5, chain_0) and
    # J2_SENS (t=0.5, single-node chain_1) survive.
    assert set(placements) == {"R1", "J2_SENS"}


def _signal_flow_max_pos_trap_case():
    """A chain where the node holding the maximum ``position`` is ``fixed``
    (dropped by the per-node skip-check) -- see module doc's trap note."""
    components = [
        Component(ref="J3_IN", footprint="CONN", bounds=(2.0, 2.0)),
        Component(ref="R2", footprint="R_0402", bounds=(1.0, 1.0)),
        Component(ref="R3", footprint="R_0402", bounds=(1.0, 1.0), fixed=True),
    ]
    nets = [
        Net(name="SIG1", pins=[("J3_IN", "1"), ("R2", "1")], net_class="Signal"),
        Net(name="SIG2", pins=[("R2", "2"), ("R3", "1")], net_class="Signal"),
    ]
    netlist = Netlist(components=components, nets=nets)
    board = _board(width=100.0, height=60.0)
    constraints = _constraints(board_margin_mm=5.0)
    return netlist, board, constraints


def test_signal_flow_max_pos_uses_full_list_trap():
    netlist, board, constraints = _signal_flow_max_pos_trap_case()
    chains = ORACLE.extract_signal_chains(netlist, constraints)
    assert [(n.ref, n.position) for n in chains] == [("J3_IN", 0), ("R2", 1), ("R3", 2)]

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_placements = ORACLE.SignalFlowPreservationHeuristic()._place_by_flow(
        chains=chains, board=board, context=ctx_oracle
    )
    # R3 is fixed=True and never appears in the output, but it must still
    # set max_pos=2 for R2's t -- a naive port that filters fixed/placed
    # nodes BEFORE computing max_pos would compute max_pos=1 from R2 alone
    # and place R2 at t=1.0 (x=95.0) instead of t=0.5 (x=50.0).
    assert set(oracle_placements) == {"R2"}
    assert oracle_placements["R2"].position == pytest.approx((50.0, 30.0))

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_by_flow(chains=chains, board=board, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)


# ---------------------------------------------------------------------------
# Shipped-module delegation proof -- NOT a bit-exactness check.
#
# A green differential above compares the oracle against the Rust kernel
# directly and passes whether or not the SHIPPED style.py module actually
# calls it. Monkeypatching the Rust symbol to raise and calling the shipped
# entry point is the only thing that proves the production code path was
# rewired, not left as a second, unreachable implementation next to the
# first. THIS IS THE PART THAT IS CURRENTLY RED: style.py has zero
# `temper_geometry` references, so these two tests fail with "DID NOT RAISE"
# until Phase B wires the call site.
# ---------------------------------------------------------------------------

import temper_geometry as _GEOM  # noqa: E402
import temper_placer.heuristics.style as shipped  # noqa: E402


def test_place_radially_delegates_to_rust():
    netlist, board, constraints = _star_ground_case()
    domains = shipped.identify_ground_domains(netlist, constraints)
    heuristic = shipped.StarGroundTopologyHeuristic()
    star_point = heuristic._get_star_point(board, constraints)
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)

    sentinel = RuntimeError("REACHED_RUST_RADIAL_SECTOR")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.radial_sector_positions_py
    _GEOM.radial_sector_positions_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_RADIAL_SECTOR"):
            heuristic._place_radially(domains=domains, star_point=star_point, board=board, context=ctx)
    finally:
        _GEOM.radial_sector_positions_py = original


def test_place_by_flow_delegates_to_rust():
    netlist, board, constraints = _signal_flow_case()
    chains = shipped.extract_signal_chains(netlist, constraints)
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)

    sentinel = RuntimeError("REACHED_RUST_SIGNAL_CHAIN")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.signal_chain_positions_py
    _GEOM.signal_chain_positions_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_SIGNAL_CHAIN"):
            shipped.SignalFlowPreservationHeuristic()._place_by_flow(chains=chains, board=board, context=ctx)
    finally:
        _GEOM.signal_chain_positions_py = original
