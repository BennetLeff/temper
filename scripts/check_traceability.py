#!/usr/bin/env python3
"""CLI wrapper for traceability gate checks.

Usage:
    uv run python scripts/check_traceability.py --all
    uv run python scripts/check_traceability.py --check-annotations
    uv run python scripts/check_traceability.py --check-coverage
    uv run python scripts/check_traceability.py --check-registry-scope

Scope model
-----------
**2026-07-27 rewrite** (see
docs/evidence/2026-07-27-traceability-scope-fix.md, responding to
docs/evidence/2026-07-27-gate-subset-blindness-audit.md): the previous scope
model gated *both* R2 (annotation validity) and R3 (requirement coverage) on
whether a directory happened to contain a `TRACEABILITY` sentinel file.
Exactly one directory in the whole repo ever had one
(`packages/temper-placer/tests/router_v6/`), so R2/R3 could only ever see
annotations there -- and R3's coverage loop silently `continue`d past every
plan whose declared `scope` didn't overlap that one directory, with no note
in the output. The headline symptom: `R3 gate passed: all requirements are
covered.` printed with zero indication that only 1 of the registry's plans
was ever eligible to be checked.

The scope is now **driven directly by `docs/traceability-registry.yaml`**
rather than by filesystem sentinels: the scan universe for `@req`
annotations is the union of every registered plan's `scope` entries (files
and directories), not "whatever happens to sit under an opted-in
directory." A `TRACEABILITY` sentinel still narrows which plan-ids are
*accepted* in the directory it sits in (the "scoped sentinel" feature in
docs/TRACEABILITY.md) -- it no longer gates whether a directory's
annotations are scanned or a plan's coverage is checked at all.

This was chosen over two alternatives considered:
- **default-include with a narrow exclude list** (the shape
  `check_vacuous_gates.py` was rewritten into the same day) doesn't have a
  natural meaning here: there is no fixed directory convention analogous to
  `packages/*/src` for "where annotatable code lives" -- the registry's
  `scope` field already names the exact files, so "default-include" in this
  domain *is* "scan what the registry says," i.e. this option.
- **keep the sentinel opt-in but fail closed on an unclaimed plan** was
  rejected because it still leaves R2 blind to any `@req` annotation
  written outside whichever directories happen to hold a sentinel -- it
  fixes R3's silent skip but not R2's narrow visibility, and the registry
  already has this exact information (which files implement which plan)
  more precisely than a per-directory sentinel could.

Coverage is additionally now scope-precise: an annotation only counts
toward a requirement's coverage if it lives in a file within *that same
plan's* declared scope (`_is_file_in_scope` -- previously written but never
called). Without this, an `@req(N10, U1)` annotation sitting in a file that
is actually APC1's scope would have falsely satisfied N10's coverage once
the scan universe widened past a single directory; this closes that gap
before it can be exploited.

No allowlist of any kind was added. The scope is 100% derived from
docs/traceability-registry.yaml, which is itself kept honest by the
`--check-registry-scope` check (every scope entry must be a git-tracked
file) -- there is nothing here that can silently accumulate stale entries
the way a hand-maintained include-list could.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_SOURCE_SUFFIXES = (".py", ".c", ".h")


def _collect_scope_targets(registry: dict, repo_root: Path) -> list[Path]:
    """Union of every registered plan's `scope` entries, resolved to paths.

    This -- not "which directories contain a TRACEABILITY sentinel" -- is
    the traceability gate's scan universe. Driven directly by
    docs/traceability-registry.yaml (see module docstring).
    """
    targets: set[Path] = set()
    for plan_entry in registry.get("plans", {}).values():
        for scope_entry in plan_entry.get("scope", []):
            targets.add(repo_root / scope_entry)
    return sorted(targets)


def _iter_source_files(target: Path) -> list[Path]:
    """Return annotatable (.py/.c/.h) files under *target*.

    *target* may be a file (yielded directly if it has a matching suffix)
    or a directory (recursively globbed). A missing path yields nothing --
    `--check-registry-scope` is responsible for flagging scope entries that
    don't exist or aren't git-tracked; this function just doesn't crash on
    one.
    """
    if target.is_file():
        return [target] if target.suffix in _SOURCE_SUFFIXES else []
    if target.is_dir():
        results: list[Path] = []
        for suffix in _SOURCE_SUFFIXES:
            results.extend(target.rglob(f"*{suffix}"))
        return results
    return []


def _collect_and_validate(registry: dict, repo_root: Path):
    """Scan every file in the registry-driven scope for @req annotations.

    Returns ``(opted_in, annotations, files_scanned)``. ``files_scanned``
    is the denominator both R2 and R3 must report on every run, pass or
    fail (docs/evidence/2026-07-27-gate-subset-blindness-audit.md: a gate
    reporting "0 violations" without saying how much it looked at cannot
    be distinguished from a gate that looked at nothing).
    """
    import re as _re

    opted_in: dict[Path, str | None] = {}
    for sentinel in sorted(repo_root.rglob("TRACEABILITY")):
        if sentinel.is_file():
            content = sentinel.read_text(encoding="utf-8").strip() or None
            opted_in[sentinel.parent] = content

    def _governing_sentinel(file_path: Path) -> tuple[Path | None, str | None]:
        """Nearest ancestor directory (if any) holding a TRACEABILITY
        sentinel, and its content. ``None, None`` means no sentinel
        anywhere above this file -- which is now a normal, unrestricted
        state, not a reason to skip the file (see module docstring)."""
        cur = file_path.parent
        while True:
            if cur in opted_in:
                return cur, opted_in[cur]
            parent = cur.parent
            if parent == cur:
                return None, None
            cur = parent

    _PYTHON_REQ_RE = _re.compile(r"#\s*@req\((\w+),\s*(\w+)\):?(.*)")
    _C_REQ_RE = _re.compile(r"//\s*@req\((\w+),\s*(\w+)\):?(.*)")

    scanned_files: set[Path] = set()
    for target in _collect_scope_targets(registry, repo_root):
        scanned_files.update(_iter_source_files(target))

    annotations: list[dict] = []
    for src_file in sorted(scanned_files):
        regex = _PYTHON_REQ_RE if src_file.suffix == ".py" else _C_REQ_RE
        try:
            lines = src_file.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        traceability_dir, sentinel_content = _governing_sentinel(src_file)
        for lineno, line in enumerate(lines, start=1):
            for m in regex.finditer(line):
                annotations.append(
                    {
                        "file": src_file,
                        "line": lineno,
                        "plan_id": m.group(1),
                        "req_id": m.group(2),
                        "note": m.group(3).strip() if m.lastindex and m.lastindex >= 3 else "",
                        "traceability_dir": traceability_dir,
                        "sentinel_content": sentinel_content,
                    }
                )
    return opted_in, annotations, len(scanned_files)


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
    _, annotations, files_scanned = _collect_and_validate(registry, repo_root)
    plans = registry.get("plans", {})
    n_plans_with_scope = sum(1 for p in plans.values() if p.get("scope"))

    denominator = (
        f"Scanned {files_scanned} file(s) across {n_plans_with_scope} of "
        f"{len(plans)} registered plan(s)' declared scope in "
        f"docs/traceability-registry.yaml; found {len(annotations)} @req "
        f"annotation(s)."
    )

    if files_scanned == 0:
        print(
            f"FAIL (closed): {denominator} An R2 gate that scans zero "
            f"files cannot report a meaningful pass -- check "
            f"docs/traceability-registry.yaml's `scope` entries."
        )
        return 1

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
        print(denominator)
        return 1
    print(f"R2 gate passed: all @req annotations are valid. {denominator}")
    return 0


def check_coverage(registry: dict, repo_root: Path) -> int:
    """R3 gate: check requirement coverage.

    Coverage scope is driven directly by each plan's own `scope` field in
    docs/traceability-registry.yaml, not by whether some directory happens
    to contain a TRACEABILITY sentinel (see module docstring). An
    annotation only counts toward a requirement's coverage if it lives in
    a file within that *same* plan's declared scope (`_is_file_in_scope`)
    -- otherwise an annotation for a different plan sharing a req-id in
    some unrelated file could falsely satisfy coverage now that the scan
    universe is no longer a single directory.

    Fails closed (not a vacuous pass) when: zero files were scanned, zero
    plans are active, or zero non-deferred requirements were parsed across
    every active, in-scope plan -- each of those is "this gate never
    actually evaluated anything," which must never look the same as "this
    gate evaluated everything and found no problems."
    """
    _, annotations, files_scanned = _collect_and_validate(registry, repo_root)
    plans = registry.get("plans", {})

    annotated_by_key: dict[tuple[str, str], list[Path]] = {}
    for ann in annotations:
        annotated_by_key.setdefault((ann["plan_id"], ann["req_id"]), []).append(ann["file"])

    n_plans_with_scope = sum(1 for p in plans.values() if p.get("scope"))
    base_denominator = (
        f"Annotation scan: {files_scanned} file(s) across "
        f"{n_plans_with_scope} of {len(plans)} registered plan(s)' "
        f"declared scope."
    )

    if files_scanned == 0:
        print(
            f"FAIL (closed): {base_denominator} An R3 coverage gate that "
            f"scans zero files cannot report a meaningful pass -- check "
            f"docs/traceability-registry.yaml's `scope` entries."
        )
        return 1

    violations: list[str] = []
    active_plans = 0
    unclaimed_plans: list[str] = []
    checkable_plans = 0
    total_required = 0
    total_uncovered = 0

    for plan_id, plan_entry in plans.items():
        plan_path = repo_root / plan_entry["path"]
        if not plan_path.exists():
            continue
        frontmatter = _parse_plan_frontmatter(plan_path.read_text(encoding="utf-8"))
        status = frontmatter.get("status", "unknown")
        if status != "active":
            continue
        active_plans += 1

        scope = plan_entry.get("scope", [])
        if not scope:
            unclaimed_plans.append(plan_id)
            violations.append(
                f"{plan_id}: plan has no declared `scope` in "
                f"docs/traceability-registry.yaml -- requirement coverage "
                f"cannot be verified for any requirement in this plan"
            )
            continue
        checkable_plans += 1

        all_reqs, deferred_reqs = _parse_requirements(plan_path.read_text(encoding="utf-8"))
        required = all_reqs - deferred_reqs
        if not required:
            continue
        total_required += len(required)

        for req_id in sorted(required):
            candidate_files = annotated_by_key.get((plan_id, req_id), [])
            covered = any(_is_file_in_scope(f, scope, repo_root) for f in candidate_files)
            if not covered:
                total_uncovered += 1
                violations.append(
                    f"{plan_id} {req_id}: no @req annotation found in the "
                    f"plan's declared scope — requirement is uncovered"
                )

    denominator = (
        f"{base_denominator} Checked {checkable_plans} of {active_plans} "
        f"active plan(s) ({len(unclaimed_plans)} with no declared scope) "
        f"out of {len(plans)} total registered plan(s); {total_required} "
        f"non-deferred requirement(s) parsed; {total_uncovered} uncovered."
    )

    if active_plans == 0:
        print(
            f"FAIL (closed): {denominator} No active plan exists in the "
            f"registry -- an R3 gate with zero active plans to check "
            f"cannot report a meaningful pass."
        )
        return 1

    if violations:
        for v in sorted(violations):
            print(f"UNCOVERED: {v}")
        print(denominator)
        return 1

    if total_required == 0:
        print(
            f"FAIL (closed): {denominator} Zero non-deferred requirements "
            f"were parsed across any active, in-scope plan -- an R3 gate "
            f"that never evaluated a single requirement cannot report a "
            f"meaningful pass."
        )
        return 1

    print(f"R3 gate passed: all requirements are covered. {denominator}")
    return 0


def check_registry_scope(registry: dict, repo_root: Path) -> int:
    """Validate registry scope entries against git-tracked files."""
    plans = registry.get("plans", {})
    n_scope_entries = sum(len(p.get("scope", [])) for p in plans.values())
    denominator = f"Checked {len(plans)} plan(s), {n_scope_entries} scope entrie(s)."

    if not plans:
        print(
            "FAIL (closed): docs/traceability-registry.yaml declares zero "
            "plans -- a registry-scope gate with nothing to validate "
            "cannot report a meaningful pass."
        )
        return 1

    violations = _run_registry_scope_check(registry, repo_root)
    plan_path_violations = []
    for plan_id, plan_entry in plans.items():
        plan_path = repo_root / plan_entry.get("path", "")
        if not plan_path.exists():
            plan_path_violations.append(
                f"{plan_id}: plan document '{plan_entry.get('path', '')}' does not exist"
            )
    all_violations = sorted(violations + plan_path_violations)
    if all_violations:
        for v in all_violations:
            print(f"SCOPE ISSUE: {v}")
        print(denominator)
        return 1
    print(f"Registry scope check passed: all entries valid. {denominator}")
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
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Override path to the traceability registry YAML (default: "
        "docs/traceability-registry.yaml). Exists for fail-closed "
        "verification against synthetic/missing registries, not for "
        "normal use.",
    )

    args = parser.parse_args()

    if not (args.check_annotations or args.check_coverage or args.check_registry_scope or args.all):
        parser.print_help()
        sys.exit(1)

    import yaml

    registry_path = args.registry if args.registry is not None else (
        REPO_ROOT / "docs" / "traceability-registry.yaml"
    )
    if not registry_path.exists():
        print(f"FAIL (closed): traceability registry not found at {registry_path}.")
        sys.exit(1)

    with open(registry_path, encoding="utf-8") as fh:
        registry = yaml.safe_load(fh) or {}

    if not isinstance(registry, dict):
        print(
            f"FAIL (closed): traceability registry at {registry_path} did "
            f"not parse to a mapping."
        )
        sys.exit(1)

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
