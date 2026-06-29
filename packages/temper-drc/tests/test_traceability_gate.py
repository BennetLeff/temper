"""Traceability gate tests: validate @req annotations and check requirement coverage.

R2 (test_req_annotations_valid):
    Parses @req(<plan-id>, <req-id>) annotations from opted-in source files
    and validates each against the plan document: plan-id in registry, plan
    status is active, req-id is defined and not deferred, annotation is in
    an appropriate opted-in directory.

R3 (test_req_coverage_complete):
    For every active plan, checks that every non-deferred requirement has
    at least one @req annotation in an opted-in file within the plan's scope.

Plan requirement parsing regex (version 1):
    In-scope requirements: lines matching ``^- R\\d+[.:]`` in sections
    headed "In scope", "Requirements", or "Scope Boundaries" (the plan's
    ### In scope / ## Scope Boundaries blocks).
    Deferred: R<num> IDs found in sections headed ``### Deferred`` or
    ``## Deferred``.
    Plan status: YAML frontmatter field ``status``.

Runs as a standard pytest and is collected by the existing
"Run temper-drc tests" CI step.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

REGISTRY_PATH = REPO_ROOT / "docs" / "traceability-registry.yaml"

_PYTHON_REQ_RE = re.compile(r"#\s*@req\((\w+),\s*(\w+)\):?(.*)")
_C_REQ_RE = re.compile(r"//\s*@req\((\w+),\s*(\w+)\):?(.*)")

_REQUIREMENT_DEF_RE = re.compile(r"^-\s*([RU]\d+)[.:]")
_REQUIREMENT_INLINE_RE = re.compile(r"\b([RU]\d+)\b")
_DEFERRED_HEADING_RE = re.compile(r"^#{2,3}\s+Deferred", re.IGNORECASE)
_NON_DEFERRED_SECTION_RE = re.compile(
    r"^#{2,3}\s+(In scope|Requirements|Scope Boundaries)(\s|$)", re.IGNORECASE
)

_YAML_FRONTMATTER_RE = re.compile(r"^---\s*$(.*?)^---\s*$", re.MULTILINE | re.DOTALL)


def _load_registry() -> dict:
    with open(REGISTRY_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _find_traceability_dirs(root: Path) -> dict[Path, str | None]:
    """Walk root and return {dir_path: traceability_content} for opted-in dirs.

    traceability_content is the raw file content (empty string for an empty
    sentinel file, or a YAML string like 'plans: [N4]').
    """
    opted_in: dict[Path, str | None] = {}
    for sentinel in sorted(root.rglob("TRACEABILITY")):
        if sentinel.is_file():
            content = sentinel.read_text(encoding="utf-8").strip() or None
            opted_in[sentinel.parent] = content
    return opted_in


def _parse_traceability_plan_list(content: str | None) -> set[str] | None:
    """Return the set of allowed plan-ids, or None (all allowed)."""
    if content is None:
        return None
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict) and "plans" in data:
            return set(data["plans"])
    except yaml.YAMLError:
        pass
    return None


def _is_file_in_scope(file_path: Path, scope: list[str]) -> bool:
    """Check if file_path (relative to repo root) is in or under a scope path."""
    try:
        rel = file_path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    rel_str = str(rel)
    for scope_entry in scope:
        if rel_str == scope_entry or rel_str.startswith(scope_entry + "/"):
            return True
    return False


def _parse_plan_frontmatter(plan_path: Path) -> dict:
    """Parse YAML frontmatter from a plan markdown file."""
    text = plan_path.read_text(encoding="utf-8")
    m = _YAML_FRONTMATTER_RE.search(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _parse_requirements(plan_text: str) -> tuple[set[str], set[str]]:
    """Parse requirement IDs and deferred requirement IDs from plan markdown.

    Returns (all_req_ids, deferred_req_ids).
    The parser is conservative: a req-id is considered non-deferred unless it
    appears *only* in a Deferred section and never in an In-scope section.
    Ambiguous req-ids (appearing in both) are treated as non-deferred.
    """
    non_deferred_ids: set[str] = set()
    deferred_ids: set[str] = set()
    in_deferred_section = False
    in_non_deferred_section = False
    section_level = 0

    for line in plan_text.splitlines():
        # Track heading level and whether we're in a Deferred section
        heading_match = re.match(r"^(#{2,3})\s+(.+)", line)
        if heading_match:
            hashes = heading_match.group(1)
            heading_text = heading_match.group(2).strip()
            level = len(hashes)
            if re.match(r"Deferred", heading_text, re.IGNORECASE) and not heading_text.lower().startswith(
                "deferred to"
            ):
                in_deferred_section = True
                in_non_deferred_section = False
                section_level = level
            elif re.match(
                r"(In scope|Requirements|Scope Boundaries)(\s|$)",
                heading_text,
                re.IGNORECASE,
            ):
                in_non_deferred_section = True
                in_deferred_section = False
                section_level = level
            elif level < section_level and section_level > 0:
                # Higher-level heading ends the current section
                in_deferred_section = False
                in_non_deferred_section = False
                section_level = level
            else:
                section_level = level

            # Extract requirement IDs from heading text in any section
            # (catches U<N>, R<N> patterns in e.g. ### U1. headings)
            for m in _REQUIREMENT_INLINE_RE.finditer(heading_text):
                req_id = m.group(1)
                if req_id not in non_deferred_ids and req_id not in deferred_ids:
                    non_deferred_ids.add(req_id)
            continue

        # Collect requirement IDs from bullet lines
        if in_non_deferred_section:
            # Also extract requirement IDs from heading lines (e.g., ### U1., ### R2:)
            for m in _REQUIREMENT_INLINE_RE.finditer(line):
                req_id = m.group(1)
                if req_id not in non_deferred_ids:
                    non_deferred_ids.add(req_id)
            req_match = _REQUIREMENT_DEF_RE.match(line)
            if req_match:
                non_deferred_ids.add(req_match.group(1))

        if in_deferred_section:
            for m in _REQUIREMENT_INLINE_RE.finditer(line):
                deferred_ids.add(m.group(1))

    # Remove any req-id from deferred_ids if it also appears in non_deferred
    # (conservative: ambiguous = non-deferred)
    ambiguous = deferred_ids & non_deferred_ids
    deferred_ids -= ambiguous

    return non_deferred_ids, deferred_ids


def _parse_plan_requirements(plan_path: Path) -> tuple[set[str], set[str]]:
    """Parse a plan document for requirement IDs and deferred requirement IDs."""
    return _parse_requirements(plan_path.read_text(encoding="utf-8"))


def _scan_annotations(
    opted_in_dirs: dict[Path, str | None],
    _registry: dict,
) -> list[dict]:
    """Scan opted-in directories for @req annotations.

    Returns list of annotation dicts with keys:
        file, line, plan_id, req_id, note, traceability_dir, traceability_content
    """
    annotations: list[dict] = []
    for opt_dir, sentinel_content in opted_in_dirs.items():
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
    return annotations


def _validate_annotation(ann: dict, registry: dict) -> list[str]:
    """Validate a single annotation. Returns list of violation messages."""
    violations: list[str] = []
    plan_id = ann["plan_id"]
    req_id = ann["req_id"]
    plans = registry.get("plans", {})

    # Check plan-id in registry
    if plan_id not in plans:
        violations.append(
            f"plan-id '{plan_id}' is not in the traceability registry "
            f"(docs/traceability-registry.yaml)"
        )
        return violations

    plan_entry = plans[plan_id]
    plan_path = REPO_ROOT / plan_entry["path"]

    # Check plan status
    frontmatter = _parse_plan_frontmatter(plan_path)
    status = frontmatter.get("status", "unknown")
    if status != "active":
        violations.append(
            f"plan '{plan_id}' has status '{status}', expected 'active'. "
            f"Superseded plans cannot carry live annotations."
        )
        return violations

    # Parse requirements from plan
    all_reqs, deferred_reqs = _parse_plan_requirements(plan_path)

    # Check req-id is defined
    if req_id not in all_reqs:
        violations.append(
            f"requirement '{req_id}' is not defined in {plan_entry['path']}"
        )
        return violations

    # Check req-id is not deferred
    if req_id in deferred_reqs:
        violations.append(
            f"requirement '{req_id}' is deferred in {plan_entry['path']}. "
            f"Deferred requirements must not carry annotations."
        )

    # Check directory-level traceability scope
    allowed_plans = _parse_traceability_plan_list(ann["sentinel_content"])
    if allowed_plans is not None and plan_id not in allowed_plans:
        violations.append(
            f"plan-id '{plan_id}' is not in the directory's TRACEABILITY opt-in list. "
            f"Add '{plan_id}' to the directory's TRACEABILITY file or move the "
            f"annotation to the correct directory."
        )

    return violations


def _check_coverage(
    annotations: list[dict],
    registry: dict,
    opted_in_dirs: dict[Path, str | None],
) -> list[str]:
    """Check that every non-deferred requirement has at least one annotation.

    Only gates requirements for plans whose scope files have opted into
    traceability (at least one scope file is under an opted-in directory).
    Returns list of uncovered-requirement messages.
    """
    violations: list[str] = []
    plans = registry.get("plans", {})

    # Build set of (plan_id, req_id) pairs that have annotations
    annotated_reqs: set[tuple[str, str]] = set()
    for ann in annotations:
        annotated_reqs.add((ann["plan_id"], ann["req_id"]))

    for plan_id, plan_entry in plans.items():
        plan_path = REPO_ROOT / plan_entry["path"]
        frontmatter = _parse_plan_frontmatter(plan_path)
        status = frontmatter.get("status", "unknown")
        if status != "active":
            continue

        all_reqs, deferred_reqs = _parse_plan_requirements(plan_path)
        required = all_reqs - deferred_reqs

        if not required:
            continue

        scope = plan_entry.get("scope", [])
        # Check if any scope file is under an opted-in directory
        scope_opted_in = False
        for opt_dir in opted_in_dirs:
            for scope_entry in scope:
                scope_path = REPO_ROOT / scope_entry
                try:
                    scope_path.resolve().relative_to(opt_dir.resolve())
                    scope_opted_in = True
                    break
                except ValueError:
                    pass
            if scope_opted_in:
                break

        if not scope_opted_in:
            # Plan hasn't opted into traceability — skip coverage gate
            continue

        for req_id in sorted(required):
            if (plan_id, req_id) in annotated_reqs:
                continue

            violations.append(
                f"{plan_id} {req_id}: no @req annotation found in any opted-in file "
                f"within plan scope. Requirement is uncovered."
            )

    return violations


# --- pytest test functions ---


def _collect_annotation_violations() -> list[str]:
    registry = _load_registry()
    opted_in = _find_traceability_dirs(REPO_ROOT)
    annotations = _scan_annotations(opted_in, registry)

    reports: list[str] = []
    for ann in annotations:
        try:
            rel_path = ann["file"].resolve().relative_to(REPO_ROOT)
        except ValueError:
            rel_path = ann["file"]
        for v in _validate_annotation(ann, registry):
            reports.append(f"{rel_path}:{ann['line']}: {v}")
    return sorted(reports)


def _collect_coverage_violations() -> list[str]:
    registry = _load_registry()
    opted_in = _find_traceability_dirs(REPO_ROOT)
    annotations = _scan_annotations(opted_in, registry)
    return sorted(_check_coverage(annotations, registry, opted_in))


def test_req_annotations_valid() -> None:
    """R2 gate: every @req annotation references a live, non-deferred requirement."""
    violations = _collect_annotation_violations()
    if violations:
        report = "\n".join(violations)
        pytest.fail(f"Invalid @req annotations found:\n{report}")


def test_req_coverage_complete() -> None:
    """R3 gate: every non-deferred requirement in active plans has an annotation."""
    violations = _collect_coverage_violations()
    if violations:
        report = "\n".join(violations)
        pytest.fail(f"Uncovered requirements found:\n{report}")
