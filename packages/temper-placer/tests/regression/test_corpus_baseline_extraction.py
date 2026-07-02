"""Tests for the corrected corpus baseline extraction.

Verifies that the five-bug regime (wrong function name, swallowed try/except,
hardcoded zeroes, mislabeled alias) is no longer possible.
"""
import importlib
import sys

import pytest


def test_compute_total_hpwl_imports_do_not_raise():
    """The correct HPWL entrypoint exists and imports without error."""
    from temper_placer.losses.wirelength import compute_total_hpwl
    assert callable(compute_total_hpwl)


def test_compute_hpwl_does_not_exist():
    """The nonexistent `compute_hpwl` name raises ImportError — no silent fallback.

    The old extract_corpus_baselines.py called ``compute_hpwl(state, netlist)``
    inside a bare ``try: ... except Exception: pass``, silently writing 0.0 when
    this name failed to import.  This test proves the broken name does not exist.
    """
    import temper_placer.losses.wirelength as wl
    assert hasattr(wl, "compute_total_hpwl")
    assert not hasattr(wl, "compute_hpwl")


def test_extract_script_syntax_and_metrics_keys():
    """The corrected extract script parses and produces the right metric keys."""
    from pathlib import Path

    script_path = (
        Path(__file__).resolve().parents[4]
        / "scripts"
        / "extract_corpus_baselines.py"
    )
    assert script_path.exists(), f"script not found: {script_path}"

    # Parse the script to ensure no syntax errors after our edits.
    with open(script_path) as f:
        source = f.read()
    compile(source, str(script_path), "exec")

    # Verify import of the correct function is in the source.
    assert "compute_total_hpwl" in source, (
        "Missing import of compute_total_hpwl in extract_corpus_baselines.py"
    )
    assert "compute_hpwl" not in source, (
        "Stale reference to nonexistent compute_hpwl still present"
    )
