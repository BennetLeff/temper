"""R1a differential: heuristics/style.py's two ``_place_*`` placement
kernels vs their pinned oracle, plus a wiring proof that the shipped module
actually delegates to ``temper_geometry``.

**THIS SUITE IS DELIBERATELY RED** until the Rust extension is built with
the new symbols and the shipped module is wired. See ``REQUIRED_RUST_SYMBOLS``
and the adapter block below for the mechanism (pattern:
``tests/heuristics/test_structural_rust_differential.py`` /
``tests/heuristics/test_organizational_rust_differential.py`` /
``tests/router_v6/_pending_rust.py``).

Arms
----
* **oracle** -- ``tests/heuristics/_style_py_oracle.py``, a verbatim
  ``git show`` copy of the whole ``style.py`` module at
  ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5``.
* **rust** -- ``temper_geometry``'s two new pyfunctions
  (``radial_sector_positions_py``, ``signal_chain_positions_py``), reached
  through adapter functions in this file that reimplement each ``_place_*``
  method's orchestration (grouping, ``context.is_position_valid``,
  ``ComponentPlacement`` construction) exactly as the wired ``style.py``
  does -- mirroring the organizational differential's ``_rust_place_modules``
  et al., which do the same for ``organizational.py``.

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``).
No tolerance anywhere.

Wiring proof
------------
``style.py`` follows ``structural.py``/``organizational.py``'s established
pattern of a **function-local** ``from temper_geometry import ...`` at each
``_place_*`` call site (not a module-scope ``import temper_geometry as _tg``),
so the wiring tests below monkeypatch the attribute on the ``temper_geometry``
module object itself -- the function-local import resolves that same
attribute fresh on every call, so the patch is visible without needing a
module-scope alias to intercept (pattern:
``tests/router_v6/test_occupancy_grid_rust_differential.py``'s
``_WiringMarker``/``_raise_marker``, adapted for a function-local rather than
module-scope import).
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

# Mirrors StarGroundTopologyHeuristic._place_radially's domain_angles dict --
# this stays Python on both arms (board-fraction-style constant table, not
# per-item compute), matching organizational.py's region-box precedent.
_DOMAIN_ANGLES = {
    "PGND": (3.14159 * 0.25, 3.14159 * 0.75),
    "DGND": (-3.14159 * 0.25, 3.14159 * 0.25),
    "AGND": (-3.14159 * 0.75, -3.14159 * 0.25),
}


def _rust_place_radially(domains, star_point, board, context):
    """Mirrors ``StarGroundTopologyHeuristic._place_radially`` once wired."""
    radial_sector_positions = rust(_RUST_MODULE, "radial_sector_positions_py")
    placements: dict[str, ComponentPlacement] = {}
    sx, sy = star_point

    domain_components: dict[str, list[str]] = {"PGND": [], "DGND": [], "AGND": []}
    for ref, domain in domains.items():
        if ref not in context.current_placements and not context.netlist.get_component(ref).fixed:
            domain_components[domain].append(ref)

    for domain, refs in domain_components.items():
        if not refs:
            continue
        angle_start, angle_end = _DOMAIN_ANGLES[domain]
        min_radius = 15.0
        max_radius = min(board.width, board.height) * 0.4
        positions = radial_sector_positions(
            len(refs), sx, sy, angle_start, angle_end, min_radius, max_radius
        )
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
        chain_groups.setdefault(node.chain_name, []).append(node)
    for nodes in chain_groups.values():
        nodes.sort(key=lambda n: n.position)

    chain_names = list(chain_groups.keys())
    chain_positions = [[n.position for n in chain_groups[name]] for name in chain_names]
    per_chain = signal_chain_positions(chain_positions, ox, oy, board.width, board.height, margin)

    for name, per_node in zip(chain_names, per_chain, strict=True):
        nodes = chain_groups[name]
        for node, (pos_x, pos_y) in zip(nodes, per_node, strict=True):
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

    Uses the AST (not a text search for a marker) because the oracle's own
    explanatory docstring text also mentions ``from __future__ import
    annotations`` -- a naive ``str.index`` finds that mention first, not the
    real import line.
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
    """Everything past the oracle's own docstring is byte-identical to the pin."""
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


def test_rust_symbols_exist():
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert missing == [], f"still owed: {missing}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _board(width=120.0, height=90.0, origin=(0.0, 0.0)) -> Board:
    return Board(width=width, height=height, origin=origin)


def _constraints(board_margin_mm: float = 4.0) -> PlacementConstraints:
    return PlacementConstraints(board_margin_mm=board_margin_mm)


# ---------------------------------------------------------------------------
# Site 1: StarGroundTopologyHeuristic (radial sector placement, 3 domains)
# ---------------------------------------------------------------------------


def _star_ground_case():
    # PGND: 1 component (n==1 -> t=0.5 midpoint branch).
    # AGND: 2 components (odd/non-axis-aligned angle interpolation).
    # DGND: 3 components (default domain -- generic refs matching no pattern).
    components = [
        Component(ref="Q1", footprint="SOT23", bounds=(1.5, 1.0)),  # PGND (power pattern)
        Component(ref="U1_OPAMP", footprint="SOIC8", bounds=(3.0, 3.0)),  # AGND
        Component(ref="U2_ADC", footprint="SOIC8", bounds=(3.0, 3.0)),  # AGND
        Component(ref="R1", footprint="R_0402", bounds=(1.0, 0.5)),  # DGND (default)
        Component(ref="R2", footprint="R_0402", bounds=(1.0, 0.5)),  # DGND
        Component(ref="R3", footprint="R_0402", bounds=(1.0, 0.5)),  # DGND
    ]
    netlist = Netlist(components=components, nets=[])
    board = _board()
    constraints = _constraints()
    return netlist, board, constraints


def test_star_ground_topology_matches_oracle():
    netlist, board, constraints = _star_ground_case()
    domains = ORACLE.identify_ground_domains(netlist, constraints)

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_heuristic = ORACLE.StarGroundTopologyHeuristic()
    star_point = oracle_heuristic._get_star_point(board, constraints)
    oracle_placements = oracle_heuristic._place_radially(
        domains=domains, star_point=star_point, board=board, context=ctx_oracle
    )

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_radially(
        domains=domains, star_point=star_point, board=board, context=ctx_rust
    )

    assert sig(oracle_placements) == sig(rust_placements)


def test_star_ground_topology_nonvacuous():
    netlist, board, constraints = _star_ground_case()
    domains = ORACLE.identify_ground_domains(netlist, constraints)
    assert set(domains.values()) == {"PGND", "AGND", "DGND"}, "fixture must exercise all 3 domains"
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    heuristic = ORACLE.StarGroundTopologyHeuristic()
    star_point = heuristic._get_star_point(board, constraints)
    placements = heuristic._place_radially(domains=domains, star_point=star_point, board=board, context=ctx)
    assert len(placements) == 6, "fixture should place all 6 components"


def test_star_ground_topology_explicit_star_point_matches_oracle():
    # Exercise a non-default star point (skips _get_star_point's board-center
    # fallback branch, still identical math downstream).
    netlist, board, constraints = _star_ground_case()
    domains = ORACLE.identify_ground_domains(netlist, constraints)
    star_point = (40.0, 20.0)

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_placements = ORACLE.StarGroundTopologyHeuristic(star_point=star_point)._place_radially(
        domains=domains, star_point=star_point, board=board, context=ctx_oracle
    )

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_radially(
        domains=domains, star_point=star_point, board=board, context=ctx_rust
    )

    assert sig(oracle_placements) == sig(rust_placements)


# ---------------------------------------------------------------------------
# Site 2: SignalFlowPreservationHeuristic (per-chain linear placement)
# ---------------------------------------------------------------------------


def _signal_flow_case():
    # Chain 0: J1_IN -> U1_MCU -> U2_DRV (position 0, 1, 2 -- exercises the
    # "max_pos from the FULL unfiltered node list" trap when U1_MCU is
    # pre-placed below).
    # Chain 1: J2_SENS alone (no outgoing signal net -- position 0 only,
    # max_pos == 0 -> the `else 0.5` branch).
    components = [
        Component(ref="J1_IN", footprint="CONN", bounds=(5.0, 3.0)),
        Component(ref="U1_MCU", footprint="QFN", bounds=(7.0, 7.0)),
        Component(ref="U2_DRV", footprint="SOIC8", bounds=(4.0, 4.0)),
        Component(ref="J2_SENS", footprint="CONN", bounds=(5.0, 3.0)),
    ]
    nets = [
        Net(name="SIG_A", pins=[("J1_IN", "1"), ("U1_MCU", "1")], net_class="Signal"),
        Net(name="SIG_B", pins=[("U1_MCU", "2"), ("U2_DRV", "1")], net_class="Signal"),
    ]
    netlist = Netlist(components=components, nets=nets)
    board = _board(width=100.0, height=60.0)
    constraints = _constraints(board_margin_mm=5.0)
    return netlist, board, constraints


def test_signal_flow_preservation_matches_oracle():
    netlist, board, constraints = _signal_flow_case()
    chains = ORACLE.extract_signal_chains(netlist, constraints)

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_placements = ORACLE.SignalFlowPreservationHeuristic()._place_by_flow(
        chains=chains, board=board, context=ctx_oracle
    )

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_by_flow(chains=chains, board=board, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)


def test_signal_flow_preservation_nonvacuous():
    netlist, board, constraints = _signal_flow_case()
    chains = ORACLE.extract_signal_chains(netlist, constraints)
    assert {c.ref for c in chains} == {"J1_IN", "U1_MCU", "U2_DRV", "J2_SENS"}
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    placements = ORACLE.SignalFlowPreservationHeuristic()._place_by_flow(
        chains=chains, board=board, context=ctx
    )
    assert "J2_SENS" in placements, "the single-node chain (t=0.5) always survives"


def _signal_flow_max_pos_case():
    # A single 4-node chain, positions 0..3, where the node holding the
    # MAXIMUM position (U1_MCU, position=3) is the one that gets pre-placed
    # and therefore skipped. Built directly as SignalChainNode objects
    # (bypassing extract_signal_chains's graph walk entirely) so the trap is
    # isolated from netlist-connectivity concerns: this test is about
    # `_place_by_flow`'s own `max_pos` computation, not chain extraction.
    #
    # J1_IN (t=0) and U2_DRV -- omitted here -- would sit exactly on a board
    # margin boundary and always be rejected by `is_position_valid`
    # regardless of `max_pos` correctness (same shape as
    # `organizational.py`'s `test_power_flow_topology_nonvacuous` endpoint
    # note), so this fixture checks the two INTERIOR nodes (A1, A2) instead,
    # which is where a wrong `max_pos` is actually observable in the output
    # position, not just in whether placement succeeds at all.
    components = [
        Component(ref="J1_IN", footprint="CONN", bounds=(3.0, 3.0)),
        Component(ref="A1", footprint="R_0603", bounds=(2.0, 1.0)),
        Component(ref="A2", footprint="R_0603", bounds=(2.0, 1.0)),
        Component(ref="U1_MCU", footprint="QFN", bounds=(3.0, 3.0)),
    ]
    netlist = Netlist(components=components, nets=[])
    board = _board(width=100.0, height=60.0)
    constraints = _constraints(board_margin_mm=5.0)
    chains = [
        ORACLE.SignalChainNode(ref="J1_IN", chain_name="chain_0", position=0),
        ORACLE.SignalChainNode(ref="A1", chain_name="chain_0", position=1),
        ORACLE.SignalChainNode(ref="A2", chain_name="chain_0", position=2),
        ORACLE.SignalChainNode(ref="U1_MCU", chain_name="chain_0", position=3),
    ]
    return netlist, board, constraints, chains


def test_signal_flow_preservation_max_pos_uses_full_chain_matches_oracle():
    """The trap this exists to catch: max_pos for chain_0 must be derived
    from ALL 4 nodes (positions 0,1,2,3), even though U1_MCU (position 3,
    the chain's maximum) is pre-placed and therefore skipped by the
    per-node filter. A Rust port that filtered before computing max_pos
    would divide by 2 (the max of the surviving [0,1,2]), not 3, and
    silently move A1/A2 to the wrong x position -- still "matching" a
    naive same-bug reimplementation but not the real oracle.
    """
    netlist, board, constraints, chains = _signal_flow_max_pos_case()

    seeded = {
        "U1_MCU": ComponentPlacement(ref="U1_MCU", position=(50.0, 30.0), rotation=0, confidence=1.0)
    }

    ctx_oracle = PlacementContext(
        board=board, netlist=netlist, constraints=constraints, current_placements=dict(seeded)
    )
    oracle_placements = ORACLE.SignalFlowPreservationHeuristic()._place_by_flow(
        chains=chains, board=board, context=ctx_oracle
    )

    ctx_rust = PlacementContext(
        board=board, netlist=netlist, constraints=constraints, current_placements=dict(seeded)
    )
    rust_placements = _rust_place_by_flow(chains=chains, board=board, context=ctx_rust)

    assert "U1_MCU" not in oracle_placements, "pre-placed node must be skipped by both arms"
    assert sig(oracle_placements) == sig(rust_placements)

    # A1 (position=1) and A2 (position=2) must reflect max_pos=3 (the full
    # chain's maximum, including the skipped U1_MCU), not max_pos=2 (the
    # maximum of the filtered survivors [0,1,2]) that a filter-then-compute
    # bug would produce.
    assert "A1" in oracle_placements, "A1 (interior, t=1/3) must clear is_position_valid"
    assert "A2" in oracle_placements, "A2 (interior, t=2/3) must clear is_position_valid"
    ox, _oy = board.origin
    margin = constraints.board_margin_mm
    x_range = board.width - 2 * margin
    expected_a1_x = ox + margin + (1.0 / 3.0) * x_range  # t = 1/3, NOT 1/2
    expected_a2_x = ox + margin + (2.0 / 3.0) * x_range  # t = 2/3, NOT 1
    assert oracle_placements["A1"].position[0] == expected_a1_x
    assert oracle_placements["A2"].position[0] == expected_a2_x


# ---------------------------------------------------------------------------
# Wiring proof: the SHIPPED style.py module must actually delegate.
# Monkeypatch each Rust entry point on the temper_geometry module object to
# raise a distinctive marker exception, call the shipped Heuristic's public
# apply()/_place_* method, and require the marker to propagate. `style.py`
# uses a function-local `from temper_geometry import ...` at each call site
# (matching structural.py/organizational.py's precedent) -- that import
# resolves the attribute on the already-imported `temper_geometry` module
# fresh on every call, so patching the attribute directly (no module-scope
# alias needed) is sufficient to intercept it.
# ---------------------------------------------------------------------------


class _WiringMarker(RuntimeError):
    """Distinctive exception raised by a monkeypatched Rust entry point."""


def _raise_marker(*_args, **_kwargs):
    raise _WiringMarker("kernel called")


def test_star_ground_topology_shipped_module_delegates_to_rust(monkeypatch):
    import temper_geometry

    import temper_placer.heuristics.style as SHIPPED

    monkeypatch.setattr(temper_geometry, "radial_sector_positions_py", _raise_marker)

    netlist, board, constraints = _star_ground_case()
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    with pytest.raises(_WiringMarker):
        SHIPPED.StarGroundTopologyHeuristic().apply(ctx)


def test_signal_flow_preservation_shipped_module_delegates_to_rust(monkeypatch):
    import temper_geometry

    import temper_placer.heuristics.style as SHIPPED

    monkeypatch.setattr(temper_geometry, "signal_chain_positions_py", _raise_marker)

    netlist, board, constraints = _signal_flow_case()
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    with pytest.raises(_WiringMarker):
        SHIPPED.SignalFlowPreservationHeuristic().apply(ctx)
