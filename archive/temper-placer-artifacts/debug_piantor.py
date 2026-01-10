import jax.numpy as jnp
from tests.fixtures.external import get_pcb_path
from temper_placer.losses.plane_integrity import analyze_plane_integrity
from temper_placer.routing.layer_assignment import assign_layers
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.net_ordering import order_nets

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses import (
    BoundaryLoss,
    CompositeLoss,
    LossContext,
    OverlapLoss,
    WeightedLoss,
    WirelengthLoss,
)
from temper_placer.optimizer import (
    AdaptiveOverlapConfig,
    CurriculumPhase,
    EarlyStoppingConfig,
    InitializationConfig,
    OptimizerConfig,
)
from temper_placer.optimizer.config import LearningRateSchedule
from temper_placer.visualization import create_board_view_from_state, render_board

project_name = "piantor_right"
pcb_path = get_pcb_path(project_name)
result = parse_kicad_pcb(pcb_path)
netlist, board = result.netlist, result.board
print(f"Board Dimensions: {board.width} x {board.height}")
print(f"Loaded netlist with {len(netlist.components)} components.")
print(f"First component {netlist.components[0].ref} initial pos: {netlist.components[0].initial_position}")
fixed_count = sum(1 for c in netlist.components if c.fixed)
print(f"Fixed components: {fixed_count}")

# Define loss factory for multiphase training
def make_loss_factory(weights):
    return CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
        WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
        WeightedLoss(WirelengthLoss(), weight=weights.get("wirelength", 10.0)),
    ])

# Run Optimizer with robust 2-phase settings
phases = [
    CurriculumPhase(
        name="explosion",
        start_epoch=0,
        end_epoch=3000,
        loss_weights={
            "overlap": 5000.0,
            "boundary": 1000.0,
            "wirelength": 0.0,
        }
    ),
    CurriculumPhase(
        name="refinement",
        start_epoch=2000,
        end_epoch=8000,
        loss_weights={
            "overlap": 5000.0,
            "boundary": 1000.0,
            "wirelength": 1.0,
        }
    )
]

context = LossContext.from_netlist_and_board(netlist, board)

config = OptimizerConfig(
    epochs=8000,
    seed=42,
    initialization=InitializationConfig(method="spectral"),
    learning_rate=LearningRateSchedule(initial=0.5, final=0.01),
    early_stopping=EarlyStoppingConfig(enabled=False),
    gradient_clip_norm=10.0,
    adaptive_overlap=AdaptiveOverlapConfig(enabled=True, ramp_rate=1.1, max_cap=100.0),
    curriculum_phases=phases
)

from temper_placer.optimizer import train_multiphase

# Debug: Run phase-by-phase trace? No, just run it.
opt_result = train_multiphase(
    netlist=netlist,
    board=board,
    loss_factory=make_loss_factory,
    context=context,
    config=config,
)

# Run Post-Processing
from temper_placer.optimizer.postprocess import PostProcessConfig, postprocess

print("\nRunning Post-Processing...")
pp_config = PostProcessConfig(
    grid_snap_enabled=True,
    grid_size=0.5,
    legalization_enabled=True,
    legalization_iterations=2000, # Massive iterations now possible with NumPy
    local_search_enabled=False, # Disable to avoid JAX recompilation
    local_search_iterations=0,
)

# We need a loss function for post-process that focuses on Overlap/Boundary
# This should match the "legalization" phase weights
def pp_loss_fn(state):
    # Quick stateless loss eval using context variables or re-creation
    # Actually, we can just use the final composite loss
    res = composite_loss(state.positions, state.rotation_logits, context)
    return float(res.value)

# Update composite_loss to final phase weights for post-processing
final_weights = phases[-1].loss_weights
composite_loss = make_loss_factory(final_weights)

pp_result = postprocess(
    state=opt_result.best_state,
    loss_fn=pp_loss_fn,
    config=pp_config,
    context=context,
    netlist=netlist,
    component_sizes=context.bounds, # Approximate sizes
)

# Use post-processed state for rendering/reporting
opt_result.best_state = pp_result.state
best_pos = pp_result.state.positions.tolist()
best_rot_indices = jnp.argmax(pp_result.state.rotation_logits, axis=-1)
best_rot_degrees = (best_rot_indices * 90.0).tolist()
# Get bounds
comp_bounds = [c.bounds for c in netlist.components]
component_refs = [c.ref for c in netlist.components]

# Calculate statuses based on overlaps
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.visualization.model import ComponentStatus

overlap_loss_fn = OverlapLoss()
overlap_res = overlap_loss_fn(
    opt_result.best_state.positions,
    opt_result.best_state.rotation_logits,
    context
)
per_comp_overlap = overlap_res.breakdown["per_component"]
statuses = [
    ComponentStatus.ERROR if per_comp_overlap[i] > 0.1 else ComponentStatus.OK
    for i in range(len(netlist.components))
]

# Debug red component positions
red_indices = [i for i, s in enumerate(statuses) if s == ComponentStatus.ERROR]
print("\nRed Component Positions (Top 3):")
for i in red_indices[:3]:
    comp = netlist.components[i]
    pos = opt_result.best_state.positions[i]
    print(f"  {comp.ref}: at {pos}, bounds {comp.bounds}")

board_view = create_board_view_from_state(
    board_width=board.width,
    board_height=board.height,
    component_refs=component_refs,
    positions=best_pos,
    rotations=best_rot_degrees,
    bounds=comp_bounds,
    statuses=statuses,
)
fig = render_board(board_view)
fig.write_html("piantor_right_debug.html")

print(f"Final Loss: {opt_result.final_loss:.4f}")
print(f"Total Epochs: {opt_result.total_epochs}")

# Report Loss Breakdown
# Re-create composite loss using final weights for reporting
final_weights = phases[-1].loss_weights
composite_loss = make_loss_factory(final_weights)

res = composite_loss(
    opt_result.best_state.positions,
    opt_result.best_state.rotation_logits,
    context,
    epoch=8000,
    total_epochs=8000
)
print(f"Total Weighted Loss: {res.value:.4f}")
for name, val in res.breakdown.items():
    # Handle both base names and suffixed breakdown keys
    weight = 1.0
    for w in composite_loss.losses:
        if name.startswith(w.loss_fn.name):
            weight = w.weight
            break
    print(f"  {name}: {jnp.sum(val):.4f} (weighted: {jnp.sum(val)*weight:.4f})")

# Report Overlaps
from temper_placer.losses.overlap import OverlapLoss

overlap_loss_fn = OverlapLoss(margin=0.2) # Add some margin for conservative reporting
overlap_res = overlap_loss_fn(
    opt_result.best_state.positions,
    opt_result.best_state.rotation_logits,
    context,
    epoch=8000,
    total_epochs=8000
)
print(f"Total Overlap Penalty: {overlap_res.value:.4f}")
if overlap_res.value > 0:
    per_comp = overlap_res.breakdown["per_component"]
    n_overlapping = jnp.sum(per_comp > 1e-6)
    print(f"Overlapping Components: {n_overlapping} / {len(netlist.components)}")
    max_overlap = jnp.max(per_comp)
    print(f"Max Per-Component Overlap: {max_overlap:.4f}")

# Verify Plane Preservation
print("\nVerifying Plane Preservation...")
from temper_placer.core.loop import LoopCollection

# Use a coarser grid for speed in debug script
router = MazeRouter.from_board(board, cell_size_mm=2.0)
router.block_components(netlist.components, opt_result.best_state.positions)

# Route top 20 most critical nets
net_order = order_nets(netlist, LoopCollection())[:20]
assignments = assign_layers(netlist)
results = router.route_all_nets(netlist, opt_result.best_state.positions, net_order, assignments)

plane_metrics = analyze_plane_integrity(results, board)
if not plane_metrics:
    print("No plane layers found in stackup.")
for m in plane_metrics:
    print(f"Layer {m.layer_name}: Vias={m.via_count}, Horizontal Segments={m.horizontal_segment_count}, Score={m.integrity_score:.2f}")
    if m.horizontal_segment_count > 0:
        print(f"WARNING: Horizontal segments detected on plane layer {m.layer_name}!")
    else:
        print(f"SUCCESS: No horizontal segments on plane layer {m.layer_name}.")
