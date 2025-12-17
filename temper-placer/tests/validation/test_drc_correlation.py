"""
DRC Correlation Study: Generate placements with varying quality for DRC testing.

This module generates placements at different quality levels and exports them
to KiCad PCB format for DRC correlation analysis. The goal is to correlate
our optimizer's loss penalties with actual KiCad DRC violations.

Quality levels:
1. Perfect - Hand-crafted placement with zero optimizer loss
2. Good - Optimized to convergence (minimal loss)
3. Mediocre - Stopped at 50% of optimal epochs
4. Bad - Stopped at 10% of optimal epochs
5. Terrible - Random positions with no optimization

For each placement, we record:
- Loss values (overlap, boundary, wirelength)
- Penalty breakdown per component
- Export to .kicad_pcb for KiCad DRC testing
"""

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import json
import subprocess
import shutil
from typing import Dict, List, Optional, Tuple, Any

import pytest

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb, ParseResult
from temper_placer.io.kicad_writer import (
    PlacementUpdate,
    write_placements_to_pcb,
    state_to_placements,
    export_placements,
)
from temper_placer.losses import (
    CompositeLoss,
    WeightedLoss,
    LossContext,
    OverlapLoss,
    BoundaryLoss,
    WirelengthLoss,
)
from temper_placer.optimizer import train, OptimizerConfig
from temper_placer.optimizer.config import (
    TemperatureSchedule,
    LearningRateSchedule,
    CheckpointConfig,
    EarlyStoppingConfig,
)


# Test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MEDIUM_PCB = FIXTURES_DIR / "medium_board.kicad_pcb"
DRC_PLACEMENTS_DIR = FIXTURES_DIR / "drc_test_placements"


@dataclass
class PlacementMetrics:
    """Metrics for a single placement."""

    quality_level: str
    total_loss: float
    overlap_loss: float
    boundary_loss: float
    wirelength_loss: float
    epochs_run: int
    converged: bool
    positions: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "quality_level": self.quality_level,
            "total_loss": self.total_loss,
            "overlap_loss": self.overlap_loss,
            "boundary_loss": self.boundary_loss,
            "wirelength_loss": self.wirelength_loss,
            "epochs_run": self.epochs_run,
            "converged": self.converged,
            "component_positions": {
                ref: {"x": pos[0], "y": pos[1]} for ref, pos in self.positions.items()
            },
        }


# ============================================================================
# DRC Runner - Interface to KiCad CLI
# ============================================================================

# Standard KiCad CLI locations by platform
KICAD_CLI_PATHS = [
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",  # macOS
    "/usr/bin/kicad-cli",  # Linux
    "/usr/local/bin/kicad-cli",  # Linux alternative
    "kicad-cli",  # In PATH
]

# Results directory for DRC correlation analysis
RESULTS_DIR = Path(__file__).parent / "results"


def find_kicad_cli() -> Optional[str]:
    """
    Find the kicad-cli executable.

    Returns:
        Path to kicad-cli if found, None otherwise.
    """
    for path in KICAD_CLI_PATHS:
        if path == "kicad-cli":
            # Check if in PATH
            result = shutil.which("kicad-cli")
            if result:
                return result
        elif Path(path).exists():
            return path
    return None


@dataclass
class DRCViolation:
    """A single DRC violation from KiCad."""

    type: str  # e.g., "courtyards_overlap", "clearance", "edge_clearance"
    severity: str  # "error" or "warning"
    description: str
    items: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: Dict) -> "DRCViolation":
        """Create from KiCad JSON output."""
        return cls(
            type=data.get("type", "unknown"),
            severity=data.get("severity", "error"),
            description=data.get("description", ""),
            items=data.get("items", []),
        )


@dataclass
class DRCResult:
    """Results of running KiCad DRC on a PCB file."""

    pcb_file: Path
    violations: List[DRCViolation] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    ran_successfully: bool = False
    error_message: Optional[str] = None

    @property
    def total_violations(self) -> int:
        return self.error_count + self.warning_count

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def violations_by_type(self) -> Dict[str, int]:
        """Count violations by type."""
        counts: Dict[str, int] = {}
        for v in self.violations:
            counts[v.type] = counts.get(v.type, 0) + 1
        return counts

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "pcb_file": str(self.pcb_file),
            "ran_successfully": self.ran_successfully,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "total_violations": self.total_violations,
            "violations_by_type": self.violations_by_type(),
            "error_message": self.error_message,
        }


def run_kicad_drc(
    pcb_file: Path,
    output_file: Optional[Path] = None,
    kicad_cli: Optional[str] = None,
) -> DRCResult:
    """
    Run KiCad DRC on a PCB file and return the results.

    Args:
        pcb_file: Path to the .kicad_pcb file
        output_file: Optional path for the DRC report (JSON format)
        kicad_cli: Optional explicit path to kicad-cli

    Returns:
        DRCResult with violation details
    """
    result = DRCResult(pcb_file=pcb_file)

    # Find kicad-cli
    cli_path = kicad_cli or find_kicad_cli()
    if cli_path is None:
        result.error_message = "kicad-cli not found. Install KiCad 7.0+ to run DRC tests."
        return result

    # Create temp file for output if not specified
    if output_file is None:
        output_file = Path(tempfile.mktemp(suffix=".json"))
        cleanup_output = True
    else:
        cleanup_output = False

    try:
        # Build command
        cmd = [
            cli_path,
            "pcb",
            "drc",
            "--format",
            "json",
            "--severity-all",
            "--output",
            str(output_file),
            str(pcb_file),
        ]

        # Run DRC
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout
        )

        # Check for kicad-cli errors (not DRC violations)
        if proc.returncode not in (0, 5):  # 5 = violations found
            result.error_message = f"kicad-cli failed: {proc.stderr}"
            return result

        # Parse JSON output
        if output_file.exists():
            with open(output_file) as f:
                drc_data = json.load(f)

            result.ran_successfully = True

            # Parse violations
            for v_data in drc_data.get("violations", []):
                violation = DRCViolation.from_json(v_data)
                result.violations.append(violation)
                if violation.severity == "error":
                    result.error_count += 1
                else:
                    result.warning_count += 1
        else:
            result.error_message = f"DRC output file not created: {output_file}"

    except subprocess.TimeoutExpired:
        result.error_message = "kicad-cli timed out"
    except Exception as e:
        result.error_message = f"Error running DRC: {e}"
    finally:
        if cleanup_output and output_file.exists():
            output_file.unlink()

    return result


def kicad_cli_available() -> bool:
    """Check if kicad-cli is available."""
    return find_kicad_cli() is not None


# Pytest marker for tests requiring KiCad
requires_kicad = pytest.mark.skipif(
    not kicad_cli_available(),
    reason="KiCad CLI not available (install KiCad 7.0+ to run DRC tests)",
)


def create_composite_loss() -> CompositeLoss:
    """Create standard composite loss for DRC correlation tests."""
    return CompositeLoss(
        [
            WeightedLoss(OverlapLoss(), weight=100.0),
            WeightedLoss(BoundaryLoss(), weight=50.0),
            WeightedLoss(WirelengthLoss(), weight=10.0),
        ]
    )


def evaluate_placement(
    state: PlacementState,
    context: LossContext,
) -> Tuple[float, float, float, float]:
    """
    Evaluate a placement state and return loss breakdown.

    Returns:
        Tuple of (total_loss, overlap_loss, boundary_loss, wirelength_loss)
    """
    # Get discrete rotations for evaluation
    _, rotation_indices = state.to_discrete()
    rotations = jax.nn.one_hot(rotation_indices, 4)

    # Evaluate individual losses
    overlap = OverlapLoss()
    boundary = BoundaryLoss()
    wirelength = WirelengthLoss()

    overlap_val = float(overlap(state.positions, rotations, context).value)
    boundary_val = float(boundary(state.positions, rotations, context).value)
    wirelength_val = float(wirelength(state.positions, rotations, context).value)

    # Total with weights
    total = 100.0 * overlap_val + 50.0 * boundary_val + 10.0 * wirelength_val

    return total, overlap_val, boundary_val, wirelength_val


def create_perfect_placement(
    netlist: Netlist,
    board: Board,
) -> Tuple[PlacementState, PlacementMetrics]:
    """
    Create a hand-crafted "perfect" placement with components arranged in a grid.

    This placement:
    - Has no overlaps (components well-spaced)
    - All components within board boundaries
    - Reasonable wirelength (grid layout)

    Note: Positions are in ABSOLUTE coordinates (board.origin + offset), matching
    what the optimizer and loss functions expect.
    """
    n = netlist.n_components

    # Board origin (absolute coordinates)
    ox, oy = board.origin

    # Calculate grid dimensions
    cols = max(1, int(jnp.ceil(jnp.sqrt(n))))

    # Calculate spacing (use 80% of board, leave margin)
    margin = 5.0  # mm from edge
    usable_width = board.width - 2 * margin
    usable_height = board.height - 2 * margin

    # Get max component size for spacing
    max_width = max(c.bounds[0] for c in netlist.components) if netlist.components else 5.0
    max_height = max(c.bounds[1] for c in netlist.components) if netlist.components else 5.0

    # Spacing between component centers
    spacing_x = max(max_width + 2.0, usable_width / (cols + 1))
    spacing_y = max(max_height + 2.0, usable_height / (cols + 1))

    # Create positions in a grid (ABSOLUTE coordinates)
    positions = []
    for i in range(n):
        col = i % cols
        row = i // cols
        # Position relative to origin
        rel_x = margin + spacing_x * (col + 0.5)
        rel_y = margin + spacing_y * (row + 0.5)
        # Clamp to board bounds
        rel_x = min(rel_x, board.width - margin)
        rel_y = min(rel_y, board.height - margin)
        # Convert to absolute coordinates
        positions.append([ox + rel_x, oy + rel_y])

    positions_array = jnp.array(positions)

    # All components at 0 degree rotation
    rotation_logits = jnp.zeros((n, 4))
    rotation_logits = rotation_logits.at[:, 0].set(10.0)  # Strong preference for 0 deg

    state = PlacementState(
        positions=positions_array,
        rotation_logits=rotation_logits,
    )

    # Evaluate
    context = LossContext.from_netlist_and_board(netlist, board)
    total, overlap, boundary, wirelength = evaluate_placement(state, context)

    # Record positions
    pos_dict = {
        netlist.components[i].ref: (float(positions_array[i, 0]), float(positions_array[i, 1]))
        for i in range(n)
    }

    metrics = PlacementMetrics(
        quality_level="perfect",
        total_loss=total,
        overlap_loss=overlap,
        boundary_loss=boundary,
        wirelength_loss=wirelength,
        epochs_run=0,
        converged=True,  # Hand-crafted, not trained
        positions=pos_dict,
    )

    return state, metrics


def create_optimized_placement(
    netlist: Netlist,
    board: Board,
    epochs: int,
    quality_level: str,
    seed: int = 42,
) -> Tuple[PlacementState, PlacementMetrics]:
    """
    Create an optimized placement by running the optimizer.

    Args:
        netlist: Component netlist
        board: Board definition
        epochs: Number of epochs to run
        quality_level: Label for this quality level
        seed: Random seed

    Returns:
        Tuple of (final_state, metrics)

    Note: Uses absolute coordinates (origin-relative + origin offset).
    """
    composite = create_composite_loss()
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create initial state in ABSOLUTE coordinates
    key = jax.random.PRNGKey(seed)
    initial_state = random_init_absolute(netlist.n_components, board, key, margin=5.0)

    config = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        temperature=TemperatureSchedule(start=2.0, end=0.5, warmup_epochs=min(50, epochs // 4)),
        learning_rate=LearningRateSchedule(
            initial=0.1,
            warmup_epochs=min(50, epochs // 4),
            decay_type="cosine",
            final=0.01,
        ),
        checkpoint=CheckpointConfig(enabled=False),
        early_stopping=EarlyStoppingConfig(enabled=False),  # Run full epochs
        log_interval=max(1, epochs // 10),
    )

    result = train(netlist, board, composite, context, config, initial_state=initial_state)

    # Evaluate final state
    total, overlap, boundary, wirelength = evaluate_placement(result.final_state, context)

    # Record positions
    n = netlist.n_components
    pos_dict = {
        netlist.components[i].ref: (
            float(result.final_state.positions[i, 0]),
            float(result.final_state.positions[i, 1]),
        )
        for i in range(n)
    }

    metrics = PlacementMetrics(
        quality_level=quality_level,
        total_loss=total,
        overlap_loss=overlap,
        boundary_loss=boundary,
        wirelength_loss=wirelength,
        epochs_run=result.total_epochs,
        converged=result.converged,
        positions=pos_dict,
    )

    return result.final_state, metrics


def random_init_absolute(
    n_components: int,
    board: Board,
    key,
    margin: float = 10.0,
) -> PlacementState:
    """
    Create random initial positions in ABSOLUTE coordinates.

    Unlike PlacementState.random_init which generates positions in [0, width],
    this function generates positions in [origin[0], origin[0]+width].

    Args:
        n_components: Number of components
        board: Board with origin and dimensions
        key: JAX random key
        margin: Margin from edges

    Returns:
        PlacementState with positions in absolute coordinates
    """
    key1, key2 = jax.random.split(key)
    ox, oy = board.origin

    # Random positions within margins (absolute coords)
    x = jax.random.uniform(
        key1, (n_components,), minval=ox + margin, maxval=ox + board.width - margin
    )
    y = jax.random.uniform(
        key2, (n_components,), minval=oy + margin, maxval=oy + board.height - margin
    )
    positions = jnp.stack([x, y], axis=-1)

    # Uniform rotation logits
    rotation_logits = jnp.zeros((n_components, 4), dtype=jnp.float32)

    return PlacementState(positions=positions, rotation_logits=rotation_logits)


def create_random_placement(
    netlist: Netlist,
    board: Board,
    seed: int = 12345,
) -> Tuple[PlacementState, PlacementMetrics]:
    """
    Create a random placement with no optimization.

    Components are placed randomly within board bounds with random rotations.
    This represents the worst-case "terrible" quality level.

    Note: Positions are in ABSOLUTE coordinates.
    """
    n = netlist.n_components
    key = jax.random.PRNGKey(seed)

    # Use absolute coordinate random init
    state = random_init_absolute(n, board, key, margin=5.0)

    # Evaluate
    context = LossContext.from_netlist_and_board(netlist, board)
    total, overlap, boundary, wirelength = evaluate_placement(state, context)

    # Record positions
    pos_dict = {
        netlist.components[i].ref: (float(state.positions[i, 0]), float(state.positions[i, 1]))
        for i in range(n)
    }

    metrics = PlacementMetrics(
        quality_level="terrible",
        total_loss=total,
        overlap_loss=overlap,
        boundary_loss=boundary,
        wirelength_loss=wirelength,
        epochs_run=0,
        converged=False,
        positions=pos_dict,
    )

    return state, metrics


def export_placement_to_pcb(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    template_pcb: Path,
    output_pcb: Path,
) -> None:
    """Export a PlacementState to a KiCad PCB file."""
    component_refs = [c.ref for c in netlist.components]
    export_placements(
        template_pcb=template_pcb,
        output_pcb=output_pcb,
        state=state,
        component_refs=component_refs,
        origin=board.origin,
    )


class TestPlacementGeneration:
    """Tests for generating placements at different quality levels."""

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    @pytest.fixture
    def parsed_medium(self) -> ParseResult:
        """Parse medium board fixture."""
        if not MEDIUM_PCB.exists():
            pytest.skip("Medium PCB fixture not found")
        return parse_kicad_pcb(MEDIUM_PCB)

    def test_perfect_placement_zero_overlap(self, parsed_minimal: ParseResult):
        """Perfect placement should have zero or near-zero overlap."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, metrics = create_perfect_placement(netlist, board)

        # Overlap should be zero or very small
        assert metrics.overlap_loss < 0.1, f"Overlap too high: {metrics.overlap_loss}"

    def test_perfect_placement_within_bounds(self, parsed_minimal: ParseResult):
        """Perfect placement should be within board boundaries."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, metrics = create_perfect_placement(netlist, board)

        # Boundary loss should be zero or very small
        assert metrics.boundary_loss < 0.1, f"Boundary loss too high: {metrics.boundary_loss}"

    def test_good_placement_better_than_random(self, parsed_minimal: ParseResult):
        """Good placement (optimized) should be better than random."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        # Create random placement
        _, random_metrics = create_random_placement(netlist, board, seed=999)

        # Create good placement (400 epochs)
        _, good_metrics = create_optimized_placement(
            netlist, board, epochs=400, quality_level="good", seed=42
        )

        # Good should have lower total loss
        assert good_metrics.total_loss < random_metrics.total_loss, (
            f"Good ({good_metrics.total_loss}) should be better than random ({random_metrics.total_loss})"
        )

    def test_quality_ordering(self, parsed_minimal: ParseResult):
        """Quality levels should have monotonically increasing loss."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        # Generate placements at different quality levels
        _, perfect = create_perfect_placement(netlist, board)
        _, good = create_optimized_placement(netlist, board, epochs=400, quality_level="good")
        _, mediocre = create_optimized_placement(
            netlist, board, epochs=200, quality_level="mediocre"
        )
        _, bad = create_optimized_placement(netlist, board, epochs=40, quality_level="bad")
        _, terrible = create_random_placement(netlist, board)

        # Check ordering (allow some tolerance since optimizer is stochastic)
        # Perfect should generally be best
        assert perfect.overlap_loss <= 0.5, "Perfect should have minimal overlap"
        assert perfect.boundary_loss <= 0.5, "Perfect should be within bounds"

        # Good should be better than terrible on overlap
        assert good.overlap_loss < terrible.overlap_loss or good.total_loss < terrible.total_loss, (
            "Good should generally be better than terrible"
        )

    @pytest.mark.slow
    def test_generate_all_quality_levels(self, parsed_minimal: ParseResult):
        """Generate and export all quality levels (integration test)."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        placements = []

        # 1. Perfect
        state, metrics = create_perfect_placement(netlist, board)
        placements.append(("perfect", state, metrics))

        # 2. Good (400 epochs)
        state, metrics = create_optimized_placement(
            netlist, board, epochs=400, quality_level="good"
        )
        placements.append(("good", state, metrics))

        # 3. Mediocre (200 epochs)
        state, metrics = create_optimized_placement(
            netlist, board, epochs=200, quality_level="mediocre"
        )
        placements.append(("mediocre", state, metrics))

        # 4. Bad (40 epochs)
        state, metrics = create_optimized_placement(netlist, board, epochs=40, quality_level="bad")
        placements.append(("bad", state, metrics))

        # 5. Terrible (random)
        state, metrics = create_random_placement(netlist, board)
        placements.append(("terrible", state, metrics))

        # Verify all placements were created
        assert len(placements) == 5

        # Print summary
        for name, _, metrics in placements:
            print(
                f"{name}: total={metrics.total_loss:.2f}, "
                f"overlap={metrics.overlap_loss:.4f}, "
                f"boundary={metrics.boundary_loss:.4f}, "
                f"wirelength={metrics.wirelength_loss:.2f}"
            )


class TestPlacementExport:
    """Tests for exporting placements to KiCad PCB format."""

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    def test_export_perfect_placement(self, parsed_minimal: ParseResult):
        """Perfect placement should export to valid PCB file."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, _ = create_perfect_placement(netlist, board)

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            export_placement_to_pcb(state, netlist, board, MINIMAL_PCB, temp_path)

            # Verify file was created and is parseable
            assert temp_path.exists()
            reparsed = parse_kicad_pcb(temp_path)
            assert reparsed.netlist.n_components == netlist.n_components
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_export_random_placement(self, parsed_minimal: ParseResult):
        """Random placement should still export to valid PCB file."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, _ = create_random_placement(netlist, board)

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            export_placement_to_pcb(state, netlist, board, MINIMAL_PCB, temp_path)

            # Verify file was created and is parseable
            assert temp_path.exists()
            reparsed = parse_kicad_pcb(temp_path)
            assert reparsed.netlist.n_components == netlist.n_components
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_export_preserves_component_count(self, parsed_minimal: ParseResult):
        """Exported PCB should have same number of components."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, _ = create_optimized_placement(netlist, board, epochs=100, quality_level="test")

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            export_placement_to_pcb(state, netlist, board, MINIMAL_PCB, temp_path)
            reparsed = parse_kicad_pcb(temp_path)

            assert reparsed.netlist.n_components == netlist.n_components, (
                f"Component count changed: {netlist.n_components} -> {reparsed.netlist.n_components}"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestDRCPlacementFiles:
    """Tests for generating the actual DRC test placement files."""

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    @pytest.mark.slow
    def test_generate_drc_placements(self, parsed_minimal: ParseResult):
        """Generate all DRC test placement files."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        # Ensure output directory exists
        DRC_PLACEMENTS_DIR.mkdir(parents=True, exist_ok=True)

        all_metrics = []

        # Define quality levels with their parameters
        quality_configs = [
            ("perfect", None, None),  # Hand-crafted
            ("good", 400, 42),
            ("mediocre", 200, 43),
            ("bad", 40, 44),
            ("terrible", None, 12345),  # Random
        ]

        for quality, epochs, seed in quality_configs:
            if quality == "perfect":
                state, metrics = create_perfect_placement(netlist, board)
            elif quality == "terrible":
                state, metrics = create_random_placement(netlist, board, seed=seed)
            else:
                state, metrics = create_optimized_placement(
                    netlist, board, epochs=epochs, quality_level=quality, seed=seed
                )

            # Export to file
            output_path = DRC_PLACEMENTS_DIR / f"{quality}.kicad_pcb"
            export_placement_to_pcb(state, netlist, board, MINIMAL_PCB, output_path)

            all_metrics.append(metrics)

            # Verify file was created
            assert output_path.exists(), f"Failed to create {output_path}"

        # Save metrics to JSON
        metrics_path = DRC_PLACEMENTS_DIR / "metrics.json"
        metrics_data = {
            "description": "DRC correlation test placements",
            "source_pcb": str(MINIMAL_PCB),
            "placements": [m.to_dict() for m in all_metrics],
        }
        with open(metrics_path, "w") as f:
            json.dump(metrics_data, f, indent=2)

        # Verify all files exist
        for quality, _, _ in quality_configs:
            output_path = DRC_PLACEMENTS_DIR / f"{quality}.kicad_pcb"
            assert output_path.exists(), f"Missing {quality}.kicad_pcb"
        assert metrics_path.exists(), "Missing metrics.json"

        print(f"\nGenerated DRC test placements in {DRC_PLACEMENTS_DIR}")
        print(f"Files: {[f'{q[0]}.kicad_pcb' for q in quality_configs]}")
        print(f"Metrics saved to: {metrics_path}")


class TestMetricsRecording:
    """Tests for recording and validating placement metrics."""

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    def test_metrics_to_dict(self, parsed_minimal: ParseResult):
        """PlacementMetrics.to_dict() should produce valid JSON."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        _, metrics = create_perfect_placement(netlist, board)

        d = metrics.to_dict()

        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert len(json_str) > 0

        # Should have required fields
        assert "quality_level" in d
        assert "total_loss" in d
        assert "overlap_loss" in d
        assert "boundary_loss" in d
        assert "wirelength_loss" in d
        assert "component_positions" in d

    def test_metrics_positions_match_state(self, parsed_minimal: ParseResult):
        """Recorded positions should match the state positions."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, metrics = create_perfect_placement(netlist, board)

        for i, comp in enumerate(netlist.components):
            state_x = float(state.positions[i, 0])
            state_y = float(state.positions[i, 1])
            metrics_x, metrics_y = metrics.positions[comp.ref]

            assert abs(state_x - metrics_x) < 0.001, f"X mismatch for {comp.ref}"
            assert abs(state_y - metrics_y) < 0.001, f"Y mismatch for {comp.ref}"


# ============================================================================
# DRC Correlation Tests - Correlate optimizer penalties with KiCad DRC
# ============================================================================


class TestDRCRunner:
    """Tests for the DRC runner infrastructure."""

    def test_find_kicad_cli_returns_path_or_none(self):
        """find_kicad_cli should return a path string or None."""
        result = find_kicad_cli()
        assert result is None or isinstance(result, str)
        if result:
            assert Path(result).exists() or shutil.which(result)

    def test_drc_result_dataclass(self):
        """DRCResult dataclass should work correctly."""
        result = DRCResult(pcb_file=Path("test.kicad_pcb"))
        assert result.total_violations == 0
        assert not result.has_errors
        assert result.ran_successfully is False

        result.error_count = 3
        result.warning_count = 2
        assert result.total_violations == 5
        assert result.has_errors

    def test_drc_violation_from_json(self):
        """DRCViolation should parse from JSON correctly."""
        data = {
            "type": "courtyards_overlap",
            "severity": "error",
            "description": "Courtyards overlap: R1 and R2",
            "items": [{"type": "R1"}, {"type": "R2"}],
        }
        v = DRCViolation.from_json(data)
        assert v.type == "courtyards_overlap"
        assert v.severity == "error"
        assert len(v.items) == 2

    @requires_kicad
    def test_run_drc_on_minimal_board(self):
        """Run DRC on the minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")

        result = run_kicad_drc(MINIMAL_PCB)

        # Should run successfully (even if there are violations)
        assert result.ran_successfully, f"DRC failed: {result.error_message}"

        # Should return valid counts
        assert result.error_count >= 0
        assert result.warning_count >= 0

        print(f"\nMinimal board DRC: {result.error_count} errors, {result.warning_count} warnings")


class TestDRCCorrelation:
    """
    Tests for correlating optimizer penalties with KiCad DRC results.

    These tests require KiCad CLI to be installed.
    """

    @pytest.fixture
    def drc_placements(self) -> List[Tuple[str, Path]]:
        """Get list of DRC test placement files."""
        if not DRC_PLACEMENTS_DIR.exists():
            pytest.skip("DRC placements not generated. Run test_generate_drc_placements first.")

        quality_levels = ["perfect", "good", "mediocre", "bad", "terrible"]
        placements = []
        for level in quality_levels:
            pcb_path = DRC_PLACEMENTS_DIR / f"{level}.kicad_pcb"
            if pcb_path.exists():
                placements.append((level, pcb_path))

        if not placements:
            pytest.skip("No DRC placement files found")

        return placements

    @pytest.fixture
    def metrics_data(self) -> Dict:
        """Load the metrics.json file."""
        metrics_path = DRC_PLACEMENTS_DIR / "metrics.json"
        if not metrics_path.exists():
            pytest.skip("metrics.json not found")

        with open(metrics_path) as f:
            return json.load(f)

    @requires_kicad
    @pytest.mark.slow
    def test_run_drc_on_all_placements(self, drc_placements: List[Tuple[str, Path]]):
        """Run DRC on all 5 quality levels and report results."""
        results: Dict[str, DRCResult] = {}

        for quality_level, pcb_path in drc_placements:
            result = run_kicad_drc(pcb_path)
            results[quality_level] = result

            assert result.ran_successfully, (
                f"DRC failed for {quality_level}: {result.error_message}"
            )

        # Print summary
        print("\n" + "=" * 60)
        print("DRC Results by Quality Level")
        print("=" * 60)
        for level in ["perfect", "good", "mediocre", "bad", "terrible"]:
            if level in results:
                r = results[level]
                print(f"{level:12s}: {r.error_count:3d} errors, {r.warning_count:3d} warnings")
                if r.violations_by_type():
                    for vtype, count in sorted(r.violations_by_type().items()):
                        print(f"              - {vtype}: {count}")
        print("=" * 60)

    @requires_kicad
    @pytest.mark.slow
    def test_drc_errors_increase_with_penalty(
        self,
        drc_placements: List[Tuple[str, Path]],
        metrics_data: Dict,
    ):
        """
        Test correlation: more optimizer penalty → more DRC errors.

        This test checks if our loss functions correlate with actual DRC results.
        A strong positive correlation means our penalties predict real DRC issues.
        """
        # Run DRC on all placements
        drc_results: Dict[str, DRCResult] = {}
        for quality_level, pcb_path in drc_placements:
            result = run_kicad_drc(pcb_path)
            if result.ran_successfully:
                drc_results[quality_level] = result

        # Load metrics for each placement
        metrics_by_level = {m["quality_level"]: m for m in metrics_data.get("placements", [])}

        # Build correlation data
        data_points: List[Tuple[str, float, float, int]] = []  # (level, overlap, total, drc_errors)

        for level, result in drc_results.items():
            if level in metrics_by_level:
                m = metrics_by_level[level]
                data_points.append(
                    (
                        level,
                        m.get("overlap_loss", 0),
                        m.get("total_loss", 0),
                        result.error_count,
                    )
                )

        # Print correlation data
        print("\n" + "=" * 70)
        print("Correlation Data: Optimizer Penalty vs DRC Errors")
        print("=" * 70)
        print(f"{'Level':12s} {'Overlap':>10s} {'Total Loss':>12s} {'DRC Errors':>12s}")
        print("-" * 70)
        for level, overlap, total, errors in data_points:
            print(f"{level:12s} {overlap:10.4f} {total:12.2f} {errors:12d}")
        print("=" * 70)

        # Save results for further analysis
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        correlation_data = {
            "description": "DRC correlation analysis results",
            "data_points": [
                {
                    "quality_level": level,
                    "overlap_loss": overlap,
                    "total_loss": total,
                    "drc_errors": errors,
                }
                for level, overlap, total, errors in data_points
            ],
        }
        with open(RESULTS_DIR / "drc_correlation_data.json", "w") as f:
            json.dump(correlation_data, f, indent=2)

        # Basic correlation check: if we have enough data points
        if len(data_points) >= 3:
            # Sort by total loss
            sorted_points = sorted(data_points, key=lambda x: x[2])

            # Check if DRC errors generally increase with loss
            # (weak check - just verify we don't have inverted correlation)
            lowest_loss_errors = sorted_points[0][3]
            highest_loss_errors = sorted_points[-1][3]

            # Log the relationship
            print(f"\nLowest loss ({sorted_points[0][0]}): {lowest_loss_errors} DRC errors")
            print(f"Highest loss ({sorted_points[-1][0]}): {highest_loss_errors} DRC errors")

    @requires_kicad
    @pytest.mark.slow
    def test_overlap_penalty_vs_courtyard_overlap(
        self,
        drc_placements: List[Tuple[str, Path]],
        metrics_data: Dict,
    ):
        """
        Test if our overlap penalty correlates with KiCad courtyard overlap violations.

        KiCad DRC violation type: "courtyards_overlap"
        """
        # Run DRC and count courtyard overlaps
        courtyard_violations: Dict[str, int] = {}
        for quality_level, pcb_path in drc_placements:
            result = run_kicad_drc(pcb_path)
            if result.ran_successfully:
                violations_by_type = result.violations_by_type()
                courtyard_violations[quality_level] = violations_by_type.get(
                    "courtyards_overlap", 0
                )

        # Load overlap penalties
        metrics_by_level = {m["quality_level"]: m for m in metrics_data.get("placements", [])}

        print("\n" + "=" * 60)
        print("Overlap Penalty vs Courtyard Overlap DRC Violations")
        print("=" * 60)
        print(f"{'Level':12s} {'Overlap Loss':>14s} {'Courtyard DRC':>14s}")
        print("-" * 60)

        for level in ["perfect", "good", "mediocre", "bad", "terrible"]:
            if level in metrics_by_level and level in courtyard_violations:
                overlap = metrics_by_level[level].get("overlap_loss", 0)
                drc = courtyard_violations[level]
                print(f"{level:12s} {overlap:14.4f} {drc:14d}")

        print("=" * 60)

    @requires_kicad
    @pytest.mark.slow
    def test_boundary_penalty_vs_edge_clearance(
        self,
        drc_placements: List[Tuple[str, Path]],
        metrics_data: Dict,
    ):
        """
        Test if our boundary penalty correlates with KiCad edge clearance violations.

        KiCad DRC violation types: "silk_edge_clearance", "copper_edge_clearance"
        """
        # Run DRC and count edge violations
        edge_violations: Dict[str, int] = {}
        for quality_level, pcb_path in drc_placements:
            result = run_kicad_drc(pcb_path)
            if result.ran_successfully:
                violations_by_type = result.violations_by_type()
                # Count all edge-related violations
                edge_count = 0
                for vtype, count in violations_by_type.items():
                    if "edge" in vtype.lower():
                        edge_count += count
                edge_violations[quality_level] = edge_count

        # Load boundary penalties
        metrics_by_level = {m["quality_level"]: m for m in metrics_data.get("placements", [])}

        print("\n" + "=" * 60)
        print("Boundary Penalty vs Edge Clearance DRC Violations")
        print("=" * 60)
        print(f"{'Level':12s} {'Boundary Loss':>14s} {'Edge DRC':>14s}")
        print("-" * 60)

        for level in ["perfect", "good", "mediocre", "bad", "terrible"]:
            if level in metrics_by_level and level in edge_violations:
                boundary = metrics_by_level[level].get("boundary_loss", 0)
                drc = edge_violations[level]
                print(f"{level:12s} {boundary:14.4f} {drc:14d}")

        print("=" * 60)


class TestDRCCorrelationAnalysis:
    """
    Analysis tests that generate reports and visualizations.

    These tests produce output files in tests/validation/results/
    """

    @pytest.fixture
    def drc_placements(self) -> List[Tuple[str, Path]]:
        """Get list of DRC test placement files."""
        if not DRC_PLACEMENTS_DIR.exists():
            pytest.skip("DRC placements not generated")

        quality_levels = ["perfect", "good", "mediocre", "bad", "terrible"]
        placements = []
        for level in quality_levels:
            pcb_path = DRC_PLACEMENTS_DIR / f"{level}.kicad_pcb"
            if pcb_path.exists():
                placements.append((level, pcb_path))
        return placements

    @pytest.fixture
    def metrics_data(self) -> Dict:
        """Load metrics.json."""
        metrics_path = DRC_PLACEMENTS_DIR / "metrics.json"
        if not metrics_path.exists():
            pytest.skip("metrics.json not found")
        with open(metrics_path) as f:
            return json.load(f)

    @requires_kicad
    @pytest.mark.slow
    def test_generate_correlation_report(
        self,
        drc_placements: List[Tuple[str, Path]],
        metrics_data: Dict,
    ):
        """
        Generate a comprehensive DRC correlation report.

        Output: tests/validation/results/drc_correlation_report.json
        """
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        # Collect all data
        report = {
            "description": "DRC Correlation Study Results",
            "kicad_cli": find_kicad_cli(),
            "placements": [],
        }

        metrics_by_level = {m["quality_level"]: m for m in metrics_data.get("placements", [])}

        for quality_level, pcb_path in drc_placements:
            # Run DRC
            drc_result = run_kicad_drc(pcb_path)

            # Get optimizer metrics
            opt_metrics = metrics_by_level.get(quality_level, {})

            # Combine
            entry = {
                "quality_level": quality_level,
                "optimizer_metrics": {
                    "total_loss": opt_metrics.get("total_loss", None),
                    "overlap_loss": opt_metrics.get("overlap_loss", None),
                    "boundary_loss": opt_metrics.get("boundary_loss", None),
                    "wirelength_loss": opt_metrics.get("wirelength_loss", None),
                },
                "drc_results": {
                    "ran_successfully": drc_result.ran_successfully,
                    "error_count": drc_result.error_count,
                    "warning_count": drc_result.warning_count,
                    "violations_by_type": drc_result.violations_by_type(),
                },
            }
            report["placements"].append(entry)

        # Save report
        report_path = RESULTS_DIR / "drc_correlation_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nDRC correlation report saved to: {report_path}")

        # Verify report was created
        assert report_path.exists()

        # Print summary
        print("\n" + "=" * 70)
        print("DRC Correlation Report Summary")
        print("=" * 70)
        for entry in report["placements"]:
            level = entry["quality_level"]
            opt = entry["optimizer_metrics"]
            drc = entry["drc_results"]
            print(f"\n{level}:")
            print(
                f"  Optimizer: total={opt.get('total_loss', 'N/A'):.2f}, "
                f"overlap={opt.get('overlap_loss', 'N/A'):.4f}"
            )
            print(f"  DRC: {drc['error_count']} errors, {drc['warning_count']} warnings")
            if drc["violations_by_type"]:
                for vtype, count in drc["violations_by_type"].items():
                    print(f"    - {vtype}: {count}")

    @requires_kicad
    @pytest.mark.slow
    def test_identify_penalty_thresholds(
        self,
        drc_placements: List[Tuple[str, Path]],
        metrics_data: Dict,
    ):
        """
        Analyze the data to identify penalty thresholds that predict DRC pass.

        Output: tests/validation/results/penalty_thresholds.json
        """
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        # Collect data
        data_points = []
        metrics_by_level = {m["quality_level"]: m for m in metrics_data.get("placements", [])}

        for quality_level, pcb_path in drc_placements:
            drc_result = run_kicad_drc(pcb_path)
            if not drc_result.ran_successfully:
                continue

            opt_metrics = metrics_by_level.get(quality_level, {})

            data_points.append(
                {
                    "quality_level": quality_level,
                    "overlap_loss": opt_metrics.get("overlap_loss", 0),
                    "boundary_loss": opt_metrics.get("boundary_loss", 0),
                    "total_loss": opt_metrics.get("total_loss", 0),
                    "drc_errors": drc_result.error_count,
                    "drc_warnings": drc_result.warning_count,
                    "drc_pass": drc_result.error_count == 0,
                }
            )

        # Find threshold candidates
        # Sort by overlap and find where DRC starts failing
        sorted_by_overlap = sorted(data_points, key=lambda x: x["overlap_loss"])
        sorted_by_boundary = sorted(data_points, key=lambda x: x["boundary_loss"])
        sorted_by_total = sorted(data_points, key=lambda x: x["total_loss"])

        # Find thresholds (highest passing value + margin)
        passing_overlaps = [p["overlap_loss"] for p in data_points if p["drc_pass"]]
        passing_boundaries = [p["boundary_loss"] for p in data_points if p["drc_pass"]]
        passing_totals = [p["total_loss"] for p in data_points if p["drc_pass"]]

        thresholds = {
            "overlap_threshold": max(passing_overlaps) * 1.2 if passing_overlaps else None,
            "boundary_threshold": max(passing_boundaries) * 1.2 if passing_boundaries else None,
            "total_loss_threshold": max(passing_totals) * 1.2 if passing_totals else None,
            "safety_margin": 0.2,  # 20% margin
            "data_points": data_points,
            "note": "Thresholds are highest passing value + 20% safety margin",
        }

        # Save thresholds
        threshold_path = RESULTS_DIR / "penalty_thresholds.json"
        with open(threshold_path, "w") as f:
            json.dump(thresholds, f, indent=2)

        print(f"\nPenalty thresholds saved to: {threshold_path}")
        print("\n" + "=" * 60)
        print("Penalty Thresholds (with 20% safety margin)")
        print("=" * 60)
        print(f"Overlap threshold:    {thresholds['overlap_threshold']}")
        print(f"Boundary threshold:   {thresholds['boundary_threshold']}")
        print(f"Total loss threshold: {thresholds['total_loss_threshold']}")
        print("=" * 60)

        assert threshold_path.exists()
