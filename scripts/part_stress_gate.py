#!/usr/bin/env python3
"""Part stress gate: applied stress vs. absolute-maximum rating, per part.

Motivation (docs/hardware/PART_STRESS_AUDIT.md, 2026-08-07): STRATEGY.md
names "part stress vs. abs-max" as a netlist-stage check that is
safety-critical and was, before that audit, entirely absent. The project
had already been bitten by exactly this class, found only by manual
inspection: the DC-bus electrolytic capacitors fail their datasheet ripple
rating by ~5x (docs/evidence/2026-07-26-bus-capacitor-ripple.md). That was
one part, found by luck. This gate makes the check re-runnable so the next
one is not.

This is a DATA-driven check, deliberately: scripts/part_stress_limits.yaml
holds every rated/applied figure and its datasheet or evidence-doc source;
this script contains no part-specific numbers at all, so a part swap or a
re-derived stress figure only requires editing the YAML (see that file's
own header for the schema and docs/hardware/PART_STRESS_AUDIT.md Sec 7 for
why this split matters). A checker encoding a misunderstanding is worse
than none -- the analysis backing every entry lives in the audit doc, not
here.

What this gate checks, per entry in the limits file:
  1. Every designator listed still exists in elec/build/default.csv.
  2. If `mpn` is set (not null), every one of those designators still
     carries that MPN in the current BOM -- a silent part swap invalidates
     a previously-computed rating/stress pair, and this must fail closed
     rather than silently comparing a stale number against a different
     physical part.
  3. margin = (rated - applied) / rated. Classified:
       FAIL  margin < 0           -- at or over the datasheet rating
       WARN  0 <= margin < guideline_margin -- under the part's own
             rating but below this project's derating guideline
       OK    margin >= guideline_margin
     `conditional: true` entries are reported as FAIL(conditional) /
     WARN(conditional) -- the underlying arithmetic is the same, but the
     applied-stress figure rests on an assumption this repo could not
     independently confirm (see the entry's `notes`), so it must never be
     silently merged into the same bucket as a directly-measured finding.

Exit codes:
  0 - OK: every entry is OK or WARN (guideline advisories do not fail the
      gate -- they are not the hard limit).
  3 - stress_violation: at least one entry is FAIL (margin < 0, at or over
      its rated limit), unconditional or conditional.
  5 - tool_error: missing/unparseable BOM or limits file, a designator
      absent from the BOM, or an MPN mismatch against the current board.
      Never treated as "0 violations" -- same fail-closed convention as
      scripts/capacity_budget_gate.py.

Usage:
  uv run python scripts/part_stress_gate.py [--help]
  uv run python scripts/part_stress_gate.py --bom PATH --limits PATH
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_BOM = REPO_ROOT / "elec" / "build" / "default.csv"
DEFAULT_LIMITS = REPO_ROOT / "scripts" / "part_stress_limits.yaml"


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass
class Entry:
    id: str
    designators: list[str]
    mpn: str | None
    domain: str
    unit: str
    rated: float
    applied: float
    guideline_margin: float
    conditional: bool
    source: str
    notes: str
    margin: float = field(init=False)
    status: str = field(init=False)

    def __post_init__(self) -> None:
        if self.rated == 0:
            raise GateError(f"entry {self.id!r}: rated must be nonzero")
        self.margin = (self.rated - self.applied) / self.rated
        if self.margin < 0:
            self.status = "FAIL"
        elif self.margin < self.guideline_margin:
            self.status = "WARN"
        else:
            self.status = "OK"

    @property
    def display_status(self) -> str:
        if self.conditional and self.status in ("FAIL", "WARN"):
            return f"{self.status}(conditional)"
        return self.status


def load_bom(path: Path) -> dict[str, str]:
    """Return {designator: mpn} from an atopile default.csv-shaped BOM.

    atopile's default.csv groups one row per (value, footprint) with a
    comma-joined Designator field; both the Comment and LCSC columns carry
    the real `mpn` (see scripts/capacity_budget_gate.py's own docstring for
    why default.csv, not default.net, is the trustworthy identity source --
    default.net aliases part identity by footprint).
    """
    if not path.exists():
        raise GateError(f"BOM not found: {path} (run `ato build` in elec/ first)")
    text = path.read_text()
    if not text.strip():
        raise GateError(f"BOM is empty: {path}")

    designator_to_mpn: dict[str, str] = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "Designator" not in reader.fieldnames:
            raise GateError(f"BOM missing 'Designator' column: {path}")
        for row in reader:
            mpn = (row.get("Comment") or row.get("LCSC") or "").strip()
            designators_field = row.get("Designator") or ""
            for ref in designators_field.split(","):
                ref = ref.strip()
                if ref:
                    designator_to_mpn[ref] = mpn

    if not designator_to_mpn:
        raise GateError(f"BOM parsed but contained no designators: {path}")
    return designator_to_mpn


def load_limits(path: Path) -> list[dict]:
    if not path.exists():
        raise GateError(f"limits file not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not data or "entries" not in data or not data["entries"]:
        raise GateError(f"limits file has no entries: {path}")
    return data["entries"]


def build_entries(
    raw_entries: list[dict], bom: dict[str, str]
) -> tuple[list[Entry], list[str]]:
    """Return (entries, errors). Errors are designator/MPN mismatches --
    these are tool_error conditions (fail closed), not stress findings."""
    entries: list[Entry] = []
    errors: list[str] = []

    for raw in raw_entries:
        entry_id = raw.get("id", "<unnamed>")
        designators = raw.get("designators") or []
        if not designators:
            errors.append(f"entry {entry_id!r}: no designators listed")
            continue

        expected_mpn = raw.get("mpn")
        entry_ok = True
        for ref in designators:
            if ref not in bom:
                errors.append(
                    f"entry {entry_id!r}: designator {ref!r} not found in BOM "
                    "(part removed, renumbered, or never on the board)"
                )
                entry_ok = False
                continue
            if expected_mpn is not None and bom[ref] != expected_mpn:
                errors.append(
                    f"entry {entry_id!r}: designator {ref!r} carries MPN "
                    f"{bom[ref]!r}, expected {expected_mpn!r} -- part swapped "
                    "since this limit was recorded; re-verify rating before trusting it"
                )
                entry_ok = False

        if not entry_ok:
            # Skip scoring this entry rather than silently comparing a
            # stale rating to a designator/part that no longer matches it.
            continue

        try:
            entries.append(
                Entry(
                    id=entry_id,
                    designators=designators,
                    mpn=expected_mpn,
                    domain=raw.get("domain", "unknown"),
                    unit=raw.get("unit", ""),
                    rated=float(raw["rated"]),
                    applied=float(raw["applied"]),
                    guideline_margin=float(raw.get("guideline_margin", 0.0)),
                    conditional=bool(raw.get("conditional", False)),
                    source=raw.get("source", ""),
                    notes=raw.get("notes", ""),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"entry {entry_id!r}: malformed ({exc})")

    return entries, errors


def render_report(entries: list[Entry]) -> str:
    lines: list[str] = []
    order = {"FAIL": 0, "WARN": 1, "OK": 2}
    ranked = sorted(entries, key=lambda e: (order[e.status], e.margin))

    lines.append(f"{'STATUS':<18} {'MARGIN':>8}  {'ID':<32} {'DESIGNATORS'}")
    lines.append("-" * 90)
    for e in ranked:
        designators = ",".join(e.designators)
        lines.append(
            f"{e.display_status:<18} {e.margin * 100:>7.1f}%  {e.id:<32} {designators}"
        )

    fails = [e for e in ranked if e.status == "FAIL"]
    warns = [e for e in ranked if e.status == "WARN"]
    lines.append("")
    lines.append(f"{len(fails)} FAIL, {len(warns)} WARN, {len(entries) - len(fails) - len(warns)} OK")

    if fails:
        lines.append("")
        lines.append("--- FAIL detail (at or over rated limit) ---")
        for e in fails:
            lines.append(
                f"\n[{e.id}] {e.applied}{e.unit} applied vs {e.rated}{e.unit} rated "
                f"({e.margin * -100:.1f}% over){' [CONDITIONAL]' if e.conditional else ''}"
            )
            lines.append(f"  designators: {', '.join(e.designators)}")
            lines.append(f"  source: {e.source}")
            lines.append(f"  notes: {e.notes}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    parser.add_argument("--limits", type=Path, default=DEFAULT_LIMITS)
    args = parser.parse_args(argv)

    try:
        bom = load_bom(args.bom)
        raw_entries = load_limits(args.limits)
        entries, errors = build_entries(raw_entries, bom)
    except GateError as exc:
        print(f"tool_error: {exc}", file=sys.stderr)
        return 5

    if errors:
        print("tool_error: designator/MPN mismatches (fail closed):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 5

    print(render_report(entries))

    if any(e.status == "FAIL" for e in entries):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
