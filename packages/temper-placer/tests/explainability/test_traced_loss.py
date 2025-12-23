"""Tests for traced loss computation utilities."""

import pytest
import jax.numpy as jnp
from temper_placer.explainability.trace import Trace
from temper_placer.explainability.traced_loss import (
    traced_loss,
    combine_traced_losses,
    constraint_to_traced_loss,
    TracedLossContext,
)


class MockConstraint:
    """Mock constraint for testing."""
    def __init__(self, a, because):
        self.a = a
        self.because = because


class TestTracedLoss:
    """Tests for traced_loss wrapper."""
    
    def test_traced_loss_returns_tuple(self):
        """GIVEN a loss function
        WHEN wrapping with traced_loss
        THEN returns (loss, trace) tuple"""
        def simple_loss(x):
            return x ** 2
        
        traced_fn = traced_loss(simple_loss, "Q1", "Test reason")
        loss, trace = traced_fn(5.0)
        
        assert loss == 25.0
        assert isinstance(trace, Trace)
    
    def test_traced_loss_creates_trace_entry(self):
        """GIVEN a loss function with significant loss
        WHEN calling traced function
        THEN creates trace entry with reason"""
        def simple_loss(x):
            return x ** 2
        
        traced_fn = traced_loss(simple_loss, "Q1", "Minimize distance")
        loss, trace = traced_fn(5.0)
        
        assert len(trace) == 1
        assert trace.entries[0].subject == "Q1"
        assert trace.entries[0].because == "Minimize distance"
    
    def test_traced_loss_skips_negligible(self):
        """GIVEN a loss function with negligible loss
        WHEN calling traced function
        THEN does not create trace entry"""
        def zero_loss(x):
            return 0.0
        
        traced_fn = traced_loss(zero_loss, "Q1", "Reason")
        loss, trace = traced_fn(5.0)
        
        assert loss == 0.0
        assert len(trace) == 0


class TestCombineTracedLosses:
    """Tests for combining traced losses."""
    
    def test_combine_empty_list(self):
        """GIVEN empty list of traced results
        WHEN combining
        THEN returns zero loss and empty trace"""
        total_loss, trace = combine_traced_losses([])
        
        assert total_loss == 0.0
        assert len(trace) == 0
    
    def test_combine_single_result(self):
        """GIVEN single traced result
        WHEN combining
        THEN returns same result"""
        trace1 = Trace.empty().add("Q1", 10.0, "Reason 1")
        results = [(5.0, trace1)]
        
        total_loss, combined_trace = combine_traced_losses(results)
        
        assert total_loss == 5.0
        assert len(combined_trace) == 1
    
    def test_combine_multiple_results(self):
        """GIVEN multiple traced results
        WHEN combining
        THEN sums losses and combines traces"""
        trace1 = Trace.empty().add("Q1", 10.0, "Reason 1")
        trace2 = Trace.empty().add("Q2", 20.0, "Reason 2")
        trace3 = Trace.empty().add("Q1", 15.0, "Reason 3")
        
        results = [
            (5.0, trace1),
            (3.0, trace2),
            (2.0, trace3),
        ]
        
        total_loss, combined_trace = combine_traced_losses(results)
        
        assert total_loss == 10.0
        assert len(combined_trace) == 3
        # Verify all entries present
        assert combined_trace.entries[0].subject == "Q1"
        assert combined_trace.entries[1].subject == "Q2"
        assert combined_trace.entries[2].subject == "Q1"
    
    def test_combine_preserves_order(self):
        """GIVEN traced results in specific order
        WHEN combining
        THEN preserves entry order"""
        trace1 = Trace.empty().add("Q1", 1, "R1")
        trace2 = Trace.empty().add("Q2", 2, "R2")
        trace3 = Trace.empty().add("Q3", 3, "R3")
        
        results = [(1.0, trace1), (2.0, trace2), (3.0, trace3)]
        
        _, combined_trace = combine_traced_losses(results)
        
        assert combined_trace.entries[0].because == "R1"
        assert combined_trace.entries[1].because == "R2"
        assert combined_trace.entries[2].because == "R3"


class TestConstraintToTracedLoss:
    """Tests for converting constraints to traced losses."""
    
    def test_constraint_with_a_field(self):
        """GIVEN constraint with 'a' field
        WHEN converting to traced loss
        THEN uses 'a' as subject"""
        constraint = MockConstraint(a="Q1", because="Test reason")
        
        def loss_fn(c, x):
            return x ** 2
        
        traced_fn = constraint_to_traced_loss(constraint, loss_fn)
        loss, trace = traced_fn(5.0)
        
        assert loss == 25.0
        assert len(trace) == 1
        assert trace.entries[0].subject == "Q1"
        assert trace.entries[0].because == "Test reason"
    
    def test_constraint_propagates_because(self):
        """GIVEN constraint with 'because' field
        WHEN converting to traced loss
        THEN propagates 'because' to trace"""
        constraint = MockConstraint(
            a="Q1",
            because="Minimize commutation loop for half-bridge"
        )
        
        def loss_fn(c, x):
            return 10.0
        
        traced_fn = constraint_to_traced_loss(constraint, loss_fn)
        _, trace = traced_fn(None)
        
        assert "Minimize commutation loop" in trace.entries[0].because


class TestTracedLossContext:
    """Tests for TracedLossContext manager."""
    
    def test_context_manager(self):
        """GIVEN TracedLossContext
        WHEN using as context manager
        THEN can add losses and get result"""
        with TracedLossContext() as ctx:
            trace1 = Trace.empty().add("Q1", 10, "R1")
            trace2 = Trace.empty().add("Q2", 20, "R2")
            
            ctx.add(5.0, trace1)
            ctx.add(3.0, trace2)
        
        total_loss, combined_trace = ctx.result()
        
        assert total_loss == 8.0
        assert len(combined_trace) == 2
    
    def test_context_empty(self):
        """GIVEN empty context
        WHEN getting result
        THEN returns zero loss and empty trace"""
        with TracedLossContext() as ctx:
            pass
        
        total_loss, trace = ctx.result()
        
        assert total_loss == 0.0
        assert len(trace) == 0
    
    def test_context_accumulates(self):
        """GIVEN context with multiple additions
        WHEN getting result
        THEN accumulates all losses and traces"""
        with TracedLossContext() as ctx:
            for i in range(5):
                trace = Trace.empty().add(f"Q{i}", i, f"Reason {i}")
                ctx.add(float(i), trace)
        
        total_loss, combined_trace = ctx.result()
        
        assert total_loss == 10.0  # 0 + 1 + 2 + 3 + 4
        assert len(combined_trace) == 5


class TestIntegrationExample:
    """Integration test showing full workflow."""
    
    def test_full_traced_optimization_step(self):
        """GIVEN multiple constraints
        WHEN computing traced losses
        THEN can combine and query results"""
        # Create mock constraints
        constraints = [
            MockConstraint("Q1", "Minimize commutation loop"),
            MockConstraint("Q2", "Thermal edge constraint"),
            MockConstraint("Q1", "HV isolation requirement"),
        ]
        
        # Define loss functions
        def adjacency_loss(c, positions):
            return 5.0  # Mock loss
        
        def thermal_loss(c, positions):
            return 3.0  # Mock loss
        
        def isolation_loss(c, positions):
            return 2.0  # Mock loss
        
        loss_fns = [adjacency_loss, thermal_loss, isolation_loss]
        
        # Compute traced losses
        with TracedLossContext() as ctx:
            for constraint, loss_fn in zip(constraints, loss_fns):
                traced_fn = constraint_to_traced_loss(constraint, loss_fn)
                loss, trace = traced_fn(None)  # positions=None for mock
                ctx.add(loss, trace)
        
        total_loss, combined_trace = ctx.result()
        
        # Verify results
        assert total_loss == 10.0  # 5 + 3 + 2
        assert len(combined_trace) == 3
        
        # Query trace for Q1
        q1_explanation = combined_trace.why("Q1")
        assert "Q1" in q1_explanation
        assert "Minimize commutation loop" in q1_explanation
        assert "HV isolation requirement" in q1_explanation
