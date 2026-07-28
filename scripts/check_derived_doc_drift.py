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

3. **Board-fact drift** (`board_facts:` in the config): a number that
   `docs/STRATEGY.md` asserts about the committed board, compared against
   `pcb/temper.kicad_pcb` measured structurally. On 2026-07-27 the board
   was routed (`556ccf4f`, 2,338 segments) and the document went on saying
   "The committed board carries no routing: 0 segments, 0 vias, 0 zones" --
   true when written, and nothing re-checked it. The taxonomy in
   `docs/evidence/2026-07-27-failure-mechanism-taxonomy.md` proposes this
   as a seventh METHODOLOGY §4 class: *stale record -- ground truth changed
   and the record that claims to track it didn't*.

4. **Stale board prose** (`stale_board_claims:` in the config): the
   negative counterpart to 3. This document deliberately keeps superseded
   measurements, because its value is the record of how state moved; a
   retained passage must carry a supersession marker so it cannot be read
   as current.

Locating a board claim: by an HTML-comment anchor plus an exact table row
label -- never by matching the surrounding prose. A prose regex stops
matching after a harmless reword, which is silent, and that failure *is*
the bug this arm exists to prevent. Anchor missing or duplicated, row
renamed, value unparseable, a table row nobody configured, and an
unreadable PCB are all tool_error. Granularity for arm 4 is the single
list item / table row / paragraph, not the blank-line block: at block
granularity a sibling bullet's date masked the stale one (found by
falsification -- see the tests).

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
      document's restatement of a gate, a stale verdict was found
      unmitigated, a board fact disagrees with `pcb/temper.kicad_pcb`, or
      a retained board claim lacks its supersession marker. For the
      `gates:` arm this is merge-blocking only once the soft-launch window
      closes; **board-fact violations are never soft-launched** and always
      exit 3. That arm merged against an already-reconciled tree, so it has
      nothing to grandfather, and a warn-only board check would itself be
      the "reports false" failure it exists to catch.
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
from _lib.github_summary import get_github_summary_path
from _lib.repo import find_repo_root
from rich.console import Console

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
    if not norm_locator:
        # locator comes straight from config (gate_cfg["source_row_locator"]
        # or check["row_locator"]) with no schema-level minimum-length
        # check. An empty locator would make the all() below vacuously
        # True for every row in every table -- silently "matching" without
        # checking any actual content, which is exactly the drift-masking
        # failure mode this gate exists to catch. Fail closed instead.
        raise ValueError(
            "find_rows_by_locator: locator must be non-empty -- an empty "
            "locator vacuously matches every row"
        )
    norm_header_filter = [normalize(s) for s in header_contains] if header_contains else None
    matches = []
    for t in tables:
        if norm_header_filter is not None:
            # norm_header_filter can only be non-None here when
            # header_contains was itself truthy (see the ternary above: an
            # empty list is falsy, so header_contains=[] yields None, never
            # a non-None empty list) -- and a list comprehension preserves
            # length, so norm_header_filter is always non-empty whenever
            # this branch runs. Safe by construction; asserted, not
            # rewritten.
            assert norm_header_filter
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
            # Same invariant as find_rows_by_locator above: norm_header_filter
            # is non-None only when header_contains was truthy, and the
            # comprehension preserves length -- so it is always non-empty
            # whenever this branch runs. Safe by construction.
            assert norm_header_filter
            header_text = normalize(" | ".join(t.header))
            if not all(h in header_text for h in norm_header_filter):
                continue
        for r in t.rows:
            if any(normalize(cell) == norm_value for cell in r):
                matches.append((t, r))
    return matches


# ---------------------------------------------------------------------------
# board facts: pcb/temper.kicad_pcb as the source of truth
# ---------------------------------------------------------------------------

_SEXP_TOKEN_RE = re.compile(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)")
_CU_LAYER_RE = re.compile(r'^\s*\(\d+\s+"([^"]+\.Cu)"', re.M)

# Metric name -> the top-level s-expression token whose occurrences it counts.
# "Top-level" means a direct child of the root `(kicad_pcb ...)` node, i.e.
# paren depth 2. This is the whole point of the parser below: a naive
# `(net ` scan over the file text returns ~3,160 on the current board
# because every pad, segment, via and zone carries a net *reference*, while
# only 164 are net *declarations*. Counting references as declarations is
# the exact error this gate exists to prevent, so the measurement is done
# structurally rather than by text match.
_TOP_LEVEL_METRICS = {
    "footprints": "footprint",
    "nets": "net",
    "segments": "segment",
    "vias": "via",
    "zones": "zone",
}
# Metrics that are not a top-level count and need their own derivation.
_DERIVED_METRICS = ("copper_layers",)

KNOWN_BOARD_METRICS: tuple[str, ...] = tuple(_TOP_LEVEL_METRICS) + _DERIVED_METRICS


def measure_board(pcb_text: str) -> dict[str, int]:
    """Structurally measure a KiCad `.kicad_pcb` file.

    Walks the s-expression tracking paren depth and string state, so
    parentheses and tokens inside quoted strings (net names, property
    values, footprint descriptions) cannot be miscounted. Returns a dict
    keyed by the names in `KNOWN_BOARD_METRICS`.

    Deliberately does not depend on indentation: KiCad's own writer and
    `kiutils` disagree about leading whitespace, and an indentation-keyed
    regex would silently start counting zero after a reformat.
    """
    counts = dict.fromkeys(_TOP_LEVEL_METRICS, 0)
    token_for_depth2 = {tok: name for name, tok in _TOP_LEVEL_METRICS.items()}

    layers_spans: list[tuple[int, int]] = []
    depth = 0
    i = 0
    n = len(pcb_text)
    in_str = False
    layers_start: int | None = None
    layers_depth = -1

    while i < n:
        c = pcb_text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "(":
            depth += 1
            if depth == 2:
                m = _SEXP_TOKEN_RE.match(pcb_text, i)
                if m:
                    tok = m.group(1)
                    if tok in token_for_depth2:
                        counts[token_for_depth2[tok]] += 1
                    elif tok == "layers":
                        layers_start = i
                        layers_depth = depth
            i += 1
            continue
        if c == ")":
            if layers_start is not None and depth == layers_depth:
                layers_spans.append((layers_start, i))
                layers_start = None
                layers_depth = -1
            depth -= 1
            i += 1
            continue
        i += 1

    # Copper layers: entries of the board's top-level `(layers ...)` stack
    # whose canonical name ends in `.Cu` (F.Cu, In1.Cu, In2.Cu, B.Cu).
    copper = 0
    for start, end in layers_spans:
        copper += len(set(_CU_LAYER_RE.findall(pcb_text[start:end])))
    counts["copper_layers"] = copper
    return counts


_INT_CELL_RE = re.compile(r"^-?[\d,]+$")


def parse_claimed_int(cell: str) -> int | None:
    """Parse a table cell like ``**2,338**`` into ``2338``.

    Returns None if the cell is not a plain integer, which the caller
    turns into a tool_error -- an unparseable claim is an unverifiable
    claim, never a pass.
    """
    t = _BOLD_RE.sub("", cell).strip()
    t = t.replace("`", "").strip()
    if not _INT_CELL_RE.match(t):
        return None
    try:
        return int(t.replace(",", ""))
    except ValueError:
        return None


def find_anchored_table(text: str, anchor: str) -> tuple[Table | None, str | None]:
    """Locate the pipe-table introduced by a unique HTML-comment *anchor*.

    Returns (table, None) on success or (None, reason) on failure.

    This is the anti-fail-open mechanism. The claims being gated live in
    prose-heavy narrative, and a regex that pattern-matches the sentence
    around a number stops matching the moment somebody rewords the
    sentence -- which is silent, and recreates exactly the staleness bug
    this check was written for (the doc asserted "no routing: 0 segments,
    0 vias, 0 zones" for a board that had carried 2,338 segments since
    2026-07-27). Binding to an explicit anchor inverts that: the anchor
    going missing, appearing twice, or no longer introducing a table is
    itself an error, so the check cannot quietly stop checking.
    """
    occurrences = [m.start() for m in re.finditer(re.escape(anchor), text)]
    if len(occurrences) != 1:
        return None, (
            f"anchor {anchor!r} found {len(occurrences)} times (need exactly 1) -- "
            "the board-facts table was renamed, duplicated, or deleted"
        )
    anchor_line = text.count("\n", 0, occurrences[0])
    for table in extract_tables(text):
        # header_line is 1-based; the table must follow the anchor closely
        # enough that it is unambiguously the anchored one.
        delta = (table.header_line - 1) - anchor_line
        if 0 < delta <= 6:
            return table, None
    return None, (
        f"anchor {anchor!r} is not followed by a pipe-table within 6 lines -- "
        "the table was deleted or moved away from its anchor"
    )


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
    remedy: str = ""


@dataclass
class Report:
    tool_errors: list[ToolError] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    documents_inspected: set[str] = field(default_factory=set)
    tables_parsed: int = 0
    gate_rows_matched: int = 0
    fields_checked: int = 0
    board_facts_checked: int = 0
    board_measured: dict[str, int] = field(default_factory=dict)

    def board_violations(self) -> list[Violation]:
        """Board-fact violations never enter the soft-launch window."""
        return [v for v in self.violations if v.kind in ("board_fact", "stale_board_claim")]


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
        stale_tokens = check["stale_tokens"]
        if not stale_tokens:
            # stale_tokens comes straight from config with no schema-level
            # minimum-length check. An empty list would make the all()
            # below vacuously True -- every row would be reported as
            # containing a "stale" claim regardless of its actual content,
            # which inverts this check's purpose. Fail closed instead of
            # silently mis-scoring every row.
            raise ValueError(
                f"consistency check {check['id']!r}: stale_tokens must be "
                "non-empty -- an empty list vacuously marks every row stale"
            )
        stale_present = all(normalize(t) in ctx for t in stale_tokens)
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


def check_board_facts(cfg: dict, repo_root: Path, report: Report) -> None:
    """Compare every claimed board fact in the doc against the .kicad_pcb.

    Fails closed at every step: a missing PCB, a missing/duplicated anchor,
    a row that cannot be located, a row nobody configured, and an
    unparseable number are all `tool_error`, never a silent pass.
    """
    pcb_rel = cfg["pcb"]
    doc_rel = cfg["doc"]
    anchor = cfg["anchor"]
    rows_cfg = cfg.get("rows") or {}

    if not rows_cfg:
        report.tool_errors.append(ToolError("board_facts", "zero rows configured"))
        return

    unknown = [m for m in rows_cfg if m not in KNOWN_BOARD_METRICS]
    if unknown:
        report.tool_errors.append(
            ToolError(
                "board_facts",
                f"unknown metric(s) {unknown!r} -- known metrics are {list(KNOWN_BOARD_METRICS)!r}",
            )
        )
        return

    pcb_path = repo_root / pcb_rel
    if not pcb_path.is_file():
        report.tool_errors.append(ToolError(pcb_rel, "PCB source of truth not found"))
        return
    pcb_text = pcb_path.read_text()
    if not pcb_text.strip():
        report.tool_errors.append(ToolError(pcb_rel, "PCB source of truth is empty"))
        return

    measured = measure_board(pcb_text)
    report.board_measured = measured

    # Anti-vacuity on the measurement itself: a board with zero footprints
    # means the parser did not understand the file. Treat it as a broken
    # tool, not as a board that legitimately has nothing on it.
    if measured.get("footprints", 0) == 0:
        report.tool_errors.append(
            ToolError(
                pcb_rel,
                "parsed 0 top-level footprints -- the file is not a recognizable "
                "kicad_pcb or the parser is broken; refusing to compare against it",
            )
        )
        return

    doc_text = _read_doc(repo_root, doc_rel, report)
    if doc_text is None:
        return

    table, reason = find_anchored_table(doc_text, anchor)
    if table is None:
        report.tool_errors.append(ToolError(f"{doc_rel}:{anchor}", reason or "table not found"))
        return
    report.tables_parsed += 1

    # Map each configured metric to its row, requiring exactly one match.
    label_to_metric = {normalize(c["label"]): m for m, c in rows_cfg.items()}
    matched_rows: set[int] = set()

    for metric, row_cfg in rows_cfg.items():
        label = row_cfg["label"]
        norm_label = normalize(label)
        hits = [idx for idx, r in enumerate(table.rows) if r and normalize(r[0]) == norm_label]
        if len(hits) != 1:
            report.tool_errors.append(
                ToolError(
                    f"{doc_rel}:board_facts:{metric}",
                    f"row labelled {label!r} found {len(hits)} times in the "
                    "board-facts table (need exactly 1) -- the row was renamed or "
                    "removed, so its claim can no longer be checked",
                )
            )
            continue
        idx = hits[0]
        matched_rows.add(idx)
        row = table.rows[idx]
        if len(row) < 2:
            report.tool_errors.append(
                ToolError(
                    f"{doc_rel}:board_facts:{metric}",
                    f"row {label!r} has no value column",
                )
            )
            continue
        claimed = parse_claimed_int(row[1])
        if claimed is None:
            report.tool_errors.append(
                ToolError(
                    f"{doc_rel}:board_facts:{metric}",
                    f"row {label!r} value {row[1]!r} is not a plain integer -- "
                    "an unparseable claim cannot be verified",
                )
            )
            continue

        report.board_facts_checked += 1
        actual = measured[metric]
        if claimed != actual:
            report.violations.append(
                Violation(
                    doc=doc_rel,
                    gate="board_facts",
                    field=metric,
                    expected_any_of=[f"{actual:,}"],
                    source_hint=(
                        f"{doc_rel} row {label!r} claims {claimed:,}; {pcb_rel} measures {actual:,}"
                    ),
                    kind="board_fact",
                    remedy=(
                        f"set the '{label}' row of the board-facts table in {doc_rel} "
                        f"to {actual:,} (the measured value), or explain the change. "
                        f"Do not edit {pcb_rel} to match the doc."
                    ),
                )
            )

    # Every row in the anchored table must be gated. Otherwise a new,
    # unconfigured board claim could be added to the table and go
    # unchecked forever -- a fresh instance of the same staleness bug.
    for idx, row in enumerate(table.rows):
        if idx in matched_rows or not row or not row[0].strip():
            continue
        if normalize(row[0]) in label_to_metric:
            continue
        report.tool_errors.append(
            ToolError(
                f"{doc_rel}:board_facts",
                f"table row {row[0]!r} is not configured under `board_facts.rows` -- "
                "every claim in this table must be gated; add it to "
                "scripts/derived_doc_gates.yaml or remove the row",
            )
        )


_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def _claim_units(text: str) -> list[tuple[int, str]]:
    """Split *text* into independently-assessable claim units.

    A unit is (1-based start line, text). Units are:

    * each markdown list item, together with its indented continuation
      lines;
    * each pipe-table row;
    * otherwise, each blank-line-separated prose paragraph.

    Granularity is the whole correctness argument here, and paragraphs
    alone are too coarse. The original defect --
    "The committed board carries no routing: 0 segments, 0 vias, 0 zones"
    -- sits in a tight bullet list with no blank lines between items, so
    at paragraph granularity a *sibling* bullet's "as of 2026-07-25"
    counted as that bullet's own supersession marker and the stale claim
    passed. Verified by falsification before this function was rewritten.
    Sibling rows of a table can mask each other the same way.
    """
    units: list[tuple[int, str]] = []
    current: list[str] = []
    start = 1

    def flush() -> None:
        nonlocal current
        if current:
            units.append((start, "\n".join(current)))
            current = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        # A table row and a new list item each begin a fresh unit; an
        # indented non-marker line continues the current one.
        if stripped.startswith("|") or _LIST_MARKER_RE.match(line):
            flush()
            start = lineno
            current = [line]
            continue
        if not current:
            start = lineno
        current.append(line)
    flush()
    return units


def check_stale_board_claims(checks_cfg: list[dict], repo_root: Path, report: Report) -> None:
    """Guard the doc's *historical* board claims against reading as current.

    The board-facts table above is the positive check. This is the negative
    one: passages that assert an obsolete board state (e.g. "entirely
    unrouted") must carry an explicit supersession marker in the same
    claim unit (bullet, table row, or paragraph), so a reader landing on them
    cannot mistake history for the
    present.

    Fail-closed property: each configured check must match at least one
    claim unit. If the prose it guards is reworded or deleted, the pattern
    stops matching and that is a `tool_error`, not a quiet pass -- the same
    self-validating-config rule the gate applies to `gates:`.
    """
    for check in checks_cfg:
        doc_rel = check["doc"]
        patterns = check.get("patterns") or []
        mitigating = check.get("required_mitigating_tokens") or []
        if not patterns:
            report.tool_errors.append(
                ToolError(f"{doc_rel}:{check['id']}", "patterns must be non-empty")
            )
            continue
        if not mitigating:
            report.tool_errors.append(
                ToolError(
                    f"{doc_rel}:{check['id']}",
                    "required_mitigating_tokens must be non-empty -- an empty list "
                    "would mark every matching claim unit as acceptable",
                )
            )
            continue

        text = _read_doc(repo_root, doc_rel, report)
        if text is None:
            continue

        norm_patterns = [normalize(p) for p in patterns]
        norm_mitigating = [normalize(m) for m in mitigating]
        total_hits = 0

        for start_line, block in _claim_units(text):
            norm_block = normalize(block)
            if not any(p in norm_block for p in norm_patterns):
                continue
            total_hits += 1
            report.fields_checked += 1
            if any(m in norm_block for m in norm_mitigating):
                continue
            report.violations.append(
                Violation(
                    doc=f"{doc_rel}:{start_line}",
                    gate="stale_board_claim",
                    field=check["id"],
                    expected_any_of=mitigating,
                    source_hint=check.get("message", ""),
                    kind="stale_board_claim",
                    remedy=(
                        f"the claim at {doc_rel}:{start_line} asserts an obsolete "
                        "board state with no supersession marker; date it and add one "
                        f"of {mitigating!r}"
                    ),
                )
            )

        if total_hits == 0:
            report.tool_errors.append(
                ToolError(
                    f"{doc_rel}:{check['id']}",
                    f"none of the patterns {patterns!r} matched any claim unit -- the "
                    "guarded passage was reworded or deleted, so this check is no "
                    "longer verifying anything; update scripts/derived_doc_gates.yaml",
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
    board_facts_cfg = cfg.get("board_facts") or {}
    stale_board_cfg = cfg.get("stale_board_claims") or []

    if not board_facts_cfg:
        report.tool_errors.append(
            ToolError(str(config_path), "no `board_facts:` section configured")
        )
    if not stale_board_cfg:
        report.tool_errors.append(
            ToolError(str(config_path), "no `stale_board_claims:` section configured")
        )

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
    try:
        if source_text is not None:
            source_tables = _parse_or_error(source_path, source_text, report)
            tables_cache[source_path] = source_tables
            if source_tables:
                check_source_self_validation(gates_cfg, source_tables, source_path, report)

        for doc_cfg in derived_docs_cfg:
            check_derived_document(doc_cfg, gates_cfg, repo_root, report, tables_cache)

        if consistency_cfg:
            check_consistency(consistency_cfg, repo_root, report, tables_cache)

        if board_facts_cfg:
            check_board_facts(board_facts_cfg, repo_root, report)
        if stale_board_cfg:
            check_stale_board_claims(stale_board_cfg, repo_root, report)
    except ValueError as exc:
        # A malformed config entry (e.g. an empty locator or empty
        # stale_tokens list -- see find_rows_by_locator and
        # check_consistency) raises ValueError rather than silently
        # mis-scoring; converted to a tool_error here so this stays within
        # the documented 0/3/5 exit-code contract instead of an
        # undocumented bare-crash exit code.
        report.tool_errors.append(ToolError(str(config_path), str(exc)))

    # Anti-vacuity backstop: even if nothing above tripped, a run that
    # inspected zero fields checked nothing and must not report clean.
    if report.fields_checked == 0 and not report.tool_errors:
        report.tool_errors.append(
            ToolError("<run>", "0 fields were checked -- vacuous run, not a clean pass")
        )
    # Same rule, applied independently to the board-fact arm: the gate arms
    # are separately vacuous-able, so a run where the doc/PCB comparison
    # checked nothing must not be absorbed by a healthy `gates:` arm.
    if board_facts_cfg and report.board_facts_checked == 0 and not report.tool_errors:
        report.tool_errors.append(
            ToolError(
                "<run>",
                "0 board facts were checked against the PCB -- vacuous run, not a clean pass",
            )
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
        f"{report.fields_checked} field(s) checked, "
        f"{report.board_facts_checked} board fact(s) checked"
    )
    for d in sorted(report.documents_inspected):
        console.print(f"  - {d}")
    if report.board_measured:
        measured = ", ".join(f"{k}={v:,}" for k, v in sorted(report.board_measured.items()))
        console.print(f"  measured from PCB: {measured}")

    if report.tool_errors:
        console.print(f"[red bold]{len(report.tool_errors)} TOOL ERROR(S)[/]")
        for e in report.tool_errors:
            console.print(f"  [red]TOOL_ERROR[/] {e.where}: {e.reason}")

    if report.violations:
        console.print(f"[red bold]{len(report.violations)} DRIFT VIOLATION(S)[/]")
        for v in report.violations:
            if v.kind == "board_fact":
                console.print(
                    f"  [red]BOARD DRIFT[/] {v.doc} :: {v.field} -- {v.source_hint}\n"
                    f"      fix: {v.remedy}"
                )
            elif v.kind == "stale_board_claim":
                console.print(
                    f"  [red]STALE BOARD CLAIM[/] {v.doc} :: {v.field} -- "
                    f"{v.source_hint}\n      fix: {v.remedy}"
                )
            elif v.kind == "stale_verdict":
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
        # Board-fact drift is NEVER soft-launched. The `gates:` arm has a
        # bring-up window because the tree carried known drift when that arm
        # merged; the board arm merged with the tree already reconciled, so
        # it has nothing to grandfather and fails closed from day one. A
        # warn-only board check would be precisely the "reports false"
        # failure it exists to prevent.
        board = report.board_violations()
        if board:
            console.print(
                f"[red bold]{len(board)} board-fact violation(s) -- "
                "fail-closed, not covered by the soft-launch window.[/]"
            )
            sys.exit(3)
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
