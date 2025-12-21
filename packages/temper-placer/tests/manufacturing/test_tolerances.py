import pytest
from temper_placer.manufacturing.tolerances import (
    ToleranceTable, 
    ToleranceAnalyzer, 
    CopperWeight, 
    LayerType,
    FeatureTolerance
)

def test_tolerance_table_defaults():
    table = ToleranceTable()
    assert table.etch_tolerance[CopperWeight.ONE_OZ] == 0.05
    assert table.registration[LayerType.OUTER] == 0.1

def test_analyze_clearance():
    analyzer = ToleranceAnalyzer()
    # 1oz copper, outer layer
    # etch = 0.05, reg = 0.1
    # total tolerance = 2*0.05 + 0.1 = 0.2
    tol = analyzer.analyze_clearance(0.5, CopperWeight.ONE_OZ, LayerType.OUTER)
    
    assert tol.nominal_value == 0.5
    assert tol.worst_case_min == pytest.approx(0.3)
    assert tol.tolerance_minus == pytest.approx(0.2)

def test_analyze_trace_width():
    analyzer = ToleranceAnalyzer()
    # 2oz copper
    # etch = 0.075
    tol = analyzer.analyze_trace(1.0, CopperWeight.TWO_OZ)
    
    assert tol.nominal_value == 1.0
    assert tol.worst_case_min == pytest.approx(0.925)
    assert tol.worst_case_max == pytest.approx(1.075)

def test_custom_tolerance_table():
    custom_etch = {CopperWeight.ONE_OZ: 0.01}
    table = ToleranceTable(etch_tolerance=custom_etch)
    analyzer = ToleranceAnalyzer(table=table)
    
    # Check that custom value is used
    tol = analyzer.analyze_trace(1.0, CopperWeight.ONE_OZ)
    assert tol.worst_case_min == pytest.approx(0.99)