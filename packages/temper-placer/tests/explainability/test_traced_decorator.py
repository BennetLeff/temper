import pytest

from temper_placer.explainability.traced_loss import TracedLossContext, traced


def test_traced_standalone():
    """Verify @traced returns (result, trace) tuple standalone."""
    @traced(subject="Q1", because="Test reason")
    def my_func(x):
        return x * 2

    val, trace = my_func(10)
    assert val == 20
    assert len(trace) == 1
    assert trace.entries[0].subject == "Q1"
    assert trace.entries[0].because == "Test reason"
    assert trace.entries[0].value == 20.0

def test_traced_context():
    """Verify @traced adds to active context and returns only result."""
    @traced(subject="Q1", because="Context reason")
    def my_func(x):
        return x + 5

    with TracedLossContext() as ctx:
        val = my_func(10)
        assert val == 15

    total_val, trace = ctx.result()
    assert total_val == 15
    assert len(trace) == 1
    assert trace.entries[0].subject == "Q1"
    assert "Context reason" in trace.why("Q1")

def test_traced_threshold():
    """Verify @traced respects threshold."""
    @traced(subject="Q1", because="Small value", threshold=1.0)
    def my_func(x):
        return x

    val, trace = my_func(0.5)
    assert val == 0.5
    assert len(trace) == 0  # Below threshold

def test_traced_nested():
    """Verify decorated calls nested within other decorated calls."""
    @traced(subject="Inner", because="Inner reason")
    def inner(x):
        return x

    @traced(subject="Outer", because="Outer reason")
    def outer(x):
        return inner(x)

    # Standalone nested: outer returns (inner_result, outer_trace)
    # where outer_trace only contains Outer (because inner returned result standalone as tuple)
    # This is a slightly tricky case for nested standalone.
    # Usually we use decorators either with context OR on leaf nodes.

    # Context nested (the preferred way for hierarchies)
    with TracedLossContext() as ctx:
        val = outer(10)
        assert val == 10

    _, trace = ctx.result()
    assert len(trace) == 2
    assert "Outer reason" in trace.why("Outer")
    assert "Inner reason" in trace.why("Inner")

def test_traced_defaults():
    """Verify @traced uses function name as default subject."""
    @traced
    def mystery_function(x):
        return x

    val, trace = mystery_function(42)
    assert trace.entries[0].subject == "mystery_function"
    assert "Result of mystery_function" in trace.entries[0].because

if __name__ == "__main__":
    pytest.main([__file__])
