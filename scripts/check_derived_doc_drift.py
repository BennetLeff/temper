#!/usr/bin/env python3
"""Derived-document drift gate.

Verifies that summary tables which restate requirements from
``docs/FUNCTIONAL_TEST_CRITERIA.md`` (the source of truth for gate
thresholds) have not silently dropped a qualifier, a whole column, or a
value on the way into the derived document.

Why this exists
----------------
On 2026-07-26, `docs/STRATEGY.md`'s gate summary table dropped "Peak" from
OCP-01's 45-55A setting, dropped the entire hysteresis column from OVP-01,
and dropped the falling/rising direction columns from UVL-01/UVL-02. Three
protection-gate fixes were designed against the lossy summary and were
wrong in ways that passed review -- see
`docs/solutions/best-practices/derived-documents-lose-qualifiers-2026-07-26.md`
and `docs/STRATEGY.md` "Recovered gate qualifiers invalidate three of
today's fixes". A fourth, related failure: STRATEGY.md's own audit table
marked OVP-01 "FIXED" in a row that a later section of the *same document*
showed was missing its required hysteresis network -- a stale verdict that
was never reconciled. This gate catches both shapes:

1. **Field-level drift** (`gates:` in the config): for every gate defined
   in `scripts/derived_doc_gates.yaml`, locate its defining row in the
   source document and its restatement in each configured derived
   document, then assert every `required_fields[].any_of` alternative
   (a qualifier word or a numeric value) survives into the derived row.
   Row-count or gate-ID-only comparisons cannot catch this class: the
   defect is a dropped column or a dropped word *inside* a cell.

2. **Stale-verdict drift** (`consistency_checks:` in the config): a row
   asserting a pass/fixed verdict that a documented, superseding finding
   already contradicts, with no acknowledgement in the same row.

Design choice: **verify, don't generate.** `docs/STRATEGY.md` is a living
narrative document (evidence links, running commentary, per-day sections)
that several people edit concurrently; forcing its gate table to be
machine-generated from `FUNCTIONAL_TEST_CRITERIA.md` would fight that use
and produce large, noisy diffs on a file that already changes every few
minutes today. The existing CI gates in this repo
(`scripts/import_linter_gate.py`, `scripts/check_vacuous_gates.py`) are
all verifiers, not generators, for the same reason: the repo's failure
mode is *lossy restatement*, not *structural divergence*, and a verifier
that reads both documents and asserts field-for-field correspondence
targets that directly without constraining how the summary is written.
Full reasoning: `docs/evidence/2026-07-26-derived-document-drift-gate.md`.

Self-validating config: every `required_fields[].any_of` list must have at
least one alternative found in the SOURCE row (header + data row text
combined, so a column-header concept like "Hysteresis" or "Falling"
counts even though the data cell itself is just a number). If none of a
field's alternatives can be found in the source any more, the config no
longer reflects the source document and the gate fails closed
(`tool_error`) rather than silently checking against a stale assumption.

Exit codes (mirrors `scripts/import_linter_gate.py`):
  0 - "clean": every configured gate located exactly once in the source
      and in every derived document that claims it, and every required
      field survived. Also 0 during the soft-launch window (see
      CUTOVER_DATE) when the only failures are drift, not tool errors.
  3 - "drift": at least one required field is missing from a derived
      document's restatement of a gate, or a stale verdict was found
      unmitigated. This is the gate's expected failure mode once the
      soft-launch window has closed.
  5 - "tool_error": the gate could not actually check anything --
      missing config, missing source or derived document, zero tables
      parsed, a gate row not found (or found more than once, which is
      just as unreliable) in the source or a derived document, or a
      config field whose value no longer appears in the source. Never
      conflated with "0 violations" -- see `_lib` docstrings on the
      sibling gates for the same principle.

Usage:
  uv run python scripts/check_derived_doc_drift.py [--config PATH]
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from rich.console import Console

from _lib.repo import find_repo_root
from _lib.github_summary import get_github_summary_path

console = Console()

# Soft launch, mirroring scripts/import_linter_gate.py's CUTOVER_DATE
# pattern: today's tree has at least one live drift finding (see the
# evidence doc). Rather than break CI the moment this gate merges, drift
# (not tool_error -- tool_error always blocks) prints as a warning and
# exits 0 until this date, then becomes merge-blocking.
CUTOVER_DATE = datetime.date(2026, 8, 2)


# ---------------------------------------------------------------------------
# normalization
# ---------------------------------------------------------------------------

_BOLD_RE = re.compile(r"\*\*")
_DASH_RE = re.compile(r"\s*[-–—]\s*")
_CMP_RE = re.compile(r"\s*([<>])\s*")
_DIGIT_UNIT_RE = re.compile(r"(\d)\s+(?=[A-Za-zµ°%Ω])")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Fold markdown/whitespace/dash variance so cell text is substring-comparable.

    "45 - 55 A" and "45-55A" both normalize to "45-55a". "< 1 µs" and
    "<1µs" both normalize to "<1µs". This is deliberately about
    *formatting* variance only -- it does not touch qualifier words, so
    "50A Peak" and "50A" remain distinguishable (the exact defect this
    gate exists to catch).
    """
    if not text:
        return ""
    t = _BOLD_RE.sub("", text)
    t = t.lower()
    t = _DASH_RE.sub("-", t)
    t = _CMP_RE.sub(r"\1", t)
    t = _DIGIT_UNIT_RE.sub(r"\1", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


# ---------------------------------------------------------------------------
# markdown pipe-table parsing
# ---------------------------------------------------------------------------


@dataclass
class Table:
    header: list[str]
    rows: list[list[str]]
    header_line: int  # 1-based source line number of the header row


_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def extract_tables(text: str) -> list[Table]:
    """Parse every pipe-table in *text*. Returns [] if none are found."""
    lines = text.splitlines()
    n = len(lines)
    tables: list[Table] = []
    i = 0
    while i < n:
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < n and _SEP_RE.match(lines[i + 1].strip()):
            header = _split_row(lines[i])
            j = i + 2
            rows = []
            while j < n and lines[j].strip().startswith("|"):
                rows.append(_split_row(lines[j]))
                j += 1
            tables.append(Table(header=header, rows=rows, header_line=i + 1))
            i = j
        else:
            i += 1
    return tables


def row_context(table: Table, row: list[str]) -> str:
    """Header + data row joined, so header-only concepts (e.g. a
    "Hysteresis" or "Recovery (Rising)" column header) are visible to
    token matching even when the cell itself is just a bare number."""
    return " | ".join(table.header) + " || " + " | ".join(row)


def find_rows_by_locator(
    tables: list[Table], locator: list[str], header_contains: list[str] | None = None
) -> list[tuple[Table, list[str]]]:
    """Rows where every *locator* substring appears in the normalized row context."""
    norm_locator = [normalize(s) for s in locator]
    norm_header_filter = [normalize(s) for s in header_contains] if header_contains else None
    matches = []
    for t in tables:
        if norm_header_filter is not None:
            header_text = normalize(" | ".join(t.header))
            if not all(h in header_text for h in norm_header_filter):
                continue
        for r in t.rows:
            ctx = normalize(row_context(t, r))
            if all(loc in ctx for loc in norm_locator):
                matches.append((t, r))
    return matches


def find_rows_by_exact_cell(
    tables: list[Table], value: str, header_contains: list[str] | None = None
) -> list[tuple[Table, list[str]]]:
    """Rows containing a cell that normalizes to exactly *value*."""
    norm_value = normalize(value)
    norm_header_filter = [normalize(s) for s in header_contains] if header_contains else None
    matches = []
    for t in tables:
        if norm_header_filter is not None:
            header_text = normalize(" | ".join(t.header))
            if not all(h in header_text for h in norm_header_filter):
                continue
        for r in t.rows:
            if any(normalize(cell) == norm_value for cell in r):
                matches.append((t, r))
    return matches


# ---------------------------------------------------------------------------
# result model
# ---------------------------------------------------------------------------


@dataclass
class ToolError:
    where: str
    reason: str


@dataclass
class Violation:
    doc: str
    gate: str
    field: str
    expected_any_of: list[str]
    source_hint: str
    kind: str = "missing_field"


@dataclass
class Report:
    tool_errors: list[ToolError] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    documents_inspected: set[str] = field(default_factory=set)
    tables_parsed: int = 0
    gate_rows_matched: int = 0
    fields_checked: int = 0


def _read_doc(repo_root: Path, rel_path: str, report: Report) -> str | None:
    report.documents_inspected.add(rel_path)
    p = repo_root / rel_path
    if not p.is_file():
        report.tool_errors.append(ToolError(rel_path, "document not found"))
        return None
    text = p.read_text()
    if not text.strip():
        report.tool_errors.append(ToolError(rel_path, "document is empty"))
        return None
    return text


def _parse_or_error(rel_path: str, text: str, report: Report) -> list[Table]:
    tables = extract_tables(text)
    report.tables_parsed += len(tables)
    if not tables:
        report.tool_errors.append(
            ToolError(rel_path, "zero pipe-tables parsed (unrecognized or empty format)")
        )
    return tables


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------


def check_source_self_validation(
    gates_cfg: dict, source_tables: list[Table], source_path: str, report: Report
) -> dict[str, str]:
    """Locate each gate's source row and confirm every required field's
    any_of has at least one alternative actually present in the source.

    Returns {gate_id: normalized_source_row_context} for gates that
    resolved cleanly (used only for diagnostics in violation messages).
    """
    resolved: dict[str, str] = {}
    for gate_id, gate_cfg in gates_cfg.items():
        locator = gate_cfg["source_row_locator"]
        matches = find_rows_by_locator(source_tables, locator)
        if len(matches) != 1:
            report.tool_errors.append(
                ToolError(
                    f"{source_path}:{gate_id}",
                    f"source row locator {locator!r} matched {len(matches)} rows (need exactly 1)",
                )
            )
            continue
        table, row = matches[0]
        report.gate_rows_matched += 1
        ctx = normalize(row_context(table, row))
        resolved[gate_id] = ctx
        for rf in gate_cfg["required_fields"]:
            report.fields_checked += 1
            if not any(normalize(alt) in ctx for alt in rf["any_of"]):
                report.tool_errors.append(
                    ToolError(
                        f"{source_path}:{gate_id}:{rf['name']}",
                        f"none of {rf['any_of']!r} found in source row -- config is stale "
                        "relative to the source document",
                    )
                )
    return resolved


def check_derived_document(
    doc_cfg: dict,
    gates_cfg: dict,
    repo_root: Path,
    report: Report,
    tables_cache: dict[str, list[Table]],
) -> None:
    doc_path = doc_cfg["path"]
    if doc_path not in tables_cache:
        text = _read_doc(repo_root, doc_path, report)
        if text is None:
            tables_cache[doc_path] = []
            return
        tables_cache[doc_path] = _parse_or_error(doc_path, text, report)
    tables = tables_cache[doc_path]
    if not tables:
        return  # already recorded as a tool_error

    header_contains = doc_cfg.get("header_contains")
    gate_ids = list(gates_cfg.keys()) if doc_cfg["gates"] == "all" else doc_cfg["gates"]

    for gate_id in gate_ids:
        if gate_id not in gates_cfg:
            report.tool_errors.append(
                ToolError(f"{doc_path}:{gate_id}", "gate not defined in config `gates:` section")
            )
            continue
        matches = find_rows_by_exact_cell(tables, gate_id, header_contains=header_contains)
        if len(matches) != 1:
            report.tool_errors.append(
                ToolError(
                    f"{doc_path}:{gate_id}",
                    f"gate row not found exactly once ({len(matches)} matches) -- "
                    "row deleted, renamed, or header_contains no longer matches the table",
                )
            )
            continue
        table, row = matches[0]
        report.gate_rows_matched += 1
        ctx = normalize(row_context(table, row))
        gate_cfg = gates_cfg[gate_id]
        for rf in gate_cfg["required_fields"]:
            report.fields_checked += 1
            if not any(normalize(alt) in ctx for alt in rf["any_of"]):
                report.violations.append(
                    Violation(
                        doc=doc_path,
                        gate=gate_id,
                        field=rf["name"],
                        expected_any_of=rf["any_of"],
                        source_hint=gate_cfg["source_row_locator"][0],
                    )
                )


def check_consistency(
    checks_cfg: list[dict], repo_root: Path, report: Report, tables_cache: dict[str, list[Table]]
) -> None:
    for check in checks_cfg:
        doc_path = check["doc"]
        if doc_path not in tables_cache:
            text = _read_doc(repo_root, doc_path, report)
            if text is None:
                tables_cache[doc_path] = []
                continue
            tables_cache[doc_path] = _parse_or_error(doc_path, text, report)
        tables = tables_cache[doc_path]
        if not tables:
            continue

        matches = find_rows_by_locator(tables, check["row_locator"])
        if len(matches) != 1:
            report.tool_errors.append(
                ToolError(
                    f"{doc_path}:{check['id']}",
                    f"row locator {check['row_locator']!r} matched {len(matches)} rows "
                    "(need exactly 1)",
                )
            )
            continue
        table, row = matches[0]
        report.gate_rows_matched += 1
        ctx = normalize(row_context(table, row))
        report.fields_checked += 1
        stale_present = all(normalize(t) in ctx for t in check["stale_tokens"])
        mitigated = any(normalize(t) in ctx for t in check["required_mitigating_tokens"])
        if stale_present and not mitigated:
            report.violations.append(
                Violation(
                    doc=doc_path,
                    gate=check["gate"],
                    field=check["id"],
                    expected_any_of=check["required_mitigating_tokens"],
                    source_hint=check["message"],
                    kind="stale_verdict",
                )
            )


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def run(config_path: Path, repo_root: Path) -> tuple[str, Report]:
    """Returns (state, report) where state is 'clean' | 'drift' | 'tool_error'."""
    report = Report()

    if not config_path.is_file():
        report.tool_errors.append(ToolError(str(config_path), "config file not found"))
        return "tool_error", report

    try:
        cfg = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as exc:
        report.tool_errors.append(ToolError(str(config_path), f"YAML parse error: {exc}"))
        return "tool_error", report

    if not cfg or not isinstance(cfg, dict):
        report.tool_errors.append(ToolError(str(config_path), "config is empty or not a mapping"))
        return "tool_error", report

    gates_cfg = cfg.get("gates") or {}
    derived_docs_cfg = cfg.get("derived_documents") or []
    source_path = cfg.get("source_document")
    consistency_cfg = cfg.get("consistency_checks") or []

    if not gates_cfg:
        report.tool_errors.append(ToolError(str(config_path), "zero gates configured"))
    if not derived_docs_cfg:
        report.tool_errors.append(ToolError(str(config_path), "zero derived_documents configured"))
    if not source_path:
        report.tool_errors.append(ToolError(str(config_path), "no source_document configured"))

    if not gates_cfg or not derived_docs_cfg or not source_path:
        return "tool_error", report

    source_text = _read_doc(repo_root, source_path, report)
    tables_cache: dict[str, list[Table]] = {}
    if source_text is not None:
        source_tables = _parse_or_error(source_path, source_text, report)
        tables_cache[source_path] = source_tables
        if source_tables:
            check_source_self_validation(gates_cfg, source_tables, source_path, report)

    for doc_cfg in derived_docs_cfg:
        check_derived_document(doc_cfg, gates_cfg, repo_root, report, tables_cache)

    if consistency_cfg:
        check_consistency(consistency_cfg, repo_root, report, tables_cache)

    # Anti-vacuity backstop: even if nothing above tripped, a run that
    # inspected zero fields checked nothing and must not report clean.
    if report.fields_checked == 0 and not report.tool_errors:
        report.tool_errors.append(
            ToolError("<run>", "0 fields were checked -- vacuous run, not a clean pass")
        )

    if report.tool_errors:
        return "tool_error", report
    if report.violations:
        return "drift", report
    return "clean", report


def _print_report(state: str, report: Report) -> None:
    console.print(
        f"[bold]Derived-document drift gate[/] -- "
        f"{len(report.documents_inspected)} document(s), "
        f"{report.tables_parsed} table(s) parsed, "
        f"{report.gate_rows_matched} gate row(s) matched, "
        f"{report.fields_checked} field(s) checked"
    )
    for d in sorted(report.documents_inspected):
        console.print(f"  - {d}")

    if report.tool_errors:
        console.print(f"[red bold]{len(report.tool_errors)} TOOL ERROR(S)[/]")
        for e in report.tool_errors:
            console.print(f"  [red]TOOL_ERROR[/] {e.where}: {e.reason}")

    if report.violations:
        console.print(f"[red bold]{len(report.violations)} DRIFT VIOLATION(S)[/]")
        for v in report.violations:
            if v.kind == "stale_verdict":
                console.print(
                    f"  [red]DRIFT[/] {v.doc} :: {v.gate} :: {v.field} -- {v.source_hint}"
                )
            else:
                console.print(
                    f"  [red]DRIFT[/] {v.doc} :: gate {v.gate} :: field '{v.field}' -- "
                    f"none of {v.expected_any_of!r} found "
                    f"(source: {v.source_hint!r})"
                )

    if state == "clean":
        console.print("[green]Derived-document drift gate passed[/]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to derived_doc_gates.yaml (default: scripts/derived_doc_gates.yaml)",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    config_path = args.config or (repo_root / "scripts" / "derived_doc_gates.yaml")

    state, report = run(config_path, repo_root)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Derived-document drift gate: {state}\n")
            f.write(
                f"- Documents inspected: {len(report.documents_inspected)}\n"
                f"- Tables parsed: {report.tables_parsed}\n"
                f"- Gate rows matched: {report.gate_rows_matched}\n"
                f"- Fields checked: {report.fields_checked}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
                f"- Drift violations: {len(report.violations)}\n"
            )

    if state == "tool_error":
        sys.exit(5)
    if state == "drift":
        if datetime.date.today() < CUTOVER_DATE:
            console.print(
                f"[yellow]WARNING-only until {CUTOVER_DATE.isoformat()} "
                "(soft launch) -- exiting 0 despite drift above.[/]"
            )
            sys.exit(0)
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
