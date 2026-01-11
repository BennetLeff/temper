"""
Tests for Router V6 Stage 3.7: Build SAT Model

Part of temper-5eh3
"""

import pytest

from temper_placer.router_v6.sat_model import (
    SATClause,
    SATModel,
    SATVariable,
    add_capacity_to_sat,
    add_connectivity_to_sat,
    build_sat_model,
)


def test_build_sat_model_empty():
    """Test building empty SAT model."""
    model = build_sat_model()

    assert model.variable_count == 0
    assert model.clause_count == 0


def test_add_variable():
    """Test adding variables to SAT model."""
    model = build_sat_model()
    
    var = model.add_variable("test_var", "Test variable")

    assert model.variable_count == 1
    assert var.name == "test_var"
    assert var.description == "Test variable"


def test_add_clause():
    """Test adding clauses to SAT model."""
    model = build_sat_model()
    
    var1 = model.add_variable("v1", "Variable 1")
    var2 = model.add_variable("v2", "Variable 2")
    
    model.add_clause([(var1, True), (var2, False)], "Test clause")

    assert model.clause_count == 1
    clause = model.clauses[0]
    assert len(clause.literals) == 2


def test_add_connectivity_to_sat():
    """Test adding connectivity constraints."""
    model = build_sat_model()
    
    add_connectivity_to_sat(model, "NET1", "A", "B")

    assert model.variable_count == 1
    assert model.clause_count == 1
    
    # Variable should represent the path
    var = model.variables[0]
    assert "route_NET1" in var.name


def test_add_capacity_to_sat():
    """Test adding capacity constraints."""
    model = build_sat_model()
    
    add_capacity_to_sat(model, "CH1", 2, ["NET1", "NET2", "NET3"])

    # Should create variables for each net
    assert model.variable_count == 3
    
    # Should add capacity constraint
    assert model.clause_count > 0


def test_sat_variable_str():
    """Test SATVariable string representation."""
    var = SATVariable("test", "Test variable")
    
    assert str(var) == "test"


def test_sat_clause_str():
    """Test SATClause string representation."""
    var1 = SATVariable("v1", "Variable 1")
    var2 = SATVariable("v2", "Variable 2")
    
    clause = SATClause([(var1, True), (var2, False)], "Test")
    
    # Should show positive and negated literals
    clause_str = str(clause)
    assert "v1" in clause_str
    assert "¬v2" in clause_str or "~v2" in clause_str


def test_sat_model_dataclass():
    """Test SATModel dataclass properties."""
    model = SATModel(variables=[], clauses=[])
    
    var1 = model.add_variable("v1", "Variable 1")
    var2 = model.add_variable("v2", "Variable 2")
    
    model.add_clause([(var1, True)], "Clause 1")
    model.add_clause([(var2, False)], "Clause 2")

    assert model.variable_count == 2
    assert model.clause_count == 2
