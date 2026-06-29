"""BMC adoption gate: enforce ESL + BMC test coverage for every Constraint subclass.

# @req(2026-06-28-006, FR-CI5): CI gate script scans constraint_model.py

AST-scans ``constraint_model.py`` for ``Constraint`` subclasses and verifies
each has:
  1. An ``esl()`` method on the class definition
  2. An entry in ``ESL_REGISTRY``
  3. An ``isinstance`` branch in ``populate_sat_from_constraints()``
  4. At least one BMC test reference in ``tests/router_v6/test_bmc_*.py``

Exit codes (following the import_linter_gate.py pattern):
  0 — All constraint types have full ESL + encoding + BMC test coverage
  3 — Missing ESL or BMC test (blocks merge)
  5 — Tool error (script failure, missing files)
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

CONSTRAINT_MODEL = (
    REPO_ROOT
    / "packages/temper-placer/src/temper_placer/router_v6/constraint_model.py"
)
SAT_MODEL = (
    REPO_ROOT
    / "packages/temper-placer/src/temper_placer/router_v6/sat_model.py"
)
TEST_DIR = REPO_ROOT / "packages/temper-placer/tests/router_v6"


EXIT_OK = 0
EXIT_MISSING = 3
EXIT_ERROR = 5


def _die(code: int, msg: str) -> None:
    print(f"[BMC-GATE] {msg}", file=sys.stderr)
    sys.exit(code)


def _find_constraint_subclasses(tree: ast.AST) -> list[str]:
    """Return sorted names of all Constraint subclasses (excl. Constraint itself)."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = None
                if isinstance(base, ast.Name):
                    base_name = base.id
                if base_name == "Constraint" and node.name != "Constraint":
                    names.append(node.name)
    return sorted(names)


def _class_has_esl(tree: ast.AST, class_name: str) -> bool:
    """Check that a class definition has an esl() method."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "esl":
                    return True
    return False


def _has_esl_registry_entry(code: str, class_name: str) -> bool:
    """Check that ESL_REGISTRY contains an entry for class_name."""
    return f'ESL_REGISTRY["{class_name}"]' in code


def _has_encoding_branch(code: str, class_name: str) -> bool:
    """Check that populate_sat_from_constraints has isinstance branch."""
    return f"isinstance(constraint, {class_name})" in code


def _has_bmc_test_reference(class_name: str) -> bool:
    """Check that at least one BMC test file references class_name."""
    tested = False
    for entry in TEST_DIR.glob("test_bmc_*.py"):
        text = entry.read_text()
        if class_name in text:
            tested = True
            break
    return tested


def main() -> None:
    if not CONSTRAINT_MODEL.exists():
        _die(EXIT_ERROR, f"constraint_model.py not found: {CONSTRAINT_MODEL}")
    if not SAT_MODEL.exists():
        _die(EXIT_ERROR, f"sat_model.py not found: {SAT_MODEL}")

    cm_code = CONSTRAINT_MODEL.read_text()
    cm_tree = ast.parse(cm_code)

    sm_code = SAT_MODEL.read_text()

    subclasses = _find_constraint_subclasses(cm_tree)

    if not subclasses:
        _die(EXIT_ERROR, "No Constraint subclasses found — parser error?")

    violations: list[str] = []

    for cls in subclasses:
        missing: list[str] = []

        if not _class_has_esl(cm_tree, cls):
            missing.append("esl() method")
        if not _has_esl_registry_entry(cm_code, cls):
            missing.append("ESL_REGISTRY entry")
        if not _has_encoding_branch(sm_code, cls):
            missing.append("encoding branch in populate_sat_from_constraints")
        if not _has_bmc_test_reference(cls):
            missing.append("BMC test reference")

        if missing:
            violations.append(f"  {cls}: missing {', '.join(missing)}")

    if violations:
        header = (
            f"BMC adoption gate FAILED: {len(violations)} constraint(s) "
            f"missing required coverage:"
        )
        _die(EXIT_MISSING, f"{header}\n" + "\n".join(violations))

    print(
        f"[BMC-GATE] OK: {len(subclasses)} constraint types have full "
        f"ESL + encoding + BMC test coverage"
    )


if __name__ == "__main__":
    main()
