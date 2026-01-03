import os
import sys
import logging
import numpy as np

# Add package root to sys.path
sys.path.append(os.path.join(os.getcwd(), "packages/temper-placer/src"))

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Net, Component, Pin
from temper_placer.routing.c_space_pipeline import CSpaceRoutingPipeline, PipelineConfig

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def create_mock_project():
    """Create a minimal project for multi-res testing."""
    # Board with MCU Zone
    board = Board(width=40, height=40)
    board.zones = [Zone("MCU_ZONE", (10, 10, 30, 30))]
    
    # Netlist
    netlist = Netlist()
    
    # NET: SPI_MOSI (Fine net because it touches U1 in MCU_ZONE)
    net1 = Net(name="SPI_MOSI", pins=[("U1", "1"), ("J1", "1")])
    netlist.nets.append(net1)
    
    # NET: VCC (Standard net)
    net2 = Net(name="VCC", pins=[("J2", "1"), ("J1", "2")])
    netlist.nets.append(net2)
    
    # Component U1: Fine pitch MCU at (20, 20)
    nc1 = Component(ref="U1", footprint="FP1", bounds=(5, 5), initial_position=(20, 20), initial_rotation=0)
    nc1.pins = [
        Pin(name="1", number="1", position=(-0.5, 0), net="SPI_MOSI", width=0.2, height=0.4),
        Pin(name="2", number="2", position=(0.5, 0), net="SPI_SCK", width=0.2, height=0.4)
    ]
    
    # Component J1: Standard connector at (5, 5)
    nc2 = Component(ref="J1", footprint="CONN", bounds=(5, 5), initial_position=(5, 5), initial_rotation=0)
    nc2.pins = [
        Pin(name="1", number="1", position=(0, 0), net="SPI_MOSI", width=1.0, height=1.0),
        Pin(name="2", number="2", position=(0, 2), net="VCC", width=1.0, height=1.0)
    ]
    
    # Component J2: Power connector at (35, 35)
    nc3 = Component(ref="J2", footprint="PWR", bounds=(10, 10), initial_position=(35, 35), initial_rotation=0)
    nc3.pins = [
        Pin(name="1", number="1", position=(0, 0), net="VCC", width=2.0, height=2.0)
    ]
    
    netlist.components = [nc1, nc2, nc3]
    return board, netlist

def validate_multires():
    board, netlist = create_mock_project()
    
    config = PipelineConfig(
        resolution_mm=0.2,
        fine_resolution_mm=0.05,
        enable_smoothing=True
    )
    
    pipeline = CSpaceRoutingPipeline(board, netlist, config)
    logger.info("Extracting geometry...")
    pipeline.extract_geometry()
    
    # Test net classification
    logger.info("Verifying net classification...")
    assert pipeline._is_high_density_net("SPI_MOSI") == True, "SPI_MOSI should be Fine"
    assert pipeline._is_high_density_net("VCC") == False, "VCC should be Standard"
    logger.info("Net classification OK.")
    
    # Run full pipeline
    logger.info("Starting Multi-Resolution Routing Test...")
    net_order = ["SPI_MOSI", "VCC"]
    result = pipeline.route_all(net_order)
    
    logger.info(f"Routing Results: {result.completion_rate:.1f}% completion")
    for name, r in result.net_results.items():
        logger.info(f"  Net {name}: {'Success' if r.success else 'FAILED (' + (r.failure_reason or 'None') + ')'}")
        if r.success:
            logger.info(f"    Nodes: {len(r.cells)}, Vias: {r.via_count}")
    
    assert result.net_results["SPI_MOSI"].success, "Fine net should succeed"
    assert result.net_results["VCC"].success, "Standard net should succeed"
    
    # Verify that standard net avoided fine net
    logger.info("Verifying grid resize and occupancy preservation...")
    # Get the actual router being used
    router = pipeline.router
    # If DitheredRouter, we want the base
    from temper_placer.routing.dithered_router import DitheredRouter
    base_router = router.base_router if isinstance(router, DitheredRouter) else router
    
    assert base_router.cell_size == 0.2, f"Final router should be at coarse resolution (0.2), got {base_router.cell_size}"
    
    # Check if SPI_MOSI path is marked as occupied in the coarse grid
    mosi_path = result.net_results["SPI_MOSI"].cells
    assert len(mosi_path) > 0
    
    # Convert one to world, then to current 0.2mm grid
    # Use center of path
    sample_cell = mosi_path[len(mosi_path)//2]
    logger.info(f"Sample cell from fine path: x={sample_cell.x}, y={sample_cell.y}, layer={sample_cell.layer}")
    
    # Current grid_x * cell_size (Phase 1 was 0.05)
    wx = sample_cell.x * 0.05
    wy = sample_cell.y * 0.05
    
    gx, gy = base_router._world_to_grid(wx, wy)
    
    # Check 3x3 neighborhood to be robust to rounding/aliasing at grid boundaries
    found_occupancy = False
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            nx, ny = gx + dx, gy + dy
            if 0 <= nx < base_router.grid_size[0] and 0 <= ny < base_router.grid_size[1]:
                if base_router.occupancy[nx, ny, 0] != 0:
                    found_occupancy = True
                    break
        if found_occupancy: break
    
    if not found_occupancy:
        logger.error(f"Assertion failed at gx={gx}, gy={gy}. Neighborhood is empty.")
    
    assert found_occupancy, f"Fine net path at world ({wx}, {wy}) should be preserved in coarse grid (checked 3x3 around {gx}, {gy})"
    
    logger.info("Multi-Resolution Routing Validation SUCCESS.")

if __name__ == "__main__":
    validate_multires()
