"""PBT: ConstraintGeneration invariants."""
from hypothesis import given, settings, strategies as st

@given(net_count=st.integers(1,10), edge_count=st.integers(1,5), layer_count=st.integers(1,4))
@settings(max_examples=100, deadline=30000)
def test_channel_var_count(net_count, edge_count, layer_count):
    assert net_count * edge_count * layer_count >= 1

@given(net_count=st.integers(1,10), node_count=st.integers(1,10))
@settings(max_examples=100, deadline=30000)
def test_via_var_count(net_count, node_count):
    assert net_count * node_count >= 1

@given(var_names=st.lists(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789_', min_size=1, max_size=20), min_size=0, max_size=50, unique=True))
@settings(max_examples=100, deadline=30000)
def test_no_duplicate_names(var_names):
    assert len(var_names) == len(set(var_names))
