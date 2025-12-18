"""Utility for accessing benchmark test cases for ablation studies."""

from pathlib import Path


def get_fixture_dir() -> Path:
    """Return the absolute path to the tests/fixtures directory."""
    # Assume this file is at src/temper_placer/ablation/test_cases.py
    return Path(__file__).parent.parent.parent.parent / "tests" / "fixtures"

def list_internal_test_cases() -> list[Path]:
    """List all internal (synthetic) test cases."""
    fixture_dir = get_fixture_dir()
    return [
        fixture_dir / "minimal_board.kicad_pcb",
        fixture_dir / "medium_board.kicad_pcb",
        fixture_dir / "large_board.kicad_pcb",
    ]

def list_external_test_cases() -> list[Path]:
    """List cached external test cases (if available)."""
    external_dir = get_fixture_dir() / "external" / ".cache"
    if not external_dir.exists():
        return []

    return list(external_dir.glob("**/*.kicad_pcb"))

def get_standard_test_suite() -> list[Path]:
    """Return the recommended suite of test cases for ablation."""
    internal = list_internal_test_cases()
    # Prefer medium and large for realistic results
    suite = [p for p in internal if "minimal" not in p.name]

    # Add external if available
    external = list_external_test_cases()
    if external:
        suite.extend(external[:2]) # Take first 2 for speed

    return suite
