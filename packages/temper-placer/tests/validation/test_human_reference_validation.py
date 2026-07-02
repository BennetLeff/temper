"""Per-piece validation tests for the human-reference extraction chain.

Tests every link: trace extraction, via extraction, net-name resolution,
HPWL computation on real boards, overlap loss on a deliberately-overlapping
fixture, and boundary loss on an off-board fixture.
"""

import jax
import jax.numpy as jnp
import pytest
import yaml
from pathlib import Path

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import compute_total_hpwl
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Net, Pin


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _corpus_board_path(board_id: str, filename: str | None = None) -> Path:
    repo = Path(__file__).resolve().parents[4]
    board_dir = repo / "power_pcb_dataset" / "corpus" / board_id
    if filename is None:
        return board_dir
    return board_dir / filename

_CORPUS_BOARDS = ["piantor_right", "temper", "minimal", "rp2040_designguide", "bitaxe_ultra"]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _corpus_board_path(board_id: str, filename: str | None = None) -> Path:
    repo = Path(__file__).resolve().parents[4]
    board_dir = repo / "power_pcb_dataset" / "corpus" / board_id
    if filename is None:
        return board_dir
    return board_dir / filename


# ---------------------------------------------------------------------------
# Trace / via extraction on piantor_right (covers R3, R4)
# ---------------------------------------------------------------------------

@pytest.mark.l4_regression
class TestTraceAndViaExtraction:
    """Parser trace and via extraction validated against a real routed board."""

    @pytest.fixture(scope="class")
    def parse_result(self):
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        pcb_path = _corpus_board_path("piantor_right", "keyboard_pcb.kicad_pcb")
        if not pcb_path.exists():
            pytest.skip("piantor_right PCB not available")
        return parse_kicad_pcb(pcb_path)

    def test_trace_count_nonzero(self, parse_result):
        """R3: A routed board must have at least one trace."""
        assert len(parse_result.traces) > 0, "Expected traces on a routed board"

    def test_every_trace_net_is_named(self, parse_result):
        """R3: No trace falls back to '<Net object at 0x…>' placeholder."""
        net_names = {n.name for n in parse_result.netlist.nets}
        for t in parse_result.traces:
            assert t.net is not None, f"Trace has no net assigned"
            assert t.net in net_names, (
                f"Trace net '{t.net}' not found in parsed netlist — "
                "possible fallback to str(track.net) placeholder."
            )

    def test_via_count_nonzero(self, parse_result):
        """R4: A routed board must have at least one via."""
        assert len(parse_result.vias) > 0, "Expected vias on a routed board"

    def test_every_via_net_is_named(self, parse_result):
        """R4: No via falls back to a placeholder net name."""
        net_names = {n.name for n in parse_result.netlist.nets}
        for v in parse_result.vias:
            assert v.net is not None, f"Via has no net assigned"
            assert v.net in net_names, (
                f"Via net '{v.net}' not found in parsed netlist"
            )


# ---------------------------------------------------------------------------
# HPWL on real boards (covers R5)
# ---------------------------------------------------------------------------

@pytest.mark.l4_regression
class TestHPWLOnPiantorRight:
    """HPWL must be finite and strictly positive on a multi-component board."""

    @pytest.fixture(scope="class")
    def state_and_context(self):
        from temper_placer.validation.human_reference_extractor import _build_state_and_context
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        pcb_path = _corpus_board_path("piantor_right", "keyboard_pcb.kicad_pcb")
        if not pcb_path.exists():
            pytest.skip("piantor_right PCB not available")
        result = parse_kicad_pcb(pcb_path)
        return _build_state_and_context(result)

    def test_hpwl_positive_and_finite(self, state_and_context):
        """R5: HPWL is finite and > 0 for any board with multi-pin nets."""
        state, context = state_and_context
        rotations = jax.nn.softmax(state.rotation_logits, axis=-1)
        hpwl = float(compute_total_hpwl(state.positions, rotations, context))
        assert jnp.isfinite(hpwl), f"HPWL is non-finite: {hpwl}"
        assert hpwl > 0.0, f"HPWL is {hpwl}, expected > 0 on a board with multi-pin nets"


# ---------------------------------------------------------------------------
# Overlap loss fixture (covers R6, AE2)
# ---------------------------------------------------------------------------

class TestOverlapLossFixture:
    """Overlap loss must be strictly positive on a deliberately-overlapping fixture."""

    def test_overlap_loss_positive(self):
        """AE2: Two components at nearly identical positions → overlap_loss > 0."""
        c1 = Component(
            ref="R1",
            footprint="Resistor_SMD",
            bounds=(1.0, 2.0),
            initial_position=(5.0, 5.0),
            initial_rotation=0,
            initial_side="top",
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="N1"),
            ],
        )
        c2 = Component(
            ref="R2",
            footprint="Resistor_SMD",
            bounds=(1.0, 2.0),
            initial_position=(5.0, 5.0),  # deliberately overlapping
            initial_rotation=0,
            initial_side="top",
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="N1"),
            ],
        )
        components = [c1, c2]
        nets = [Net(name="N1", pins=[("R1", "1"), ("R2", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(origin=(0.0, 0.0), width=20.0, height=20.0)

        state = PlacementState.from_positions(
            jnp.array([[5.0, 5.0], [5.0, 5.0]], dtype=jnp.float32),
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        overlap = OverlapLoss(margin=1.0, rotation_invariant=True)
        result = overlap(state.positions, jax.nn.softmax(state.rotation_logits, axis=-1), context)
        assert float(result.value) > 0.0, (
            f"Overlap loss is {result.value}, expected > 0 on an overlapping fixture"
        )


# ---------------------------------------------------------------------------
# Boundary loss fixture (covers R6, AE3)
# ---------------------------------------------------------------------------

class TestBoundaryLossFixture:
    """Boundary loss must be strictly positive on a fixture with an off-board component."""

    def test_boundary_loss_positive(self):
        """AE3: One component placed off-board → boundary_loss > 0."""
        c1 = Component(
            ref="R1",
            footprint="Resistor_SMD",
            bounds=(1.0, 2.0),
            initial_position=(-10.0, -10.0),  # well outside the board
            initial_rotation=0,
            initial_side="top",
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="N1"),
            ],
        )
        components = [c1]
        nets = [Net(name="N1", pins=[("R1", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(origin=(0.0, 0.0), width=10.0, height=10.0)

        state = PlacementState.from_positions(
            jnp.array([[-10.0, -10.0]], dtype=jnp.float32),
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        boundary = BoundaryLoss()
        result = boundary(state.positions, jax.nn.softmax(state.rotation_logits, axis=-1), context)
        assert float(result.value) > 0.0, (
            f"Boundary loss is {result.value}, expected > 0 on an off-board fixture"
        )


# ---------------------------------------------------------------------------
# Per-board validation — all 5 corpus boards (covers R13)
# ---------------------------------------------------------------------------

@pytest.mark.l4_regression
@pytest.mark.parametrize("board_id", _CORPUS_BOARDS)
class TestAllCorpusBoards:
    """Every corpus board must pass per-piece validation."""

    def test_human_reference_yaml_committed(self, board_id: str):
        yaml_path = _corpus_board_path(board_id, "human_reference.yaml")
        assert yaml_path.exists(), f"human_reference.yaml not found for {board_id}"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        assert data["board_id"] == board_id
        assert "hpwl" in data["metrics"]
        hpwl = data["metrics"]["hpwl"]["value"]
        assert hpwl > 0.0, f"HPWL is {hpwl} for {board_id}, expected > 0"
        assert jnp.isfinite(data["metrics"]["overlap_loss"]["value"])
        assert jnp.isfinite(data["metrics"]["boundary_loss"]["value"])

    def test_net_names_resolve(self, board_id: str):
        """Every trace and via net resolves to a named net from the parsed netlist."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        kicad_files = list(_corpus_board_path(board_id).glob("*.kicad_pcb"))
        if not kicad_files:
            pytest.skip(f"No .kicad_pcb found for {board_id}")
        result = parse_kicad_pcb(str(kicad_files[0]))
        net_names = {n.name for n in result.netlist.nets}
        for t in result.traces:
            assert t.net is not None and t.net in net_names, (
                f"Trace net '{t.net}' on {board_id} not in parsed netlist"
            )
        for v in result.vias:
            assert v.net is not None and v.net in net_names, (
                f"Via net '{v.net}' on {board_id} not in parsed netlist"
            )


# ---------------------------------------------------------------------------
# Committed human_reference.yaml validation (covers AE5)
# ---------------------------------------------------------------------------

@pytest.mark.l4_regression
class TestCommittedPiantorRightReference:
    """The committed human_reference.yaml for piantor_right is valid."""

    def test_committed_yaml_valid(self):
        yaml_path = _corpus_board_path("piantor_right", "human_reference.yaml")
        if not yaml_path.exists():
            pytest.skip("piantor_right human_reference.yaml not yet committed")
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        assert data["board_id"] == "piantor_right"
        assert "hpwl" in data["metrics"]
        assert data["metrics"]["hpwl"]["value"] > 0.0
        assert jnp.isfinite(data["metrics"]["overlap_loss"]["value"])
        assert jnp.isfinite(data["metrics"]["boundary_loss"]["value"])
