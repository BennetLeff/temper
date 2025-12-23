"""
Pytest fixtures and helpers for routing tests.

Provides common test utilities including grid visualization on failures.
"""

import pytest
from typing import Optional, List, Tuple
from temper_placer.routing.maze_router import GridCell, MazeRouter
from .grid_viz import print_grid_on_failure, render_grid


@pytest.fixture
def assert_path_found():
    """
    Fixture that provides a helper to assert path was found with visualization on failure.
    
    Usage:
        def test_something(assert_path_found):
            router = MazeRouter(grid_size=(10, 10))
            path = router.find_path((0, 0), (9, 9))
            assert_path_found(router, path, (0, 0), (9, 9))
    """
    def _assert(router: MazeRouter, path: Optional[List[GridCell]], 
                start: Tuple[int, int], end: Tuple[int, int]):
        if path is None:
            print_grid_on_failure(router, path, start, end, expected_success=True)
        assert path is not None, f"Expected path from {start} to {end}, got None"
    
    return _assert


@pytest.fixture
def assert_no_path():
    """
    Fixture that provides a helper to assert no path exists with visualization on failure.
    
    Usage:
        def test_blocked(assert_no_path):
            router = MazeRouter(grid_size=(10, 10))
            # ... block cells ...
            path = router.find_path((0, 0), (9, 9))
            assert_no_path(router, path, (0, 0), (9, 9))
    """
    def _assert(router: MazeRouter, path: Optional[List[GridCell]], 
                start: Tuple[int, int], end: Tuple[int, int]):
        if path is not None:
            print_grid_on_failure(router, path, start, end, expected_success=False)
        assert path is None, f"Expected no path from {start} to {end}, but found one with {len(path)} cells"
    
    return _assert


@pytest.fixture
def visualize_on_failure(request):
    """
    Fixture that automatically visualizes grid state on test failure.
    
    Usage:
        def test_something(visualize_on_failure):
            router = MazeRouter(grid_size=(10, 10))
            visualize_on_failure.router = router
            visualize_on_failure.start = (0, 0)
            visualize_on_failure.end = (9, 9)
            
            path = router.find_path((0, 0), (9, 9))
            assert path is not None  # Will show grid if this fails
    """
    class VisualizerHelper:
        def __init__(self):
            self.router = None
            self.start = None
            self.end = None
            self.path = None
    
    helper = VisualizerHelper()
    
    yield helper
    
    # After test runs, check if it failed
    if request.node.rep_call.failed if hasattr(request.node, 'rep_call') else False:
        if helper.router is not None:
            print("\n" + "=" * 60)
            print("TEST FAILURE - Grid Visualization:")
            print("=" * 60)
            if helper.start and helper.end:
                print(render_grid(helper.router, helper.path, helper.start, helper.end))
            else:
                print(render_grid(helper.router, helper.path))
            print("=" * 60)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook to capture test results for visualize_on_failure fixture.
    """
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
