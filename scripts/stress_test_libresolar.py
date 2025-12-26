"""
Stress test for the Hypergraph architecture on the Libresolar BMS (209 components).
"""

import time
import logging
import jax
import jax.numpy as jnp
from temper_placer.io import parse_kicad_pcb, load_constraints
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.physics.hypergraph_losses import hypergraph_wirelength_loss
from temper_placer.losses.physics.congestion import ElectrostaticCongestionLoss
from temper_placer.optimizer.train import train
from temper_placer.optimizer.config import OptimizerConfig, InitializationConfig
from temper_placer.losses.base import LossFunction, LossResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HypergraphWirelengthLoss(LossFunction):
    @property
    def name(self) -> str: return "wirelength"
    def __call__(self, pos, rot, ctx, ep=0, tep=1, vn=None) -> LossResult:
        if ctx.hypergraph is None: return LossResult(0.0)
        return LossResult(hypergraph_wirelength_loss(pos, ctx.hypergraph))

def run_stress_test():
    pcb_path = "packages/temper-placer/tests/fixtures/external/.cache/libresolar_bms/libresolar_bms_unrouted.kicad_pcb"
    constraints_path = "packages/temper-placer/tests/fixtures/external/.cache/libresolar_bms/libresolar_bms_constraints.yaml"
    
    logger.info(f"Loading PCB: {pcb_path}")
    res = parse_kicad_pcb(pcb_path)
    netlist = res.netlist
    board = res.board
    constraints = load_constraints(constraints_path)
    
    logger.info(f"Components: {netlist.n_components}, Nets: {netlist.n_nets}")
    
    ctx = LossContext.from_netlist_and_board(netlist, board, constraints)
    
    # Use the new Hypergraph Wirelength and Congestion
    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=500.0),
        WeightedLoss(BoundaryLoss(), weight=100.0),
        WeightedLoss(HypergraphWirelengthLoss(), weight=10.0),
        WeightedLoss(ElectrostaticCongestionLoss(), weight=5.0),
    ])
    
    config = OptimizerConfig(
        epochs=500, # Fast run
        seed=42,
        initialization=InitializationConfig(method="spectral"),
        log_interval=100,
    )
    
    logger.info("Starting optimization...")
    start = time.time()
    result = train(netlist, board, composite, ctx, config)
    end = time.time()
    
    logger.info(f"Optimization finished in {end - start:.2f} seconds")
    logger.info(f"Final Loss: {result.final_loss:.4f}")
    logger.info(f"Total Epochs: {result.total_epochs}")
    
    # Verify results
    from temper_placer.metrics.physics import measure_geometric
    metrics = measure_geometric(result.final_state, netlist, board)
    logger.info(f"Overlaps: {metrics.overlap_count}")
    logger.info(f"Boundary Violations: {metrics.boundary_violation_count}")
    
    if metrics.overlap_count == 0:
        logger.info("SUCCESS: Zero overlaps on 209-component board!")
    else:
        logger.warning(f"FAILED: {metrics.overlap_count} overlaps remain.")

if __name__ == "__main__":
    run_stress_test()