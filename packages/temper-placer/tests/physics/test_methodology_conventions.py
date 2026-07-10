"""
Light drift-checks for the physics verification methodology (U10).
Scope-guardian flagged over-abstraction — do NOT build a plugin/registry or
assert a multi-battery framework.  There is one consumer (thermal) today.

(a) The battery test files from U1–U9 exist on disk and are importable /
    collectable by pytest (not silently skipped).
(b) The methodology doc exists and its worked-example file references resolve
    to real files (no drift).

@req(2026-07-09-001-feat-physics-verification-rigor-plan, R1): four-layer methodology
@req(2026-07-09-001-feat-physics-verification-rigor-plan, R22): bug-triage rule
@req(2026-07-09-001-feat-physics-verification-rigor-plan, R24): CP-SAT Chebyshev discipline
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# (a) Battery files must exist and be importable (not silently skipped)
# ---------------------------------------------------------------------------

_BATTERY_FILES: list[str] = [
    # Soundness fixes (U1–U3)
    "tests/physics/test_thermal_fdm_matrix_class.py",
    "tests/physics/test_operating_point_monotonicity.py",
    "tests/validation/test_thermal_scorer_independence.py",
    # Solver invariants (U4)
    "tests/physics/test_thermal_fdm_invariants_pbt.py",
    # Refinement ladder (U5)
    "tests/physics/test_thermal_fdm_refinement.py",
    # A* Dijkstra oracle (U6)
    "tests/router_v6/test_astar_dijkstra_oracle_pbt.py",
    # Loop termination (U7)
    "tests/placer/cp_sat/test_loop_termination_pbt.py",
    # Verdict properties (U8)
    "tests/validation/test_verdict_properties_pbt.py",
    # Fail-closed + prereg (U9)
    "tests/fields/test_fieldresult_invariants_pbt.py",
    "tests/validation/prereg/test_prereg_fuzz_pbt.py",
]

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
_REPO_ROOT = _PROJECT_ROOT.parents[1]


def _collectable_path(rel: str) -> pathlib.Path:
    return _PROJECT_ROOT / rel


@pytest.mark.parametrize("rel_path", _BATTERY_FILES)
def test_battery_file_exists(rel_path: str) -> None:
    """Every U1–U9 battery test file exists on disk."""
    p = _collectable_path(rel_path)
    assert p.is_file(), f"Battery file missing: {p}"


@pytest.mark.parametrize("rel_path", _BATTERY_FILES)
def test_battery_file_importable(rel_path: str) -> None:
    """Every U1–U9 battery test file is syntactically valid Python
    (not silently skipped due to SyntaxError on collection)."""
    p = _collectable_path(rel_path)
    source = p.read_text(encoding="utf-8")
    try:
        ast.parse(source)
    except SyntaxError as exc:
        pytest.fail(f"Battery file has syntax error: {p} — {exc}")


# ---------------------------------------------------------------------------
# (b) Methodology doc exists and file references resolve
# ---------------------------------------------------------------------------

_METHODOLOGY_DOC = _REPO_ROOT / "docs" / "physics-verification-methodology.md"

# Files referenced in the "Worked example" table of the methodology doc,
# relative to repo root.
_REFERENCED_FILES: list[str] = [
    "packages/temper-placer/tests/physics/test_thermal_fdm_matrix_class.py",
    "packages/temper-placer/tests/physics/test_operating_point_monotonicity.py",
    "packages/temper-placer/tests/validation/test_thermal_scorer_independence.py",
    "packages/temper-placer/tests/physics/test_thermal_fdm_invariants_pbt.py",
    "packages/temper-placer/tests/physics/test_thermal_fdm_refinement.py",
    "packages/temper-placer/tests/router_v6/test_astar_dijkstra_oracle_pbt.py",
    "packages/temper-placer/tests/placer/cp_sat/test_loop_termination_pbt.py",
    "packages/temper-placer/tests/validation/test_verdict_properties_pbt.py",
    "packages/temper-placer/tests/fields/test_fieldresult_invariants_pbt.py",
    "packages/temper-placer/tests/validation/prereg/test_prereg_fuzz_pbt.py",
]


def test_methodology_doc_exists() -> None:
    """The methodology document exists on disk."""
    assert _METHODOLOGY_DOC.is_file(), (
        f"Methodology doc missing: {_METHODOLOGY_DOC}"
    )


def test_methodology_doc_has_no_drift() -> None:
    """Every battery-file path referenced in the methodology doc exists.

    We parse the doc for backtick-quoted paths matching the repo-relative
    pattern ``packages/temper-placer/tests/...`` and assert they resolve.
    """
    text = _METHODOLOGY_DOC.read_text(encoding="utf-8")

    # Extract paths in backticks that start with packages/temper-placer/tests/
    paths_found: set[str] = set()
    for match in re.finditer(r"`([^`]+)`", text):
        candidate = match.group(1)
        if candidate.startswith("packages/temper-placer/tests/"):
            paths_found.add(candidate)

    assert paths_found, "No file-path references found in methodology doc — drift check is vacuous"

    missing = [p for p in paths_found if not (_REPO_ROOT / p).is_file()]
    assert not missing, (
        f"Methodology doc references {len(missing)} file(s) that do not exist:\n"
        + "\n".join(f"  - {m}" for m in sorted(missing))
    )


def test_referenced_files_match_battery_list() -> None:
    """The set of files in _REFERENCED_FILES matches what the doc references
    (prevents adding a new file to the doc but forgetting to add it here)."""
    text = _METHODOLOGY_DOC.read_text(encoding="utf-8")
    doc_paths: set[str] = set()
    for match in re.finditer(r"`([^`]+)`", text):
        candidate = match.group(1)
        if candidate.startswith("packages/temper-placer/tests/"):
            doc_paths.add(candidate)

    expected = set(_REFERENCED_FILES)
    if doc_paths != expected:
        only_in_doc = doc_paths - expected
        only_in_list = expected - doc_paths
        msg_parts: list[str] = []
        if only_in_doc:
            msg_parts.append(f"  In doc but not in _REFERENCED_FILES: {sorted(only_in_doc)}")
        if only_in_list:
            msg_parts.append(f"  In _REFERENCED_FILES but not in doc: {sorted(only_in_list)}")
        pytest.fail("Drift between methodology doc and _REFERENCED_FILES:\n" + "\n".join(msg_parts))
