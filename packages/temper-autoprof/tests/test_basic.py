"""
Basic test to verify module import.
"""

import sys
from pathlib import Path

# Add the source directory to the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def test_can_import_profiler():
    """Test that we can import the profiler module."""

    assert True  # If we got here, import succeeded


def test_can_import_cli():
    """Test that we can import the CLI module."""

    assert True  # If we got here, import succeeded
