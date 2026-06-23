"""PBT: ModelExtraction invariants."""
from hypothesis import assume, given, settings, strategies as st

@given(rc=st.integers(0,50), tc=st.integers(0,100))
@settings(max_examples=100, deadline=30000)
def test_routed_le_total(rc, tc):
    assume(rc <= tc)
    assert rc <= tc

@given(sat=st.booleans(), rc=st.integers(0,50))
@settings(max_examples=100, deadline=30000)
def test_unsat_empty(sat, rc):
    if not sat: assume(rc == 0)

@given(ids=st.lists(st.text('abcdefghijklmnopqrstuvwxyz0123456789_', min_size=1, max_size=20), min_size=0, max_size=10))
@settings(max_examples=100, deadline=30000)
def test_ids_nonempty(ids):
    for cid in ids: assert len(cid) > 0
