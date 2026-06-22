"""AST linter that rejects bare float literals matching safety authority values.

Scans every .py file under packages/ and scripts/ (excluding tests/ and the
authority module itself) and flags any ``ast.Constant`` node whose value is a
float present in ``SAFETY_CONSTANT_AUTHORITY``.  The check can be suppressed
with a ``# allow-safety-constant: <reason>`` comment on the same line.

Runs as a standard pytest and fails on the first violation.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

_placer_src = _REPO_ROOT / "packages" / "temper-placer" / "src"
if str(_placer_src) not in sys.path:
    sys.path.insert(0, str(_placer_src))

from temper_placer.core.design_rules import SAFETY_CONSTANT_AUTHORITY  # noqa: E402

AUTHORITY_VALUES: set[float] = {v for (_, _, v) in SAFETY_CONSTANT_AUTHORITY}

_AUTHORITY_MODULE_SUFFIX = "temper_placer/core/design_rules.py"

_ALLOW_COMMENT_PREFIX = "# allow-safety-constant:"


def _is_authority_module(file_path: Path) -> bool:
    return str(file_path).endswith(_AUTHORITY_MODULE_SUFFIX)


def _is_test_dir(file_path: Path) -> bool:
    parts = file_path.parts
    return "tests" in parts


def _python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for py_file in root.rglob("*.py"):
        if _is_test_dir(py_file):
            continue
        if _is_authority_module(py_file):
            continue
        files.append(py_file)
    return files


def _scan_file(file_path: Path) -> list[tuple[int, float, str]]:
    violations: list[tuple[int, float, str]] = []
    source = file_path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if not isinstance(node.value, float):
            continue
        if node.value not in AUTHORITY_VALUES:
            continue
        lineno = getattr(node, "lineno", 0)
        if not lineno:
            continue
        line_text = source_lines[lineno - 1] if lineno <= len(source_lines) else ""
        if _ALLOW_COMMENT_PREFIX in line_text:
            continue
        matched_triples = [
            (nc, field, v)
            for (nc, field, v) in SAFETY_CONSTANT_AUTHORITY
            if v == node.value
        ]
        triples_str = "; ".join(
            f'TEMPER_NET_CLASSES["{nc}"].{field}'
            for (nc, field, _) in matched_triples
        )
        violations.append((lineno, node.value, triples_str))

    return violations


def _collect_violations() -> list[str]:
    reports: list[str] = []
    scan_roots = [
        _REPO_ROOT / "packages",
        _REPO_ROOT / "scripts",
    ]
    for root in scan_roots:
        if not root.is_dir():
            continue
        for py_file in _python_files(root):
            for lineno, value, triples_str in _scan_file(py_file):
                rel_path = py_file.relative_to(_REPO_ROOT)
                reports.append(
                    f"{rel_path}:{lineno}: float literal {value!r} matches "
                    f"authority value(s): {triples_str} — replace with "
                    f"`from temper_placer.core.design_rules import TEMPER_NET_CLASSES` "
                    f"or add `# allow-safety-constant: <reason>`"
                )
    return sorted(reports)


def test_no_bare_safety_constant_literals():
    violations = _collect_violations()
    if violations:
        report = "\n".join(violations)
        pytest.fail(f"Bare safety-constant float literals found:\n{report}")
