"""Tests for immutable Trace class.

Tests verify:
1. Immutability - operations return new traces
2. Monoid laws - identity and associativity
3. Composition - combining traces
4. Filtering - for_subject()
5. Natural language generation - why()
"""

import pytest
from temper_placer.explainability.trace import Entry, Trace


class TestEntry:
    """Tests for Entry dataclass."""
    
    def test_entry_creation(self):
        """GIVEN subject, value, because
        WHEN creating Entry
        THEN all fields are set correctly"""
        entry = Entry("Q1", (45.2, 12.3), "Minimize commutation loop")
        
        assert entry.subject == "Q1"
        assert entry.value == (45.2, 12.3)
        assert entry.because == "Minimize commutation loop"
    
    def test_entry_immutable(self):
        """GIVEN an Entry
        WHEN trying to modify it
        THEN raises AttributeError (frozen)"""
        entry = Entry("Q1", (10, 20), "Reason")
        
        with pytest.raises(AttributeError):
            entry.subject = "Q2"  # type: ignore


class TestTraceImmutability:
    """Tests for trace immutability."""
    
    def test_trace_frozen(self):
        """GIVEN a Trace
        WHEN trying to modify entries
        THEN raises AttributeError (frozen)"""
        trace = Trace.empty()
        
        with pytest.raises(AttributeError):
            trace.entries = ()  # type: ignore
    
    def test_add_returns_new_trace(self):
        """GIVEN a trace
        WHEN calling add()
        THEN returns NEW trace, original unchanged"""
        trace1 = Trace.empty()
        trace2 = trace1.add("Q1", (10, 20), "Reason")
        
        # Original unchanged
        assert len(trace1) == 0
        # New trace has entry
        assert len(trace2) == 1
        # Different objects
        assert trace1 is not trace2
    
    def test_composition_returns_new_trace(self):
        """GIVEN two traces
        WHEN composing with +
        THEN returns NEW trace, originals unchanged"""
        trace1 = Trace.empty().add("Q1", (10, 20), "R1")
        trace2 = Trace.empty().add("Q2", (30, 40), "R2")
        
        combined = trace1 + trace2
        
        # Originals unchanged
        assert len(trace1) == 1
        assert len(trace2) == 1
        # Combined has both
        assert len(combined) == 2
        # Different objects
        assert combined is not trace1
        assert combined is not trace2


class TestTraceMonoidLaws:
    """Tests for monoid properties."""
    
    def test_empty_is_identity_left(self):
        """GIVEN a trace x
        WHEN composing empty() + x
        THEN result equals x (left identity)"""
        x = Trace.empty().add("Q1", (10, 20), "Reason")
        
        result = Trace.empty() + x
        
        assert result.entries == x.entries
    
    def test_empty_is_identity_right(self):
        """GIVEN a trace x
        WHEN composing x + empty()
        THEN result equals x (right identity)"""
        x = Trace.empty().add("Q1", (10, 20), "Reason")
        
        result = x + Trace.empty()
        
        assert result.entries == x.entries
    
    def test_associativity(self):
        """GIVEN traces a, b, c
        WHEN composing (a + b) + c vs a + (b + c)
        THEN results are equal (associativity)"""
        a = Trace.empty().add("Q1", (10, 20), "R1")
        b = Trace.empty().add("Q2", (30, 40), "R2")
        c = Trace.empty().add("Q3", (50, 60), "R3")
        
        left = (a + b) + c
        right = a + (b + c)
        
        assert left.entries == right.entries


class TestTraceComposition:
    """Tests for trace composition."""
    
    def test_add_single_entry(self):
        """GIVEN empty trace
        WHEN adding single entry
        THEN trace has one entry"""
        trace = Trace.empty().add("Q1", (45.2, 12.3), "Proximity constraint")
        
        assert len(trace) == 1
        assert trace.entries[0].subject == "Q1"
        assert trace.entries[0].value == (45.2, 12.3)
        assert trace.entries[0].because == "Proximity constraint"
    
    def test_add_multiple_entries(self):
        """GIVEN empty trace
        WHEN adding multiple entries
        THEN trace has all entries in order"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "R1")
        trace = trace.add("Q2", (30, 40), "R2")
        trace = trace.add("Q1", (15, 25), "R3")
        
        assert len(trace) == 3
        assert trace.entries[0].subject == "Q1"
        assert trace.entries[1].subject == "Q2"
        assert trace.entries[2].subject == "Q1"
    
    def test_compose_two_traces(self):
        """GIVEN two traces
        WHEN composing with +
        THEN combined trace has all entries"""
        trace1 = Trace.empty()
        trace1 = trace1.add("Q1", (10, 20), "R1")
        trace1 = trace1.add("Q2", (30, 40), "R2")
        
        trace2 = Trace.empty()
        trace2 = trace2.add("Q3", (50, 60), "R3")
        
        combined = trace1 + trace2
        
        assert len(combined) == 3
        assert combined.entries[0].subject == "Q1"
        assert combined.entries[1].subject == "Q2"
        assert combined.entries[2].subject == "Q3"
    
    def test_compose_multiple_traces(self):
        """GIVEN multiple traces
        WHEN composing with + operator
        THEN can chain compositions"""
        t1 = Trace.empty().add("Q1", (10, 20), "R1")
        t2 = Trace.empty().add("Q2", (30, 40), "R2")
        t3 = Trace.empty().add("Q3", (50, 60), "R3")
        
        combined = t1 + t2 + t3
        
        assert len(combined) == 3


class TestTraceFiltering:
    """Tests for trace filtering."""
    
    def test_for_subject_single_match(self):
        """GIVEN trace with multiple subjects
        WHEN filtering for subject with one entry
        THEN returns trace with only that entry"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "R1")
        trace = trace.add("Q2", (30, 40), "R2")
        trace = trace.add("Q3", (50, 60), "R3")
        
        q2_trace = trace.for_subject("Q2")
        
        assert len(q2_trace) == 1
        assert q2_trace.entries[0].subject == "Q2"
    
    def test_for_subject_multiple_matches(self):
        """GIVEN trace with multiple entries for same subject
        WHEN filtering for that subject
        THEN returns trace with all matching entries"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "R1")
        trace = trace.add("Q2", (30, 40), "R2")
        trace = trace.add("Q1", (15, 25), "R3")
        trace = trace.add("Q1", (12, 22), "R4")
        
        q1_trace = trace.for_subject("Q1")
        
        assert len(q1_trace) == 3
        assert all(e.subject == "Q1" for e in q1_trace.entries)
    
    def test_for_subject_no_matches(self):
        """GIVEN trace
        WHEN filtering for non-existent subject
        THEN returns empty trace"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "R1")
        
        q2_trace = trace.for_subject("Q2")
        
        assert len(q2_trace) == 0
    
    def test_for_subject_preserves_order(self):
        """GIVEN trace with multiple entries
        WHEN filtering
        THEN preserves original order"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "R1")
        trace = trace.add("Q1", (15, 25), "R2")
        trace = trace.add("Q2", (30, 40), "R3")
        trace = trace.add("Q1", (12, 22), "R4")
        
        q1_trace = trace.for_subject("Q1")
        
        assert q1_trace.entries[0].because == "R1"
        assert q1_trace.entries[1].because == "R2"
        assert q1_trace.entries[2].because == "R4"


class TestNaturalLanguageGeneration:
    """Tests for why() natural language generation."""
    
    def test_why_single_decision(self):
        """GIVEN trace with single decision
        WHEN calling why()
        THEN generates explanation with value and reason"""
        trace = Trace.empty().add("Q1", (45.2, 12.3), "Minimize commutation loop")
        
        explanation = trace.why("Q1")
        
        assert "Q1" in explanation
        assert "45.2" in explanation
        assert "12.3" in explanation
        assert "Minimize commutation loop" in explanation
    
    def test_why_multiple_decisions(self):
        """GIVEN trace with multiple decisions for same subject
        WHEN calling why()
        THEN shows final value and all reasons"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "Initial placement")
        trace = trace.add("Q1", (45.2, 12.3), "Minimize commutation loop")
        trace = trace.add("Q1", (43.8, 11.9), "Thermal edge constraint")
        
        explanation = trace.why("Q1")
        
        # Final value
        assert "43.8" in explanation
        assert "11.9" in explanation
        # All reasons
        assert "Initial placement" in explanation
        assert "Minimize commutation loop" in explanation
        assert "Thermal edge constraint" in explanation
    
    def test_why_no_decisions(self):
        """GIVEN trace with no decisions for subject
        WHEN calling why()
        THEN returns 'No decisions' message"""
        trace = Trace.empty().add("Q1", (10, 20), "Reason")
        
        explanation = trace.why("Q2")
        
        assert "No decisions" in explanation
        assert "Q2" in explanation
    
    def test_why_max_reasons(self):
        """GIVEN trace with many decisions
        WHEN calling why() with max_reasons
        THEN limits number of reasons shown"""
        trace = Trace.empty()
        for i in range(10):
            trace = trace.add("Q1", (i, i), f"Reason {i}")
        
        explanation = trace.why("Q1", max_reasons=3)
        
        # Should show first 3 reasons
        assert "Reason 0" in explanation
        assert "Reason 1" in explanation
        assert "Reason 2" in explanation
        # Should indicate more exist
        assert "7 more" in explanation
    
    def test_why_non_tuple_value(self):
        """GIVEN trace with non-tuple value
        WHEN calling why()
        THEN formats value as string"""
        trace = Trace.empty().add("VCC", ["L1", "L4"], "Power net on signal layers")
        
        explanation = trace.why("VCC")
        
        assert "VCC" in explanation
        assert "Power net on signal layers" in explanation


class TestTraceUtilities:
    """Tests for utility methods."""
    
    def test_len_empty(self):
        """GIVEN empty trace
        WHEN calling len()
        THEN returns 0"""
        trace = Trace.empty()
        assert len(trace) == 0
    
    def test_len_with_entries(self):
        """GIVEN trace with entries
        WHEN calling len()
        THEN returns entry count"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "R1")
        trace = trace.add("Q2", (30, 40), "R2")
        
        assert len(trace) == 2
    
    def test_bool_empty(self):
        """GIVEN empty trace
        WHEN using in boolean context
        THEN evaluates to False"""
        trace = Trace.empty()
        assert not trace
    
    def test_bool_with_entries(self):
        """GIVEN trace with entries
        WHEN using in boolean context
        THEN evaluates to True"""
        trace = Trace.empty().add("Q1", (10, 20), "R1")
        assert trace
    
    def test_repr(self):
        """GIVEN trace
        WHEN calling repr()
        THEN shows entry count"""
        trace = Trace.empty()
        trace = trace.add("Q1", (10, 20), "R1")
        trace = trace.add("Q2", (30, 40), "R2")
        
        repr_str = repr(trace)
        
        assert "2 entries" in repr_str
