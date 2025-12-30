
import pytest
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist

@pytest.fixture(scope="session")
def temper_baseline_pcb_path():
    # Use pre_routed_v6.kicad_pcb from project root
    path = Path("../../pre_routed_v6.kicad_pcb")
    if not path.exists():
        # Try relative to package root
        path = Path("pre_routed_v6.kicad_pcb")
    if not path.exists():
        # Try relative to current dir
        path = Path("../../../pre_routed_v6.kicad_pcb")
    return path

@pytest.fixture(scope="session")
def temper_baseline_data(temper_baseline_pcb_path):
    if not temper_baseline_pcb_path.exists():
        pytest.skip(f"Baseline PCB not found at {temper_baseline_pcb_path}")
    return parse_kicad_pcb(temper_baseline_pcb_path)

@pytest.fixture
def temper_netlist(temper_baseline_data):
    return temper_baseline_data.netlist

@pytest.fixture
def temper_board(temper_baseline_data):
    return temper_baseline_data.board

@pytest.fixture
def temper_positions(temper_baseline_data):
    import jax.numpy as jnp
    positions_list = [comp.initial_position for comp in temper_baseline_data.netlist.components]
    return jnp.array(positions_list)
