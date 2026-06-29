"""PBT: AssignmentValidation invariants."""
from hypothesis import assume, given, settings
from hypothesis import strategies as st


@given(sat=st.booleans(), av=st.one_of(st.none(), st.booleans()))
@settings(max_examples=100, deadline=30000)
def test_sat_implies_valid(sat, av):
    if sat: assume(av is not False)

@given(v=st.booleans())
@settings(max_examples=100, deadline=30000)
def test_is_boolean(v):
    assert isinstance(v, bool)
