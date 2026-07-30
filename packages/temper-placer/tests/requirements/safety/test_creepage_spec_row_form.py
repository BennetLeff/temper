"""Regression gate: the creepage table in
``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 5.1 must state its Working
Voltage rows as IEC 60335-1 Table 17's own bounded ranges (e.g. ``>250,
<=400``), never as bare discrete-point labels (e.g. ``300``, ``400``).

Why this exists
----------------
PR #442 read a Sec 5.1 transcription that used invented, round-number
"rows" -- ``50``/``100``/``150``/``200``/``300``/``400``/``600`` -- each one
silently standing in for a real Table 17 range's own upper (or a nearby)
bound, with the range notation itself dropped. Reading a 400V working
voltage against a table shaped that way makes "round up to the next row"
look like the only available rule, and produces the wrong row: DC_BUS's
400V was read off the label "400" (which happened to carry row v's real
figures, ">400V and <=500V": 5.0mm basic / 10.0mm reinforced at PD2) instead
of row iv (">250V and <=400V": 4.0mm basic / 8.0mm reinforced at PD2), the
row 400V actually, literally falls in once the table's real range form is
restored. See ``docs/evidence/2026-07-30-pd2-creepage-row-determination.md``
for the full derivation, including a legible primary-text page render
confirming Table 17's rows are genuinely continuous, non-overlapping
ranges, not discrete points.

This test parses the live spec document (not a frozen copy) and fails if
Sec 5.1's Working Voltage column ever drifts back to a discrete-point
label, independent of what the enforced mm values happen to be at the time
(this repo's operative pollution degree and its mm figures have changed at
least twice already -- PD2/10.0mm -> PD2/8.0mm-corrected -> PD3/12.6mm --
and will likely change again; the row *form* is the invariant worth
protecting, not any one snapshot of the numbers).

Why this is a standalone test, not a ``scripts/check_derived_doc_drift.py``
config entry
-------------------------------------------------------------------------
That gate's model is "a named gate (e.g. ``OCP-01``) restated from an
in-repo source-of-truth document (``docs/FUNCTIONAL_TEST_CRITERIA.md``)
into one or more derived summary documents, checking that specific
qualifier words/columns survive the restatement." Neither half of that
model fits here: (1) there is no in-repo source-of-truth document to diff
against -- the source is IEC 60335-1/IS 302-1 itself, an external,
paywalled standard this repo cannot commit a machine-readable copy of
(the same caveat this project's prior creepage evidence docs already carry
repeatedly); (2) Table 17's rows are keyed by voltage range, not by a
named gate ID like ``OCP-01``, so ``check_derived_doc_drift.py``'s
row-locator-by-gate-ID matching has nothing to anchor to. A single-document,
regex-shaped structural check (this file) is the cheap, targeted fit; a new
source-vs-derived config entry would be reshaping a different problem to
fit a tool built for it, not for this one.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SPEC_PATH = _REPO_ROOT / "docs" / "specs" / "HIGH_VOLTAGE_CLEARANCE_SPEC.md"

# A Table 17 "Working Voltage" cell must express a bounded range using the
# standard's own comparison operators: "<=NNN" (or "≤NNN", the unicode
# glyph) for the first row (implicit lower bound 0), or ">NNN, <=NNN" (or
# the unicode form) for every subsequent row. A bare integer with no
# operator at all -- e.g. "300" -- is exactly the defect class that caused
# PR #442's row-selection error; fail closed on it.
_LE = r"(?:≤|<=)"
_RANGE_CELL_RE = re.compile(rf"^{_LE}\s*\d+$|^>\s*\d+\s*,\s*{_LE}\s*\d+$")

_SECTION_RE = re.compile(r"### 5\.1 Creepage Table.*?(?=\n#{2,3} |\Z)", re.S)


def _creepage_table_working_voltage_cells() -> list[str]:
    text = _SPEC_PATH.read_text(encoding="utf-8")
    m = _SECTION_RE.search(text)
    assert m, (
        "could not locate a '### 5.1 Creepage Table' section in "
        f"{_SPEC_PATH} -- has it been renamed or restructured?"
    )
    section = m.group(0)
    # Grab the markdown pipe table's rows; skip the header and the
    # ``|---|---|`` separator line, keep only data rows.
    table_lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    assert len(table_lines) >= 3, (
        f"no markdown pipe table with >=1 data row found under Sec 5.1 of {_SPEC_PATH}"
    )
    data_rows = table_lines[2:]
    cells = []
    for row in data_rows:
        first_cell = row.strip().strip("|").split("|")[0].strip()
        cells.append(first_cell.replace("**", ""))
    return cells


def test_spec_doc_is_present_and_parseable():
    """Falsifier: if the spec doc moved or the section header changed, the
    real check below would vacuously pass by finding zero rows. Assert a
    plausible-sized table was actually found."""
    cells = _creepage_table_working_voltage_cells()
    assert len(cells) >= 5, (
        f"expected at least 5 Table 17 rows under Sec 5.1, found {len(cells)}: {cells!r} "
        "-- the section may have been truncated or the table replaced with something "
        "this parser can no longer see (which would make the row-form check below "
        "vacuous, not passing)."
    )


def test_creepage_table_rows_are_bounded_ranges_not_discrete_points():
    """The regression this file exists for: every Working Voltage cell must
    be a real Table 17 range (">NNN, <=NNN" or "<=NNN"), never a bare
    number standing in for one."""
    cells = _creepage_table_working_voltage_cells()
    bad = [c for c in cells if not _RANGE_CELL_RE.match(c)]
    assert not bad, (
        "docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md Sec 5.1's creepage table has "
        f"Working Voltage cell(s) not expressed as a bounded range: {bad!r} (all cells: "
        f"{cells!r}). This is exactly the defect class that caused PR #442's "
        "row-selection error (a discrete-point label silently standing in for a "
        "range's own upper bound, making '400V' ambiguous between row iv's real "
        "endpoint and row v's) -- see "
        "docs/evidence/2026-07-30-pd2-creepage-row-determination.md."
    )


def test_row_iv_is_present_with_its_real_boundary():
    """Falsifier for a subtler drift: the table could satisfy the two tests
    above (every cell IS a well-formed range) while still silently losing
    the specific row iv boundary (">250, <=400") that this design's
    340-400V boundaries actually fall in -- e.g. if a future edit
    renumbered or merged rows. Pin it directly."""
    cells = _creepage_table_working_voltage_cells()
    normalized = [c.replace(" ", "").replace("≤", "<=") for c in cells]
    assert ">250,<=400" in normalized, (
        f"row iv (>250V, <=400V) -- the row this design's MAINS/DC_BUS/Gate-Drive-"
        f"Isolated boundaries (340V, 400V, 355V) actually fall in -- is missing from "
        f"Sec 5.1's table: {cells!r}"
    )
