#!/usr/bin/env python3
"""CLI wrapper for traceability gate checks.

Usage:
    uv run python scripts/check_traceability.py --all
    uv run python scripts/check_traceability.py --check-annotations
    uv run python scripts/check_traceability.py --check-coverage
    uv run python scripts/check_traceability.py --check-registry-scope
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _collect_and_validate(registry: dict, repo_root: Path):
    """Shared logic imported from test_traceability_gate.py style."""
    import re as _re

    opted_in: dict[Path, str | None] = {}
    for sentinel in sorted(repo_root.rglob("TRACEABILITY")):
        if sentinel.is_file():
            content = sentinel.read_text(encoding="utf-8").strip() or None
            opted_in[sentinel.parent] = content

    _PYTHON_REQ_RE = _re.compile(r"#\s*@req\((\w+),\s*(\w+)\):?(.*)")
    _C_REQ_RE = _re.compile(r"//\s*@req\((\w+),\s*(\w+)\):?(.*)")

    annotations: list[dict] = []
    for opt_dir, sentinel_content in opted_in.items():
        for ext, regex in [("*.py", _PYTHON_REQ_RE), ("*.c", _C_REQ_RE), ("*.h", _C_REQ_RE)]:
            for src_file in sorted(opt_dir.rglob(ext)):
                try:
                    lines = src_file.read_text(encoding="utf-8").splitlines()
                except (UnicodeDecodeError, OSError):
                    continue
                for lineno, line in enumerate(lines, start=1):
                    for m in regex.finditer(line):
                        annotations.append(
                            {
                                "file": src_file,
                                "line": lineno,
                                "plan_id": m.group(1),
                                "req_id": m.group(2),
                                "note": m.group(3).strip() if m.lastindex and m.lastindex >= 3 else "",
                                "traceability_dir": opt_dir,
                                "sentinel_content": sentinel_content,
                            }
                        )
    return opted_in, annotations


def _run_registry_scope_check(registry: dict, repo_root: Path) -> list[str]:
    """Validate that every scope entry in the registry points to a git-tracked file."""
    violations: list[str] = []
    git_files = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    git_files_set = set(git_files)

    plans = registry.get("plans", {})
    for plan_id, plan_entry in plans.items():
        plan_path_str = plan_entry.get("path", "")
        plan_path = repo_root / plan_path_str
        if not plan_path.exists():
            violations.append(
                f"{plan_id}: plan document '{plan_path_str}' does not exist"
            )
        for scope_entry in plan_entry.get("scope", []):
            if scope_entry not in git_files_set:
                violations.append(
                    f"{plan_id}: scope entry '{scope_entry}' is not tracked by git"
                )
    return sorted(violations)


def _parse_plan_frontmatter(plan_text: str) -> dict:
    import re as _re

    import yaml

    _YAML_FRONTMATTER_RE = _re.compile(
        r"^---\s*$(.*?)^---\s*$", _re.MULTILINE | _re.DOTALL
    )
    m = _YAML_FRONTMATTER_RE.search(plan_text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _parse_requirements(plan_text: str) -> tuple[set[str], set[str]]:
    import re as _re

    _REQUIREMENT_DEF_RE = _re.compile(r"^-\s*(R\d+)[.:]")
    _REQUIREMENT_INLINE_RE = _re.compile(r"\b(R\d+)\b")

    non_deferred_ids: set[str] = set()
    deferred_ids: set[str] = set()
    in_deferred_section = False
    in_non_deferred_section = False
    section_level = 0

    for line in plan_text.splitlines():
        heading_match = _re.match(r"^(#{2,3})\s+(.+)", line)
        if heading_match:
            hashes = heading_match.group(1)
            heading_text = heading_match.group(2).strip()
            level = len(hashes)
            if _re.match(r"Deferred", heading_text, _re.IGNORECASE) and not heading_text.lower().startswith(
                "deferred to"
            ):
                in_deferred_section = True
                in_non_deferred_section = False
                section_level = level
            elif _re.match(
                r"(In scope|Requirements|Scope Boundaries)(\s|$)",
                heading_text,
                _re.IGNORECASE,
            ):
                in_non_deferred_section = True
                in_deferred_section = False
                section_level = level
            elif level <= section_level and section_level > 0:
                in_deferred_section = False
                in_non_deferred_section = False
                section_level = 0
            continue

        if in_non_deferred_section:
            req_match = _REQUIREMENT_DEF_RE.match(line)
            if req_match:
                non_deferred_ids.add(req_match.group(1))
            else:
                for m in _REQUIREMENT_INLINE_RE.finditer(line):
                    non_deferred_ids.add(m.group(1))

        if in_deferred_section:
            for m in _REQUIREMENT_INLINE_RE.finditer(line):
                deferred_ids.add(m.group(1))

    ambiguous = deferred_ids & non_deferred_ids
    deferred_ids -= ambiguous
    return non_deferred_ids, deferred_ids


def _parse_traceability_plan_list(content: str | None) -> set[str] | None:
    import yaml

    if content is None:
        return None
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict) and "plans" in data:
            return set(data["plans"])
    except yaml.YAMLError:
        pass
    return None


def _is_file_in_scope(file_path: Path, scope: list[str], repo_root: Path) -> bool:
    try:
        rel = file_path.resolve().relative_to(repo_root)
    except ValueError:
        return False
    rel_str = str(rel)
    for scope_entry in scope:
        if rel_str == scope_entry or rel_str.startswith(scope_entry + "/"):
            return True
    return False


def check_annotations(registry: dict, repo_root: Path) -> int:
    """R2 gate: validate every @req annotation."""
    _, annotations = _collect_and_validate(registry, repo_root)
    plans = registry.get("plans", {})
    violations: list[str] = []

    for ann in annotations:
        try:
            rel_path = ann["file"].resolve().relative_to(repo_root)
        except ValueError:
            rel_path = ann["file"]
        plan_id = ann["plan_id"]
        req_id = ann["req_id"]

        if plan_id not in plans:
            violations.append(
                f"{rel_path}:{ann['line']}: plan-id '{plan_id}' is not in the registry"
            )
            continue

        plan_entry = plans[plan_id]
        plan_path = repo_root / plan_entry["path"]

        if not plan_path.exists():
            violations.append(
                f"{rel_path}:{ann['line']}: plan document not found at {plan_entry['path']}"
            )
            continue

        frontmatter = _parse_plan_frontmatter(plan_path.read_text(encoding="utf-8"))
        status = frontmatter.get("status", "unknown")
        if status != "active":
            violations.append(
                f"{rel_path}:{ann['line']}: plan '{plan_id}' has status '{status}', "
                f"expected 'active'"
            )
            continue

        all_reqs, deferred_reqs = _parse_requirements(plan_path.read_text(encoding="utf-8"))
        if req_id not in all_reqs:
            violations.append(
                f"{rel_path}:{ann['line']}: requirement '{req_id}' not defined in "
                f"{plan_entry['path']}"
            )
        elif req_id in deferred_reqs:
            violations.append(
                f"{rel_path}:{ann['line']}: requirement '{req_id}' is deferred in "
                f"{plan_entry['path']}"
            )

        allowed_plans = _parse_traceability_plan_list(ann["sentinel_content"])
        if allowed_plans is not None and plan_id not in allowed_plans:
            violations.append(
                f"{rel_path}:{ann['line']}: plan-id '{plan_id}' not in directory's "
                f"TRACEABILITY opt-in list"
            )

    if violations:
        for v in sorted(violations):
            print(f"VIOLATION: {v}")
        return 1
    print("R2 gate passed: all @req annotations are valid.")
    return 0


def check_coverage(registry: dict, repo_root: Path) -> int:
    """R3 gate: check requirement coverage."""
    opted_in, annotations = _collect_and_validate(registry, repo_root)
    plans = registry.get("plans", {})
    annotated_reqs: set[tuple[str, str]] = set()
    for ann in annotations:
        annotated_reqs.add((ann["plan_id"], ann["req_id"]))

    violations: list[str] = []
    for plan_id, plan_entry in plans.items():
        plan_path = repo_root / plan_entry["path"]
        if not plan_path.exists():
            continue
        frontmatter = _parse_plan_frontmatter(plan_path.read_text(encoding="utf-8"))
        status = frontmatter.get("status", "unknown")
        if status != "active":
            continue

        scope = plan_entry.get("scope", [])
        scope_opted_in = False
        for opt_dir in opted_in:
            for scope_entry in scope:
                scope_path = repo_root / scope_entry
                try:
                    scope_path.resolve().relative_to(opt_dir.resolve())
                    scope_opted_in = True
                    break
                except ValueError:
                    pass
            if scope_opted_in:
                break

        if not scope_opted_in:
            continue

        all_reqs, deferred_reqs = _parse_requirements(plan_path.read_text(encoding="utf-8"))
        required = all_reqs - deferred_reqs
        if not required:
            continue

        for req_id in sorted(required):
            if (plan_id, req_id) not in annotated_reqs:
                violations.append(
                    f"{plan_id} {req_id}: no @req annotation found — requirement is uncovered"
                )

    if violations:
        for v in sorted(violations):
            print(f"UNCOVERED: {v}")
        return 1
    print("R3 gate passed: all requirements are covered.")
    return 0


def check_registry_scope(registry: dict, repo_root: Path) -> int:
    """Validate registry scope entries against git-tracked files."""
    violations = _run_registry_scope_check(registry, repo_root)
    plan_path_violations = []
    for plan_id, plan_entry in registry.get("plans", {}).items():
        plan_path = repo_root / plan_entry.get("path", "")
        if not plan_path.exists():
            plan_path_violations.append(
                f"{plan_id}: plan document '{plan_entry.get('path', '')}' does not exist"
            )
    all_violations = sorted(violations + plan_path_violations)
    if all_violations:
        for v in all_violations:
            print(f"SCOPE ISSUE: {v}")
        return 1
    print("Registry scope check passed: all entries valid.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lightweight requirements-to-code traceability checks"
    )
    parser.add_argument(
        "--check-annotations",
        action="store_true",
        help="R2 gate: validate @req annotations against plan documents",
    )
    parser.add_argument(
        "--check-coverage",
        action="store_true",
        help="R3 gate: check that every non-deferred requirement has an annotation",
    )
    parser.add_argument(
        "--check-registry-scope",
        action="store_true",
        help="Validate that registry scope entries are git-tracked files",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all three checks",
    )

    args = parser.parse_args()

    if not (args.check_annotations or args.check_coverage or args.check_registry_scope or args.all):
        parser.print_help()
        sys.exit(1)

    import yaml

    registry_path = REPO_ROOT / "docs" / "traceability-registry.yaml"
    with open(registry_path, encoding="utf-8") as fh:
        registry = yaml.safe_load(fh)

    repo_root_path = REPO_ROOT
    exit_code = 0

    if args.all or args.check_annotations:
        if check_annotations(registry, repo_root_path) != 0:
            exit_code = 1

    if args.all or args.check_coverage:
        if check_coverage(registry, repo_root_path) != 0:
            exit_code = 1

    if args.all or args.check_registry_scope:
        if check_registry_scope(registry, repo_root_path) != 0:
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
