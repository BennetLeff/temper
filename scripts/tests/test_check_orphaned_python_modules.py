"""Regression tests for the orphaned-Python-module liveness scanner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_orphaned_python_modules import (  # noqa: E402
    RUST_PY_IMPORT,
    dead_import_subgraph_modules,
    strongly_connected_components,
)


def test_rust_import_pattern_matches_py_import() -> None:
    match = RUST_PY_IMPORT.search('py.import("temper_placer.example")')
    assert match is not None
    assert match.group(1) == "temper_placer.example"


def test_rust_import_pattern_matches_pymodule_import() -> None:
    match = RUST_PY_IMPORT.search(
        'PyModule::import(py, "temper_placer.regression.schema_validator")?'
    )
    assert match is not None
    assert match.group(1) == "temper_placer.regression.schema_validator"


def test_rust_import_pattern_matches_pymodule_import_bound() -> None:
    match = RUST_PY_IMPORT.search(
        'PyModule::import_bound(py, "temper_placer.example")?'
    )
    assert match is not None
    assert match.group(1) == "temper_placer.example"


def test_closed_cycle_and_descendants_are_dead_without_a_root() -> None:
    graph = {
        "pkg.a": {"pkg.b"},
        "pkg.b": {"pkg.a", "pkg.leaf"},
        "pkg.leaf": set(),
    }
    assert dead_import_subgraph_modules(graph, set()) == {
        "pkg.a", "pkg.b", "pkg.leaf"
    }


def test_rooted_cycle_is_reachable_and_not_orphaned() -> None:
    graph = {
        "pkg.entry": {"pkg.a"},
        "pkg.a": {"pkg.b"},
        "pkg.b": {"pkg.a"},
    }
    assert dead_import_subgraph_modules(graph, {"pkg.entry"}) == set()


def test_cycle_detection_keeps_unrelated_singletons_out() -> None:
    graph = {
        "pkg.a": {"pkg.b"},
        "pkg.b": {"pkg.a"},
        "pkg.public": set(),
    }
    components = strongly_connected_components(graph)
    assert {"pkg.a", "pkg.b"} in components
    assert dead_import_subgraph_modules(graph, set()) == {"pkg.a", "pkg.b"}
    assert "pkg.public" not in dead_import_subgraph_modules(graph, set())
