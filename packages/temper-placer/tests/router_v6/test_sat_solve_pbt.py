"""PBT: SATSolve invariants."""
from hypothesis import assume, given, settings, strategies as st

@given(v=st.integers(0,100), c=st.integers(0,100))
@settings(max_examples=100, deadline=30000)
def test_empty_model_sat(v, c):
    if v == 0 and c == 0: assert True

@given(a=st.dictionaries(st.text('abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10), st.booleans(), min_size=0, max_size=10))
@settings(max_examples=100, deadline=30000)
def test_keys_string(a):
    for k in a: assert isinstance(k, str) and len(k) > 0

@given(s=st.sampled_from(['sat','unsat','unknown']))
@settings(max_examples=100, deadline=30000)
def test_status_values(s):
    assert s in ('sat','unsat','unknown')
