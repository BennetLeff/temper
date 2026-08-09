"""R1a differential: the Wave-4 heuristics/ slice vs its pinned oracles.

Scope: the five remaining placement-heuristic modules --
``conflict.py``, ``topological_init.py``, ``spectral.py``,
``power_stage.py``, ``mcu_subsystem.py``. Verdict per module:

* ``conflict.py``       -- MIGRATE: the per-pair overlap scan
  (``check_conflict``) and the nudge-candidate selection
  (``_nudge_placement``) moved to
  ``temper_placement_topology.overlap_check`` / ``nudge_candidates``.
* ``topological_init.py`` -- MIGRATE: ``_check_feasibility``'s arithmetic
  (per-component fit decision, the two compensated ``sum()`` area totals)
  moved to ``temper_placement_topology.feasibility_check``.
* ``power_stage.py``    -- MIGRATE: both heuristics' boundary clamp moved to
  ``temper_placement_topology.clamp_position`` (numpy ``np.clip``
  semantics, B12).
* ``mcu_subsystem.py``  -- NO COMPUTE TO MIGRATE: its ``apply`` is a
  one-call delegation to ``place_power_stage_template``, which Phase 4
  already routed through ``temper_io_types.placer_place_power_stage_template``
  (``placer/deterministic.py``). This suite proves it structurally: the
  oracle is byte-identical to the pinned pre-migration file (nothing to
  shim) and the shipped ``apply`` provably reaches the Rust kernel.
* ``spectral.py``       -- JUSTIFIED-KEEP (networkx boundary): its compute
  is ``nx.spectral_layout(subgraph, weight="weight", dim=2)`` -- the
  eigenvector decomposition of the graph Laplacian via ``np.linalg.eigh``
  (LAPACK ``?syevd``), plus the ``np.random.uniform`` fallback (NumPy's
  PCG64 generator). See ``test_spectral_is_a_genuine_networkx_dependency``
  and the VERIFICATION.md note. This is the same judgment the repo already
  recorded for ``netlist.compute_eigenvector_centrality`` (R3 keep, named
  blocker: "No independent implementation reproduces LAPACK's output
  bit-for-bit" -- the eigenvector basis is only defined up to sign/rotation),
  and for ``topological/``'s networkx storage. A Rust re-implementation of
  an eigensolver is unreachable by R1a bit-parity, and a Rust wrapper that
  re-called ``numpy.linalg.eigh`` would add a boundary crossing while
  proving nothing.

Arms
----
* **oracle** -- ``tests/heuristics/_*_py_oracle.py``, verbatim ``git show``
  copies of the modules at their last-touching commits (see
  ``test_oracle_is_verbatim_copy``, which re-extracts and compares
  byte-for-byte).
* **rust** -- the SHIPPED modules, which now delegate to
  ``temper_placement_topology``. Comparing the shipped module against the
  oracle is strictly stronger than a synthetic adapter: it proves the
  production code path is bit-identical, not merely that some adapter that
  looks like it could be wired is. The monkeypatched-kernel tests at the
  bottom are the delegation proof (the differential would pass even if the
  shipped modules never called the extension).

Comparison is by **type-carrying signature** (``tests.router_v6._signature``),
``float.hex()`` at every float leaf, no tolerance anywhere.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

import tests.heuristics._conflict_py_oracle as CONFLICT_ORACLE
import tests.heuristics._mcu_subsystem_py_oracle as MCU_ORACLE
import tests.heuristics._power_stage_py_oracle as POWER_ORACLE
import tests.heuristics._topological_init_py_oracle as TOPO_ORACLE
from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Netlist
from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
from temper_placer.io.config_loader import PlacementConstraints
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

_RUST_MODULE = "temper_placement_topology"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "overlap_check",
    "nudge_candidates",
    "feasibility_check",
    "clamp_position",
)

_ORACLE_PINS: dict[str, str] = {
    "conflict": "cf2aad24b9030cdc8e026db3fb2e0938bad30a84",
    "topological_init": "b9c766059c34649c2947f04f89a578fdb48a2756",
    "power_stage": "5a17025b15d01bf88116b569493d8ed483e1856f",
    "mcu_subsystem": "5a17025b15d01bf88116b569493d8ed483e1856f",
}
_ORACLE_MODULES: dict[str, object] = {
    "conflict": CONFLICT_ORACLE,
    "topological_init": TOPO_ORACLE,
    "power_stage": POWER_ORACLE,
    "mcu_subsystem": MCU_ORACLE,
}


def _repo_root() -> Path:
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )


def _tail_after_module_docstring(src: str) -> str:
    """Everything in ``src`` after its own module docstring, unchanged."""
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


@pytest.mark.parametrize("name", sorted(_ORACLE_PINS))
def test_oracle_is_verbatim_copy(name: str):
    """Each oracle is byte-identical (past its own docstring) to the pin."""
    sha = _ORACLE_PINS[name]
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, check=True, cwd=_repo_root(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {sha} not present in this clone")

    pinned_src = subprocess.run(
        ["git", "show", f"{sha}:packages/temper-placer/src/temper_placer/heuristics/{name}.py"],
        capture_output=True, text=True, check=True, cwd=_repo_root(),
    ).stdout
    oracle_src = Path(_ORACLE_MODULES[name].__file__).read_text(encoding="utf-8")

    assert _tail_after_module_docstring(oracle_src) == _tail_after_module_docstring(pinned_src)


def test_rust_symbols_exist():
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert missing == [], f"still owed: {missing}"


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _board(width=100.0, height=100.0, zones=()) -> Board:
    return Board(width=width, height=height, origin=(0.0, 0.0), zones=list(zones))


def _context(board, netlist, margin=5.0, placement_priority=None, current_placements=None):
    return PlacementContext(
        board=board,
        netlist=netlist,
        constraints=PlacementConstraints(
            board_margin_mm=margin,
            placement_priority=placement_priority or {},
        ),
        current_placements=current_placements or {},
    )


def _conflict_netlist():
    return Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(10.0, 8.0)),
            Component(ref="R1", footprint="0805", bounds=(4.0, 2.0)),
            Component(ref="C1", footprint="0805", bounds=(4.0, 2.0)),
        ],
        nets=[],
    )


def _conflict_context():
    return _context(_board(), _conflict_netlist())


def _feasibility_netlist():
    return Netlist(
        components=[
            Component(ref="Q1", footprint="TO-247", bounds=(10.0, 15.0)),
            Component(ref="Q2", footprint="TO-247", bounds=(10.0, 15.0)),
            Component(ref="C1", footprint="0805", bounds=(2.0, 1.25)),
            Component(ref="U1", footprint="TSSOP-8", bounds=(3.0, 4.5)),
        ],
        nets=[],
    )


def _feasibility_context(margin=2.0):
    return _context(
        _board(
            zones=[
                Zone(name="HV_ZONE", bounds=(0.0, 0.0, 50.0, 100.0)),
                Zone(name="LV_ZONE", bounds=(50.0, 0.0, 100.0, 100.0)),
            ]
        ),
        _feasibility_netlist(),
        margin=margin,
    )


def _power_stage_netlist():
    return Netlist(
        components=[
            Component(ref="Q1", footprint="TO-247", bounds=(10.0, 8.0)),
            Component(ref="Q2", footprint="TO-247", bounds=(10.0, 8.0)),
            Component(ref="C_BUS1", footprint="CAP", bounds=(6.0, 4.0)),
            Component(ref="C_BUS2", footprint="CAP", bounds=(6.0, 4.0)),
            Component(ref="U_GATE1", footprint="SOIC-8", bounds=(5.0, 4.0)),
            Component(ref="C_BOOT1", footprint="0805", bounds=(2.0, 1.25)),
            Component(ref="C_VCC1", footprint="0805", bounds=(2.0, 1.25)),
            Component(ref="R_GATE_H1", footprint="0805", bounds=(2.0, 1.25)),
            Component(ref="R_GATE_L1", footprint="0805", bounds=(2.0, 1.25)),
        ],
        nets=[],
    )


# ---------------------------------------------------------------------------
# Site 1: conflict.py -- check_conflict
# ---------------------------------------------------------------------------


def _seeded_conflict_resolvers(strategy, min_spacing):
    oracle = CONFLICT_ORACLE.ConflictResolver(strategy=strategy, min_spacing_mm=min_spacing)
    shipped = __import__("temper_placer.heuristics.conflict", fromlist=["ConflictResolver"]).ConflictResolver(
        strategy=strategy, min_spacing_mm=min_spacing
    )
    for ref, pos in [("U1", (50.0, 50.0)), ("R1", (75.0, 25.0)), ("C1", (25.0, 75.0))]:
        p = ComponentPlacement(ref=ref, position=pos)
        oracle.add_placement(p)
        shipped.add_placement(p)
    return oracle, shipped


def test_conflict_check_conflict_identical():
    ctx = _conflict_context()
    oracle, shipped = _seeded_conflict_resolvers(None, 0.5)
    placement = ComponentPlacement(ref="X1", position=(52.0, 52.0))
    assert sig(oracle.check_conflict(placement, 4.0, 2.0, ctx)) == sig(
        shipped.check_conflict(placement, 4.0, 2.0, ctx)
    )


def test_conflict_check_conflict_no_conflict_identical():
    ctx = _conflict_context()
    oracle, shipped = _seeded_conflict_resolvers(None, 0.5)
    placement = ComponentPlacement(ref="X1", position=(10.0, 10.0))
    assert sig(oracle.check_conflict(placement, 4.0, 2.0, ctx)) == sig(
        shipped.check_conflict(placement, 4.0, 2.0, ctx)
    )


def test_conflict_check_conflict_self_excluded_identical():
    """A placement must not conflict with itself (the ref-skip branch)."""
    ctx = _conflict_context()
    oracle, shipped = _seeded_conflict_resolvers(None, 0.0)
    placement = ComponentPlacement(ref="U1", position=(50.0, 50.0))
    assert sig(oracle.check_conflict(placement, 10.0, 8.0, ctx)) == sig(
        shipped.check_conflict(placement, 10.0, 8.0, ctx)
    )


def test_conflict_min_spacing_is_part_of_the_overlap():
    """spacing grows overlap_x/y exactly as the oracle's formula."""
    ctx = _conflict_context()
    for spacing in (0.0, 0.5, 5.0):
        oracle, shipped = _seeded_conflict_resolvers(None, spacing)
        placement = ComponentPlacement(ref="X1", position=(55.0, 50.0))
        assert sig(oracle.check_conflict(placement, 4.0, 2.0, ctx)) == sig(
            shipped.check_conflict(placement, 4.0, 2.0, ctx)
        )


# ---------------------------------------------------------------------------
# Site 1b: conflict.py -- resolve / _nudge_placement
# ---------------------------------------------------------------------------


def test_conflict_resolve_nudge_identical():
    ctx = _conflict_context()
    oracle, shipped = _seeded_conflict_resolvers(None, 0.5)
    oracle.strategy = CONFLICT_ORACLE.ResolutionStrategy.NUDGE
    shipped.strategy = __import__(
        "temper_placer.heuristics.conflict", fromlist=["ResolutionStrategy"]
    ).ResolutionStrategy.NUDGE

    placement = ComponentPlacement(
        ref="X1", position=(52.0, 52.0), confidence=1.0, placed_by="test"
    )
    assert sig(oracle.resolve(placement, 4.0, 2.0, ctx)) == sig(
        shipped.resolve(placement, 4.0, 2.0, ctx)
    )


def test_conflict_resolve_reject_identical():
    ctx = _conflict_context()
    oracle, shipped = _seeded_conflict_resolvers(None, 0.5)
    oracle.strategy = CONFLICT_ORACLE.ResolutionStrategy.REJECT
    shipped.strategy = __import__(
        "temper_placer.heuristics.conflict", fromlist=["ResolutionStrategy"]
    ).ResolutionStrategy.REJECT

    placement = ComponentPlacement(ref="X1", position=(52.0, 52.0), confidence=1.0)
    assert sig(oracle.resolve(placement, 4.0, 2.0, ctx)) == sig(
        shipped.resolve(placement, 4.0, 2.0, ctx)
    )


def test_conflict_resolve_high_confidence_wins_identical():
    ctx = _conflict_context()
    oracle, shipped = _seeded_conflict_resolvers(None, 0.5)
    oracle.strategy = CONFLICT_ORACLE.ResolutionStrategy.HIGHER_CONFIDENCE_WINS
    shipped.strategy = __import__(
        "temper_placer.heuristics.conflict", fromlist=["ResolutionStrategy"]
    ).ResolutionStrategy.HIGHER_CONFIDENCE_WINS
    # raise the existing U1 confidence so the new, lower-confidence placement
    # is rejected rather than nudged
    for r in (oracle, shipped):
        r.placements["U1"].confidence = 0.9

    placement = ComponentPlacement(ref="X1", position=(52.0, 52.0), confidence=0.3)
    assert sig(oracle.resolve(placement, 4.0, 2.0, ctx)) == sig(
        shipped.resolve(placement, 4.0, 2.0, ctx)
    )


def test_conflict_resolve_conflict_log_is_identical():
    """Both arms must record the same Conflict objects (messages included)."""
    ctx = _conflict_context()
    oracle, shipped = _seeded_conflict_resolvers(None, 0.5)
    oracle.strategy = CONFLICT_ORACLE.ResolutionStrategy.NUDGE
    shipped.strategy = __import__(
        "temper_placer.heuristics.conflict", fromlist=["ResolutionStrategy"]
    ).ResolutionStrategy.NUDGE

    placement = ComponentPlacement(ref="X1", position=(52.0, 52.0), confidence=1.0)
    oracle.resolve(placement, 4.0, 2.0, ctx)
    shipped.resolve(placement, 4.0, 2.0, ctx)
    assert sig(oracle.get_all_conflicts()) == sig(shipped.get_all_conflicts())


# ---------------------------------------------------------------------------
# Site 2: topological_init.py -- _check_feasibility
# ---------------------------------------------------------------------------


def _feasibility_comparison(context, refs):
    oracle_heuristic = TOPO_ORACLE.TopologicalInitializationHeuristic()
    shipped_heuristic = __import__(
        "temper_placer.heuristics.topological_init", fromlist=["TopologicalInitializationHeuristic"]
    ).TopologicalInitializationHeuristic()
    return oracle_heuristic._check_feasibility(context, refs), shipped_heuristic._check_feasibility(
        context, refs
    )


def test_feasibility_identical_with_zones():
    ctx = _feasibility_context(margin=2.0)
    refs = ["Q1", "Q2", "C1", "U1"]
    oracle_result, shipped_result = _feasibility_comparison(ctx, refs)
    assert sig(oracle_result) == sig(shipped_result)


def test_feasibility_identical_without_zones():
    """The no-zone branch resolves zone_bounds to the board rectangle."""
    ctx = _context(_board(width=100.0, height=60.0), _feasibility_netlist(), margin=1.0)
    refs = ["Q1", "Q2", "C1", "U1"]
    oracle_result, shipped_result = _feasibility_comparison(ctx, refs)
    assert sig(oracle_result) == sig(shipped_result)


def test_feasibility_identical_when_component_too_large():
    """Q1 (10x15) against a 12x12 zone and a 8x100 zone: fits neither."""
    netlist = Netlist(components=[Component(ref="Q1", footprint="TO-247", bounds=(10.0, 15.0))])
    ctx = _context(
        _board(zones=[Zone(name="Z1", bounds=(0.0, 0.0, 12.0, 12.0))]),
        netlist,
        margin=0.0,
    )
    oracle_result, shipped_result = _feasibility_comparison(ctx, ["Q1"])
    assert not oracle_result.is_feasible
    assert sig(oracle_result) == sig(shipped_result)


def test_feasibility_identical_when_total_area_exceeds_packing():
    """Total area above 70% of zone area must produce the same message."""
    netlist = Netlist(
        components=[Component(ref=f"R{i}", footprint="R", bounds=(3.0, 3.0)) for i in range(6)]
    )
    ctx = _context(
        _board(zones=[Zone(name="Z1", bounds=(0.0, 0.0, 8.0, 8.0))]),
        netlist,
        margin=0.0,
    )
    refs = [f"R{i}" for i in range(6)]
    oracle_result, shipped_result = _feasibility_comparison(ctx, refs)
    # 6 * 9.0 = 54.0 > 64.0 * 0.7 = 44.8 -> packing conflict; each 3x3 fits in 8x8.
    assert any("Total component area" in c for c in oracle_result.conflicts)
    assert sig(oracle_result) == sig(shipped_result)


def test_feasibility_identical_with_nan_component_width():
    """A NaN width must fail both fit checks identically and not crash."""
    netlist = Netlist(components=[Component(ref="Q1", footprint="TO-247", bounds=(float("nan"), 5.0))])
    ctx = _context(
        _board(zones=[Zone(name="Z1", bounds=(0.0, 0.0, 100.0, 100.0))]),
        netlist,
        margin=0.0,
    )
    oracle_result, shipped_result = _feasibility_comparison(ctx, ["Q1"])
    assert not oracle_result.is_feasible
    assert sig(oracle_result) == sig(shipped_result)


def test_feasibility_identical_margin_erosion():
    """margin=0 vs margin=5 must change the verdict identically in both arms."""
    netlist = Netlist(
        components=[
            Component(ref=f"R{i}", footprint="R", bounds=(30.0, 30.0)) for i in range(7)
        ]
    )

    def run(margin):
        ctx = _context(
            _board(zones=[Zone(name="Z1", bounds=(0.0, 0.0, 100.0, 100.0))]),
            netlist,
            margin=margin,
        )
        refs = [f"R{i}" for i in range(7)]
        oracle_result, shipped_result = _feasibility_comparison(ctx, refs)
        assert sig(oracle_result) == sig(shipped_result)
        return oracle_result

    with_margin = run(5.0)
    without_margin = run(0.0)
    # 7x30x30 = 6300 mm^2: below 70% of the full 100x100 zone (7000) but above
    # 70% of the margin-eroded zone (90x90 -> 5670), so the packing check fires
    # exactly when the margin is non-zero -- the margin genuinely changes the
    # verdict, in both arms.
    assert not with_margin.is_feasible
    assert without_margin.is_feasible
    assert sig(with_margin) != sig(without_margin)


# ---------------------------------------------------------------------------
# Site 3: power_stage.py -- template + proximity placement
# ---------------------------------------------------------------------------


def _power_stage_template_comparison(context):
    oracle_h = POWER_ORACLE.PowerStageTemplateHeuristic()
    shipped_h = __import__(
        "temper_placer.heuristics.power_stage", fromlist=["PowerStageTemplateHeuristic"]
    ).PowerStageTemplateHeuristic()
    return oracle_h.apply(context), shipped_h.apply(context)


def _power_stage_driver_comparison(context):
    oracle_h = POWER_ORACLE.DriverProximityHeuristic()
    shipped_h = __import__(
        "temper_placer.heuristics.power_stage", fromlist=["DriverProximityHeuristic"]
    ).DriverProximityHeuristic()
    return oracle_h.apply(context), shipped_h.apply(context)


def test_power_stage_template_identical():
    ctx = _context(
        _board(width=120.0, height=90.0),
        _power_stage_netlist(),
        margin=5.0,
        placement_priority={"power": {"anchor": (75.0, 70.0)}},
    )
    oracle_result, shipped_result = _power_stage_template_comparison(ctx)
    assert set(oracle_result.placements) == {"Q1", "Q2", "C_BUS1", "C_BUS2"}
    assert sig(oracle_result) == sig(shipped_result)


def test_power_stage_template_default_anchor_identical():
    """No anchor in config -> board 0.75/0.75 default, in both arms."""
    ctx = _context(
        _board(width=120.0, height=90.0),
        _power_stage_netlist(),
        margin=5.0,
        placement_priority={"power": {}},
    )
    oracle_result, shipped_result = _power_stage_template_comparison(ctx)
    assert sig(oracle_result) == sig(shipped_result)


def test_power_stage_template_initial_position_identical():
    """The comp.initial_position branch bypasses the anchor+offset path."""
    netlist = Netlist(
        components=[
            Component(
                ref="Q1", footprint="TO-247", bounds=(10.0, 8.0), initial_position=(20.0, 30.0)
            ),
            Component(ref="Q2", footprint="TO-247", bounds=(10.0, 8.0)),
        ]
    )
    ctx = _context(
        _board(width=120.0, height=90.0),
        netlist,
        margin=5.0,
        placement_priority={"power": {"anchor": (75.0, 70.0)}},
    )
    oracle_result, shipped_result = _power_stage_template_comparison(ctx)
    assert sig(oracle_result) == sig(shipped_result)


def test_power_stage_driver_proximity_identical():
    """Driver components placed relative to a placed reference (Q1)."""
    ctx = _context(
        _board(width=120.0, height=90.0),
        _power_stage_netlist(),
        margin=5.0,
        placement_priority={"driver": {"reference": "Q1", "max_distance_mm": 20.0}},
        current_placements={"Q1": ComponentPlacement(ref="Q1", position=(75.0, 70.0))},
    )
    oracle_result, shipped_result = _power_stage_driver_comparison(ctx)
    assert sig(oracle_result) == sig(shipped_result)


def test_power_stage_driver_proximity_board_center_fallback_identical():
    """Reference not placed and no initial_position -> board center."""
    ctx = _context(
        _board(width=120.0, height=90.0),
        _power_stage_netlist(),
        margin=5.0,
        placement_priority={"driver": {"reference": "Q1", "max_distance_mm": 20.0}},
    )
    oracle_result, shipped_result = _power_stage_driver_comparison(ctx)
    assert sig(oracle_result) == sig(shipped_result)


def test_power_stage_missing_components_skipped_identical():
    """Template refs absent from the netlist are skipped identically."""
    netlist = Netlist(components=[Component(ref="Q1", footprint="TO-247", bounds=(10.0, 8.0))])
    ctx = _context(
        _board(width=120.0, height=90.0),
        netlist,
        margin=5.0,
        placement_priority={"power": {"anchor": (75.0, 70.0)}},
    )
    oracle_result, shipped_result = _power_stage_template_comparison(ctx)
    assert set(oracle_result.placements) == {"Q1"}
    assert sig(oracle_result) == sig(shipped_result)


# ---------------------------------------------------------------------------
# Site 4: mcu_subsystem.py -- pure delegation, structural proof
# ---------------------------------------------------------------------------


def test_mcu_subsystem_apply_delegates_to_rust():
    """``MCUSubsystemHeuristic.apply`` reaches
    ``temper_io_types.placer_place_power_stage_template`` -- the Phase-4 Rust
    kernel. If the production path drifts to a non-Rust implementation, the
    sentinel stops being raised."""
    import temper_io_types as _io

    from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic

    board = _board(zones=[Zone(name="MCU", bounds=(0.0, 0.0, 100.0, 100.0))])
    netlist = Netlist(
        components=[
            Component(ref="U_MCU", footprint="QFN", bounds=(7.0, 7.0)),
            Component(ref="Y1", footprint="XTAL", bounds=(2.0, 1.2)),
        ]
    )
    template_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "temper_placer"
        / "templates"
        / "mcu_subsystem.yaml"
    )

    sentinel = RuntimeError("REACHED_RUST_MCU_TEMPLATE")

    def boom(*_a, **_k):
        raise sentinel

    original = _io.placer_place_power_stage_template
    _io.placer_place_power_stage_template = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_MCU_TEMPLATE"):
            MCUSubsystemHeuristic(template_path=template_path).apply(netlist, board, "MCU")
    finally:
        _io.placer_place_power_stage_template = original

    # the fixture is meaningful: with the real kernel the same call succeeds
    result = MCUSubsystemHeuristic(template_path=template_path).apply(netlist, board, "MCU")
    assert set(result.placed_refs) >= {"U_MCU", "Y1"}


# ---------------------------------------------------------------------------
# Site 5: spectral.py -- JUSTIFIED-KEEP evidence
# ---------------------------------------------------------------------------

_SPECTRAL_PATH = (
    "packages/temper-placer/src/temper_placer/heuristics/spectral.py"
)


def test_spectral_is_a_genuine_networkx_dependency():
    """The spectral heuristic's compute is `nx.spectral_layout` -- the graph
    Laplacian eigenvector decomposition via `np.linalg.eigh` -- plus a
    `np.random.uniform` fallback. Neither is re-implementable under R1a
    bit-parity (eigenvector basis sign/rotation degeneracy; LAPACK backend
    variance), so the module is JUSTIFIED-KEEP'd at the networkx boundary,
    not ported. Assert the dependency directly so the evidence cannot rot.
    """
    src = Path(_repo_root() / _SPECTRAL_PATH).read_text(encoding="utf-8")
    assert "import networkx as nx" in src
    assert "nx.spectral_layout(subgraph, weight=" in src
    assert "nx.connected_components(G)" in src
    assert "np.linalg" in src or "np.random.uniform" in src
    # The same judgment is already recorded for the one other eigensolver in
    # the codebase (netlist.compute_eigenvector_centrality, R3 keep) -- the
    # spectral keep must cite that precedent rather than invent a new one.
    netlist_src = (
        Path(_repo_root() / "packages/temper-placer/src/temper_placer/core/netlist.py")
    ).read_text(encoding="utf-8")
    assert "compute_eigenvector_centrality" in netlist_src
    assert "stays Python" in netlist_src
    assert "numpy.linalg.eigh" in netlist_src


def test_spectral_module_is_unmodified():
    """A kept module must stay byte-identical to its pinned commit."""
    sha = "5a17025b15d01bf88116b569493d8ed483e1856f"
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, check=True, cwd=_repo_root(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {sha} not present in this clone")
    pinned_src = subprocess.run(
        ["git", "show", f"{sha}:{_SPECTRAL_PATH}"],
        capture_output=True, text=True, check=True, cwd=_repo_root(),
    ).stdout
    current = Path(_repo_root() / _SPECTRAL_PATH).read_text(encoding="utf-8")
    assert current == pinned_src


# ---------------------------------------------------------------------------
# Shipped-module delegation proof -- the monkeypatched-kernel gate.
#
# The numeric differentials above would pass whether or not the shipped
# modules call the extension. Patching each Rust symbol to raise and calling
# the shipped entry point proves the production path was rewired.
# ---------------------------------------------------------------------------

import temper_placement_topology as _RUST  # noqa: E402

import temper_placer.heuristics.conflict as shipped_conflict  # noqa: E402
import temper_placer.heuristics.power_stage as shipped_power_stage  # noqa: E402
import temper_placer.heuristics.topological_init as shipped_topo  # noqa: E402


def _patch_and_run(symbol: str, fn, *args):
    sentinel = RuntimeError(f"REACHED_RUST_{symbol.upper()}")
    original = getattr(_RUST, symbol)

    def boom(*_a, **_k):
        raise sentinel

    setattr(_RUST, symbol, boom)
    try:
        with pytest.raises(RuntimeError, match=f"REACHED_RUST_{symbol.upper()}"):
            fn(*args)
    finally:
        setattr(_RUST, symbol, original)


def test_conflict_check_conflict_delegates_to_rust():
    ctx = _conflict_context()
    _, shipped = _seeded_conflict_resolvers(None, 0.5)
    placement = ComponentPlacement(ref="X1", position=(52.0, 52.0))
    _patch_and_run("overlap_check", shipped.check_conflict, placement, 4.0, 2.0, ctx)


def test_conflict_nudge_delegates_to_rust():
    ctx = _conflict_context()
    _, shipped = _seeded_conflict_resolvers(None, 0.5)
    shipped.strategy = shipped_conflict.ResolutionStrategy.NUDGE
    placement = ComponentPlacement(ref="X1", position=(52.0, 52.0), confidence=1.0)
    _patch_and_run("nudge_candidates", shipped.resolve, placement, 4.0, 2.0, ctx)


def test_feasibility_delegates_to_rust():
    ctx = _feasibility_context(margin=2.0)
    shipped_h = shipped_topo.TopologicalInitializationHeuristic()
    _patch_and_run("feasibility_check", shipped_h._check_feasibility, ctx, ["Q1", "Q2", "C1", "U1"])


def test_power_stage_clamp_delegates_to_rust():
    ctx = _context(
        _board(width=120.0, height=90.0),
        _power_stage_netlist(),
        margin=5.0,
        placement_priority={"power": {"anchor": (75.0, 70.0)}},
    )
    shipped_h = shipped_power_stage.PowerStageTemplateHeuristic()
    _patch_and_run("clamp_position", shipped_h.apply, ctx)
