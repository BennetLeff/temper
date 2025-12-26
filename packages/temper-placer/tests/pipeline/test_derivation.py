import pytest
import math
from temper_placer.core.specification import PcbSpecification, EMISpec, ThermalSpec
from temper_placer.pipeline.derivation import derive_constraints_from_spec
from unittest.mock import MagicMock

def test_derive_constraints_from_spec():
    spec = PcbSpecification(
        emi=EMISpec(max_loop_area_mm2={"gate": 100.0}),
        thermal=ThermalSpec(power_dissipation={"Q1": 10.0})
    )
    
    mock_netlist = MagicMock()
    derived = derive_constraints_from_spec(spec, mock_netlist)
    
    # 100mm2 area -> 10mm side -> 8mm max dist
    assert derived["gate_max_dist"] == pytest.approx(8.0)
    
    # 10W thermal -> 20mm min clearance
    assert derived["Q1_min_clearance"] == pytest.approx(20.0)
