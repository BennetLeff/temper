"""PBT: VariableMapping invariants."""
from hypothesis import assume, given, settings
from hypothesis import strategies as st


@given(c=st.integers(0,50), s=st.integers(0,50))
@settings(max_examples=100, deadline=30000)
def test_sat_var_count(c, s):
    assume(s >= c)
    assert s >= c

@given(lits=st.lists(st.tuples(st.integers(0,10), st.booleans()), min_size=1, max_size=20), mv=st.integers(0,10))
@settings(max_examples=100, deadline=30000)
def test_clause_vars(lits, mv):
    for vi, _ in lits:
        assume(vi <= mv)

@given(names=st.lists(st.text('abcdefghijklmnopqrstuvwxyz_', min_size=1, max_size=16), min_size=0, max_size=30))
@settings(max_examples=100, deadline=30000)
def test_no_empty_names(names):
    for n in names:
        assert len(n) > 0
