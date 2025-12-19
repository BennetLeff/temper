import sys
from pathlib import Path

import matplotlib.pyplot as plt

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses import BoundaryLoss, OverlapLoss, WirelengthLoss
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.optimizer import train_multiphase
from temper_placer.optimizer.config import (
    CurriculumPhase,
    LearningRateSchedule,
    OptimizerConfig,
    TemperatureSchedule,
)
from validation.test_placement_comparison import BaselineMetrics, get_project_paths


def make_loss(weights):
    return CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
        WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 200.0)),
        WeightedLoss(WirelengthLoss(), weight=weights.get("wirelength", 10.0)),
    ])

def debug_libresolar():
    project_name = "libresolar_bms"
    unrouted_path, baseline_path, constraints_path = get_project_paths(project_name)

    if not unrouted_path or not unrouted_path.exists():
        print(f"Project {project_name} not found.")
        return

    print(f"Loading {project_name}...")
    baseline = BaselineMetrics.from_yaml(baseline_path)
    print(f"Baseline Wirelength: {baseline.total_wirelength_mm:.1f} mm")

    # Parse PCB
    result = parse_kicad_pcb(unrouted_path)
    netlist = result.netlist
    board = result.board

    context = LossContext.from_netlist_and_board(netlist, board)

    # Curriculum Config
    # Phase 1: Wirelength focus (low overlap penalty) - 1000 epochs
    # Phase 2: Refinement (high overlap penalty) - 1000 epochs
    config = OptimizerConfig(
        epochs=4500,
        seed=12345,
        learning_rate=LearningRateSchedule(initial=0.5),
        temperature=TemperatureSchedule(start=2.0, end=0.1),
        log_interval=100,
        curriculum_phases=[
            CurriculumPhase(
                name="global_structure",
                start_epoch=0,
                end_epoch=1500,
                loss_weights={
                    "wirelength": 10.0,
                    "overlap": 1.0,
                    "boundary": 200.0
                }
            ),
            CurriculumPhase(
                name="intermediate",
                start_epoch=1500,
                end_epoch=3000,
                loss_weights={
                    "wirelength": 10.0,
                    "overlap": 20.0,
                    "boundary": 200.0
                }
            ),
            CurriculumPhase(
                name="legalization",
                start_epoch=3000,
                end_epoch=4500,
                loss_weights={
                    "wirelength": 10.0,
                    "overlap": 200.0,
                    "boundary": 200.0
                }
            )
        ]
    )

    print("Starting optimization with curriculum...")
    train_result = train_multiphase(netlist, board, make_loss, context, config)

    # Analysis
    history = train_result.history
    losses = [h.loss for h in history]
    wirelength = [h.loss_breakdown.get("wirelength", 0) for h in history]
    overlap = [h.loss_breakdown.get("overlap", 0) for h in history]
    boundary = [h.loss_breakdown.get("boundary", 0) for h in history]

    print("\nFinal Metrics:")
    print(f"Final Wirelength Loss: {wirelength[-1]:.2f}")

    # Calculate actual wirelength (unweighted)
    # WirelengthLoss returns HPWL directly, so divide by weight
    final_hpwl = wirelength[-1] # It's already the raw value in breakdown usually?
    # Wait, breakdown usually contains weighted or unweighted?
    # In CompositeLoss, breakdown stores the raw value from loss_fn(positions, ...).
    # So wirelength[-1] is the raw HPWL.

    print(f"Optimizer Wirelength: {final_hpwl:.1f} mm")
    print(f"Ratio: {final_hpwl / baseline.total_wirelength_mm:.2f}x")

    # Plot
    plt.figure(figsize=(12, 8))
    plt.subplot(2, 2, 1)
    plt.plot(losses)
    plt.title("Total Loss")
    plt.yscale('log')

    plt.subplot(2, 2, 2)
    plt.plot(wirelength)
    plt.title("Wirelength (mm)")

    plt.subplot(2, 2, 3)
    plt.plot(overlap)
    plt.title("Overlap Loss")
    plt.yscale('log')

    plt.subplot(2, 2, 4)
    plt.plot(boundary)
    plt.title("Boundary Loss")
    plt.yscale('log')

    plt.tight_layout()
    plt.savefig("libresolar_debug.png")
    print("Plot saved to libresolar_debug.png")

if __name__ == "__main__":
    debug_libresolar()
