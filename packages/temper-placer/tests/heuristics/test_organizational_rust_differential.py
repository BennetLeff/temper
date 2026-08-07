"""R1a differential: heuristics/organizational.py's five ``_place_*``
placement kernels vs their pinned oracle.

**THIS SUITE IS DELIBERATELY RED** until the Rust extension is built with
the new symbols and the shipped module is wired. See ``REQUIRED_RUST_SYMBOLS``
and the adapter block below for the mechanism (pattern:
``tests/heuristics/test_structural_rust_differential.py`` /
``tests/router_v6/_pending_rust.py``).

**Honesty note on ordering.** The intended process for this migration was
oracle-and-differential-committed-red, *then* the Rust kernel. That did not
happen cleanly here: the Rust source
(``packages/temper-geometry/src/organizational_geometry.rs`` plus its
``lib.rs``/``bridge.rs`` registration) was committed by a checkpoint
(``wip(mig-orgheur): checkpoint agent work in progress``) before this
oracle/differential file existed in git history, because the agent authoring
both was idle long enough to trigger an automatic safety-checkpoint commit.
The Rust *source* therefore predates this file in commit history. What this
suite still proves independently: at the time this file was authored, the
worktree's Python environment had no ``temper_geometry`` extension installed
at all (``ModuleNotFoundError: No module named 'temper_geometry'``, checked
directly), so every comparison below genuinely failed with
``PendingRustError`` before ``maturin develop`` was ever run in this
worktree -- the RED state was real, just not gated on the Rust source
literally not existing in the repository yet.

Arms
----
* **oracle** -- ``tests/heuristics/_organizational_py_oracle.py``, a
  verbatim ``git show`` copy of the whole ``organizational.py`` module at
  ``b9c766059c34649c2947f04f89a578fdb48a2756``.
* **rust** -- ``temper_geometry``'s five new pyfunctions
  (``module_grid_positions_py``, ``circle_offsets_py``,
  ``power_flow_positions_py``, ``decoupling_candidate_positions_py``,
  ``domain_grid_positions_py``), reached through adapter functions in this
  file that reimplement each ``_place_*`` method's orchestration (loop,
  ``context.is_position_valid``/``check_overlap``, ``ComponentPlacement``
  construction) exactly as the wired ``organizational.py`` does -- mirroring
  the structural differential's
  ``_rust_create_keepout_mask``, which does the same for
  ``create_keepout_mask``.

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``).
No tolerance anywhere.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

import tests.heuristics._organizational_py_oracle as ORACLE
from temper_placer._constraint_types import ComponentGroup
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
from temper_placer.io.config_loader import PlacementConstraints
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm
# exists. Each function here is what the corresponding method in the wired
# `organizational.py` does: extract primitives, call the Rust kernel,
# rebuild the same orchestration (validity check, ComponentPlacement dict)
# the oracle's pinned method performs around its own inline math.
# ===========================================================================

_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "module_grid_positions_py",
    "circle_offsets_py",
    "power_flow_positions_py",
    "decoupling_candidate_positions_py",
    "domain_grid_positions_py",
)


def _rust_place_modules(modules, board, context):
    """Mirrors ``FunctionalModuleClusteringHeuristic._place_modules`` once wired."""
    module_grid_positions = rust(_RUST_MODULE, "module_grid_positions_py")
    placements: dict[str, ComponentPlacement] = {}
    ox, oy = board.origin
    centroids = module_grid_positions(
        len(modules), ox, oy, board.width, board.height, context.constraints.board_margin_mm
    )
    for module, (cx, cy) in zip(modules, centroids, strict=True):
        module_placements = _rust_place_module_components(module, (cx, cy), context)
        placements.update(module_placements)
    return placements


def _rust_place_module_components(module, centroid, context):
    """Mirrors ``_place_module_components`` once wired."""
    circle_offsets = rust(_RUST_MODULE, "circle_offsets_py")
    placements: dict[str, ComponentPlacement] = {}
    cx, cy = centroid
    to_place = [
        ref
        for ref in module.components
        if ref not in context.current_placements and not context.netlist.get_component(ref).fixed
    ]
    if not to_place:
        return {}
    radius = min(20.0 / 2, 8.0)  # matches FunctionalModuleClusteringHeuristic default max_spread_mm=20.0
    offsets = circle_offsets(len(to_place), radius)
    for ref, (offset_x, offset_y) in zip(to_place, offsets, strict=True):
        pos_x = cx + float(offset_x)
        pos_y = cy + float(offset_y)
        comp = context.netlist.get_component(ref)
        if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
            placements[ref] = ComponentPlacement(
                ref=ref, position=(pos_x, pos_y), rotation=0, confidence=0.7,
                placed_by="functional_module_clustering",
            )
    return placements


def _rust_place_power_flow(nodes, board, context, horizontal: bool):
    """Mirrors ``PowerFlowTopologyHeuristic._place_power_flow`` once wired."""
    power_flow_positions = rust(_RUST_MODULE, "power_flow_positions_py")
    placements: dict[str, ComponentPlacement] = {}
    ox, oy = board.origin
    margin = context.constraints.board_margin_mm

    stages: dict[int, list[str]] = {0: [], 1: [], 2: []}
    for node in nodes:
        if node.ref not in context.current_placements:
            stages[node.stage].append(node.ref)

    stage_counts = [len(stages[0]), len(stages[1]), len(stages[2])]
    per_stage = power_flow_positions(ox, oy, board.width, board.height, margin, stage_counts, horizontal)

    for stage, refs in stages.items():
        for ref, (pos_x, pos_y) in zip(refs, per_stage[stage], strict=True):
            comp = context.netlist.get_component(ref)
            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[ref] = ComponentPlacement(
                    ref=ref, position=(pos_x, pos_y), rotation=0, confidence=0.65,
                    placed_by="power_flow_topology",
                )
    return placements


def _rust_place_decoupling_caps(cap_to_ic, context):
    """Mirrors ``DecouplingCapHeuristic._place_decoupling_caps`` once wired."""
    decoupling_candidate_positions = rust(_RUST_MODULE, "decoupling_candidate_positions_py")
    placements: dict[str, ComponentPlacement] = {}
    for cap_ref, ic_ref in cap_to_ic.items():
        if cap_ref in context.current_placements:
            continue
        cap_comp = context.netlist.get_component(cap_ref)
        if ic_ref not in context.current_placements:
            continue
        ic_pos = context.current_placements[ic_ref].position
        ic_comp = context.netlist.get_component(ic_ref)
        candidates = decoupling_candidate_positions(ic_pos[0], ic_pos[1], ic_comp.width, cap_comp.width)
        for pos_x, pos_y in candidates:
            if context.is_position_valid(
                pos_x, pos_y, cap_comp.width, cap_comp.height
            ) and not context.check_overlap(pos_x, pos_y, cap_comp.width, cap_comp.height):
                placements[cap_ref] = ComponentPlacement(
                    ref=cap_ref, position=(pos_x, pos_y), rotation=0, confidence=0.8,
                    placed_by="decoupling_cap_positioning",
                )
                break
    return placements


def _rust_place_by_domain(domains, board, context):
    """Mirrors ``DomainSeparationHeuristic._place_by_domain`` once wired."""
    domain_grid_positions = rust(_RUST_MODULE, "domain_grid_positions_py")
    placements: dict[str, ComponentPlacement] = {}
    ox, oy = board.origin
    margin = context.constraints.board_margin_mm

    regions = {
        "power": (ox + margin, oy + margin, ox + board.width * 0.4, oy + board.height - margin),
        "digital": (
            ox + board.width * 0.5, oy + board.height * 0.4,
            ox + board.width - margin, oy + board.height - margin,
        ),
        "analog": (
            ox + board.width * 0.5, oy + margin,
            ox + board.width - margin, oy + board.height * 0.35,
        ),
    }

    domain_components: dict[str, list[str]] = {"power": [], "digital": [], "analog": []}
    for ref, domain in domains.items():
        if ref not in context.current_placements and not context.netlist.get_component(ref).fixed:
            domain_components[domain].append(ref)

    for domain, refs in domain_components.items():
        if not refs:
            continue
        x_min, y_min, x_max, y_max = regions[domain]
        positions = domain_grid_positions(len(refs), x_min, y_min, x_max, y_max)
        for ref, (pos_x, pos_y) in zip(refs, positions, strict=True):
            comp = context.netlist.get_component(ref)
            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[ref] = ComponentPlacement(
                    ref=ref, position=(pos_x, pos_y), rotation=0, confidence=0.6,
                    placed_by="domain_separation",
                )
    return placements


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "b9c766059c34649c2947f04f89a578fdb48a2756"
_ORACLE_PATH = "packages/temper-placer/src/temper_placer/heuristics/organizational.py"


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
    first, not the real import line.
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


def _board(width=100.0, height=100.0, origin=(0.0, 0.0)) -> Board:
    return Board(width=width, height=height, origin=origin)


def _constraints(board_margin_mm: float = 5.0, component_groups=None) -> PlacementConstraints:
    return PlacementConstraints(board_margin_mm=board_margin_mm, component_groups=component_groups or [])


# ---------------------------------------------------------------------------
# Site 1: FunctionalModuleClusteringHeuristic (module grid + circle offsets)
# ---------------------------------------------------------------------------


def _module_clustering_case():
    # Deliberately: one module of 1 (n==1 -> circle_offsets no-op branch),
    # one of 3 (odd n, exercises non-axis-aligned angles), one of 5
    # (n_modules total >= 4 exercises the sqrt/grid-dims code path with
    # cols>1).
    refs_a = ["A1"]
    refs_b = ["B1", "B2", "B3"]
    refs_c = ["C1", "C2", "C3", "C4", "C5"]
    all_refs = refs_a + refs_b + refs_c
    components = [Component(ref=r, footprint="R_0402", bounds=(1.2, 0.8)) for r in all_refs]
    netlist = Netlist(components=components, nets=[])
    board = _board(width=120.0, height=90.0)
    constraints = _constraints(
        board_margin_mm=4.0,
        component_groups=[
            ComponentGroup(name="grp_a", components=refs_a),
            ComponentGroup(name="grp_b", components=refs_b),
            ComponentGroup(name="grp_c", components=refs_c),
        ],
    )
    return netlist, board, constraints


def test_functional_module_clustering_matches_oracle():
    netlist, board, constraints = _module_clustering_case()

    modules = ORACLE.identify_functional_modules(netlist, constraints)
    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_heuristic = ORACLE.FunctionalModuleClusteringHeuristic()
    oracle_placements = oracle_heuristic._place_modules(modules=modules, board=board, context=ctx_oracle)

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_modules(modules=modules, board=board, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)


def test_functional_module_clustering_nonvacuous():
    netlist, board, constraints = _module_clustering_case()
    modules = ORACLE.identify_functional_modules(netlist, constraints)
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    placements = ORACLE.FunctionalModuleClusteringHeuristic()._place_modules(
        modules=modules, board=board, context=ctx
    )
    assert len(placements) == 9, "fixture should place all 9 components"


# ---------------------------------------------------------------------------
# Site 2: PowerFlowTopologyHeuristic (grid stage layout, both directions)
# ---------------------------------------------------------------------------


def _power_flow_case():
    refs = {
        "input": ["J1_DC"],
        "dist": ["U1_BUCK", "U2_LDO"],
        "load": ["U1_MCU", "U2_GATE", "U3_DRV"],
    }
    components = [
        Component(ref=r, footprint="X", bounds=(3.0, 2.0))
        for group in refs.values() for r in group
    ]
    netlist = Netlist(components=components, nets=[])
    board = _board(width=150.0, height=90.0)
    constraints = _constraints(board_margin_mm=6.0)
    return netlist, board, constraints


@pytest.mark.parametrize("horizontal", [True, False])
def test_power_flow_topology_matches_oracle(horizontal):
    netlist, board, constraints = _power_flow_case()
    nodes = ORACLE.classify_power_topology(netlist, constraints)

    flow_direction = "left_to_right" if horizontal else "top_to_bottom"
    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_heuristic = ORACLE.PowerFlowTopologyHeuristic(flow_direction=flow_direction)
    oracle_placements = oracle_heuristic._place_power_flow(nodes=nodes, board=board, context=ctx_oracle)

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_power_flow(nodes=nodes, board=board, context=ctx_rust, horizontal=horizontal)

    assert sig(oracle_placements) == sig(rust_placements)


def test_power_flow_topology_nonvacuous():
    netlist, board, constraints = _power_flow_case()
    nodes = ORACLE.classify_power_topology(netlist, constraints)
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    placements = ORACLE.PowerFlowTopologyHeuristic()._place_power_flow(nodes=nodes, board=board, context=ctx)
    assert len(placements) >= 5


# ---------------------------------------------------------------------------
# Site 3: DecouplingCapHeuristic (candidate positions around a placed IC)
# ---------------------------------------------------------------------------


def _decoupling_case():
    components = [
        Component(ref="U1_MCU", footprint="QFN", bounds=(7.0, 7.0)),
        Component(ref="C_DEC1", footprint="C_0402", bounds=(1.0, 0.5)),
    ]
    nets = [
        Net(name="VCC", pins=[("U1_MCU", "1"), ("C_DEC1", "1")], net_class="Power"),
        Net(name="GND", pins=[("U1_MCU", "2"), ("C_DEC1", "2")], net_class="Power"),
    ]
    netlist = Netlist(components=components, nets=nets)
    board = _board(width=60.0, height=60.0)
    constraints = _constraints(board_margin_mm=3.0)
    return netlist, board, constraints


def test_decoupling_cap_positioning_matches_oracle():
    netlist, board, constraints = _decoupling_case()
    cap_to_ic = ORACLE.identify_decoupling_caps(netlist)
    assert cap_to_ic == {"C_DEC1": "U1_MCU"}, "fixture must actually pair the cap with the IC"

    seeded = {"U1_MCU": (30.0, 30.0)}
    placed = {
        ref: ComponentPlacement(ref=ref, position=xy, rotation=0, confidence=1.0)
        for ref, xy in seeded.items()
    }

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints, current_placements=dict(placed))
    oracle_placements = ORACLE.DecouplingCapHeuristic()._place_decoupling_caps(cap_to_ic=cap_to_ic, context=ctx_oracle)

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints, current_placements=dict(placed))
    rust_placements = _rust_place_decoupling_caps(cap_to_ic=cap_to_ic, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)


def test_decoupling_cap_positioning_nonvacuous():
    netlist, board, constraints = _decoupling_case()
    cap_to_ic = ORACLE.identify_decoupling_caps(netlist)
    seeded = {"U1_MCU": ComponentPlacement(ref="U1_MCU", position=(30.0, 30.0), rotation=0, confidence=1.0)}
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints, current_placements=seeded)
    placements = ORACLE.DecouplingCapHeuristic()._place_decoupling_caps(cap_to_ic=cap_to_ic, context=ctx)
    assert "C_DEC1" in placements


# ---------------------------------------------------------------------------
# Site 4: DomainSeparationHeuristic (region grid layout, three domains)
# ---------------------------------------------------------------------------


def _domain_separation_case():
    refs = {
        "power": ["Q1", "Q2", "U1_BUCK"],
        "digital": ["U1_MCU", "Y1"],
        "analog": ["U1_OPAMP", "U2_ADC", "R1_SENSE"],
    }
    components = [
        Component(ref=r, footprint="X", bounds=(2.0, 2.0))
        for group in refs.values() for r in group
    ]
    netlist = Netlist(components=components, nets=[])
    board = _board(width=200.0, height=140.0)
    constraints = _constraints(board_margin_mm=5.0)
    return netlist, board, constraints


def test_domain_separation_matches_oracle():
    netlist, board, constraints = _domain_separation_case()
    domains = ORACLE.classify_signal_domains(netlist, constraints)

    ctx_oracle = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    oracle_placements = ORACLE.DomainSeparationHeuristic()._place_by_domain(domains=domains, board=board, context=ctx_oracle)

    ctx_rust = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    rust_placements = _rust_place_by_domain(domains=domains, board=board, context=ctx_rust)

    assert sig(oracle_placements) == sig(rust_placements)


def test_domain_separation_nonvacuous():
    netlist, board, constraints = _domain_separation_case()
    domains = ORACLE.classify_signal_domains(netlist, constraints)
    ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
    placements = ORACLE.DomainSeparationHeuristic()._place_by_domain(domains=domains, board=board, context=ctx)
    assert len(placements) == 8, "fixture should place all 8 components across the three domains"
