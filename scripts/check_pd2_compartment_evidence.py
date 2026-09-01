#!/usr/bin/env python3
"""PD2 compartment-evidence gate: the tree may not claim PD2/8.0mm reinforced
creepage without a real, committed, physically-checkable compartment.

Motivation
----------
On 2026-08-11 the owner decided the production architecture selects PD2 (the
IEC 60335-2-6 cl. 29.2 Addition enclosure exception) over PD3, and will add
the sealed compartment that exception requires (see
``docs/evidence/2026-08-11-pd2-decision-record.md``). That decision does
**not** make PD2 valid today. Per the decision pack this gate enforces
(``docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md``), at the time of
this gate's writing:

  - The board outline is a plain rectangle with zero vent/compartment
    provisions (``pcb/temper.kicad_pcb``'s only ``Edge.Cuts`` polygon).
  - The fan is off-board on leadwires; the chassis routes bottom-intake air
    through an 80mm fan -> IGBT-heatsink duct -> rear exhaust, across the
    same cavity the PCB occupies (``docs/CHASSIS_AIRFLOW_DESIGN.md``).
  - The "sealed gasketed PCB compartment" exists only as a *prescriptive
    release requirement* in ``docs/ENVIRONMENTAL_SPEC.md`` Sec 3.1 and
    ``docs/ASSEMBLY_GUIDE.md`` Phase 4.2 -- no cover, gasket, partition, or
    inspection geometry is committed anywhere.

Meanwhile every electrical enforcement point in the tree (the KiCad DRU
generator's ``HV_CREEPAGE_ENFORCED_MM``, the REQ-SAFE-01 validator, the
physical isolation keepout's ``MIN_BARRIER_WIDTH_MM``, the placement
corridor, ...) is aligned at the PD2 figure, 8.0mm. On the standard's own
condition this is only legitimate once the compartment is real. Until then,
every creepage figure measured against 8.0mm is provisional -- this gate
exists so that gap cannot silently persist unflagged.

What this checks
-----------------
1. Reads ``scripts/generate_kicad_dru.py`` (never modified by this gate) to
   determine which bar the tree currently claims: PD2 (``HV_CREEPAGE_ENFORCED_MM
   == HV_CREEPAGE_PD2_MM``) or PD3. If PD3 governs, the compartment
   prerequisite this gate checks does not apply -- reported as
   ``not_applicable``, not silently skipped.
2. If PD2 governs, a compartment-evidence artifact
   (default: ``docs/specs/pd2_compartment_evidence.yaml``) must exist and
   every field below must be a real, specific, non-placeholder value -- not
   prose intent:
     - ``cover``: part reference, material, and length/width/thickness_mm
       (all > 0) -- an actual cover with dimensions, not a sentence saying
       one will be added.
     - ``gasket``: part reference, sealed perimeter length_mm (> 0), and
       compression_mm (> 0).
     - ``partition.keepout_zone_name``: the name of a real ``(name "...")``
       zone that this gate cross-checks against ``pcb/temper.kicad_pcb``
       ITSELF -- a paper claim of a partition with no matching board
       geometry is a violation, not a pass. ``partition.
       separates_pcb_from_airflow`` must be the literal boolean ``true``.
     - ``airflow_routing.duct_crosses_pcb_cavity`` must be the literal
       boolean ``false`` -- an explicit, structured negative claim (not
       parsed English prose) that the coil/heatsink duct is routed outside
       the compartment -- plus a ``duct_geometry_doc`` reference that must
       be a real, existing, committed document.
     - ``inspection``: a criterion id, a numeric ``acceptance_max_gap_mm``
       (> 0, a real pass/fail bound), and a method.
     - ``sign_off``: who verified it, an ISO date, and a commit (``UNKNOWN``
       or 40 lowercase hex chars, shape-checked -- mirrors this repo's
       measurement-provenance convention in
       ``scripts/check_measurement_provenance.py``).
   Every field is validated structurally (type, non-placeholder, sign,
   cross-referenced existence) -- this gate does not attempt to parse or
   trust free-text English claims of intent.

This gate deliberately does NOT re-implement ``scripts/
check_isolation_keepout.py``'s barrier-geometry checks (layer span, erosion
width, bisection, intrusion, far-side crossing) -- that gate already owns
the electrical keepout's *geometric* correctness once a barrier exists. This
gate owns a different, currently entirely unchecked layer: whether the
*mechanical enclosure* that earns the PD2 classification in the first place
has been committed as real, checkable evidence at all.

Current status: **this gate is expected to FAIL on origin/main as of
2026-08-11**, because the compartment does not exist -- see
``docs/evidence/2026-08-11-pd2-decision-record.md`` for the full accounting
and the concrete path to blocking (build the compartment, write the
evidence file, remove this step's ``continue-on-error``).

Fail-closed contract (this repo's gate-family convention): this gate exits
non-zero for every one of:
  - ``scripts/generate_kicad_dru.py`` is missing, or the
    ``HV_CREEPAGE_PD2_MM`` / ``HV_CREEPAGE_PD3_MM`` / ``HV_CREEPAGE_ENFORCED_MM``
    assignments cannot be located in it (the gate cannot determine which bar
    governs at all)
  - the enforced bar matches neither the PD2 nor the PD3 constant it read
  - PD2 governs and ``pcb/temper.kicad_pcb`` is missing when a zone
    cross-check is required

Exit codes:
  0 - PASSED (compartment evidence complete and cross-checked against the
      real board) or NOT_APPLICABLE (the tree currently claims PD3, so the
      compartment prerequisite is moot)
  3 - VIOLATION: PD2 is claimed and the evidence is missing, incomplete, a
      placeholder, or does not match real board geometry
  5 - GATE ERROR: the gate could not determine which bar governs, or could
      not run a trustworthy cross-check

Usage:
  uv run python scripts/check_pd2_compartment_evidence.py
  uv run python scripts/check_pd2_compartment_evidence.py \\
      --dru-source PATH --evidence PATH --board PATH
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_DRU_SOURCE = REPO_ROOT / "scripts" / "generate_kicad_dru.py"
DEFAULT_EVIDENCE = REPO_ROOT / "docs" / "specs" / "pd2_compartment_evidence.yaml"
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# 1. Which bar does the tree currently claim?
# ---------------------------------------------------------------------------

# Which identifier HV_CREEPAGE_ENFORCED_MM is assigned FROM. This one still
# reads the source text, deliberately: it captures the generator's stated
# INTENT ("PD3 governs"), which a numeric comparison cannot recover when the
# two bars happen to be equal.
_ENFORCED_RE = re.compile(
    r"^HV_CREEPAGE_ENFORCED_MM\s*=\s*(HV_CREEPAGE_PD[23]_MM)", re.MULTILINE
)


def _load_generator_module(dru_source_path: Path):
    """Import the DRU generator and hand back the live module.

    Imported rather than regex-scraped. The previous implementation matched
    `^HV_CREEPAGE_PD2_MM\\s*=\\s*([0-9.]+)` -- a NUMERIC LITERAL -- and the
    generator now derives both bars from the standards table instead:

        HV_CREEPAGE_PD2_MM = _tdb.creepage_table_lookup(
            2, "IIIa/IIIb", ">250-400", "17").value_mm() * 2.0

    so neither regex matched anything, `load_enforced_bar` raised, and the gate
    exited 5 -- "could not determine governing bar" -- on every run. Single-
    sourcing the figures from IEC 60664-1 Table 17 silently blinded the gate
    that checks which pollution degree governs, on a board where PD3 sets every
    creepage number. An improvement broke its own checker.

    Importing reads whatever the generator actually computes, so this cannot
    recur the next time the derivation changes shape. The module is import-safe:
    it guards execution behind `if __name__ == "__main__"`.
    """
    if not dru_source_path.is_file():
        raise GateError(f"DRU source not found: {dru_source_path}")
    spec = importlib.util.spec_from_file_location(
        "_pd2_gate_dru_generator", dru_source_path
    )
    if spec is None or spec.loader is None:
        raise GateError(f"could not load {dru_source_path} as a Python module")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover -- generator import failure
        raise GateError(
            f"importing {dru_source_path} failed: {exc!r} -- cannot determine "
            "which creepage bar the tree currently claims"
        ) from exc
    return module


def load_enforced_bar(dru_source_path: Path) -> tuple[str, float, float, float]:
    """Returns ``(governs, enforced_mm, pd2_mm, pd3_mm)`` read from the live
    generator -- never a hardcoded constant, so this gate cannot drift from it.
    ``governs`` is ``"PD2"`` or ``"PD3"``.

    Raises GateError if the module cannot be imported, if any of the three
    values is missing, or if which bar governs cannot be established (the gate
    fails closed rather than guessing at a pollution degree).
    """
    module = _load_generator_module(dru_source_path)

    missing = [
        name
        for name in ("HV_CREEPAGE_PD2_MM", "HV_CREEPAGE_PD3_MM", "HV_CREEPAGE_ENFORCED_MM")
        if not isinstance(getattr(module, name, None), (int, float))
    ]
    if missing:
        raise GateError(
            f"{dru_source_path} does not define numeric {', '.join(missing)} -- "
            "cannot determine which creepage bar the tree currently claims"
        )
    pd2_mm = float(module.HV_CREEPAGE_PD2_MM)
    pd3_mm = float(module.HV_CREEPAGE_PD3_MM)
    enforced_mm = float(module.HV_CREEPAGE_ENFORCED_MM)

    # Prefer the generator's declared intent over a value match.
    m = _ENFORCED_RE.search(dru_source_path.read_text(encoding="utf-8"))
    if m is not None:
        governs = "PD2" if m.group(1) == "HV_CREEPAGE_PD2_MM" else "PD3"
    elif pd2_mm != pd3_mm:
        # No symbolic assignment (a literal, or computed) -- fall back to which
        # bar the enforced value equals. Only sound while the bars differ.
        if enforced_mm == pd2_mm:
            governs = "PD2"
        elif enforced_mm == pd3_mm:
            governs = "PD3"
        else:
            raise GateError(
                f"HV_CREEPAGE_ENFORCED_MM={enforced_mm} matches neither "
                f"PD2={pd2_mm} nor PD3={pd3_mm} in {dru_source_path}"
            )
    else:
        raise GateError(
            f"HV_CREEPAGE_ENFORCED_MM is not assigned from HV_CREEPAGE_PD2_MM "
            f"or HV_CREEPAGE_PD3_MM in {dru_source_path}, and the two bars are "
            f"numerically equal ({pd2_mm}) -- which one governs is genuinely "
            "ambiguous, so this fails closed rather than picking one"
        )

    expected = pd2_mm if governs == "PD2" else pd3_mm
    if enforced_mm != expected:
        raise GateError(
            f"HV_CREEPAGE_ENFORCED_MM={enforced_mm} disagrees with the "
            f"{governs} bar it is assigned from ({expected}) in {dru_source_path}"
        )
    return governs, enforced_mm, pd2_mm, pd3_mm


# ---------------------------------------------------------------------------
# 2. Board-side cross-check: does the claimed partition zone actually exist?
# ---------------------------------------------------------------------------

_ZONE_NAME_RE = re.compile(r'\(name\s+"([^"]+)"\)')


def load_board_zone_names(board_path: Path) -> set[str]:
    """Returns every zone name declared via a ``(name "...")`` field inside
    a ``(zone ...)`` block in ``board_path`` -- KiCad's convention for a
    named rule-area/keepout zone (an ordinary copper-pour zone carries only
    ``net_name``, never ``name``, so this does not accidentally match
    routine copper pours).
    """
    if not board_path.is_file():
        raise GateError(f"board file not found: {board_path}")
    text = board_path.read_text(encoding="utf-8")

    names: set[str] = set()
    idx = 0
    while True:
        marker = text.find("(zone", idx)
        if marker == -1:
            break
        # Guard against matching a longer token like "(zone_settings".
        boundary = text[marker + len("(zone") : marker + len("(zone") + 1]
        if boundary not in (" ", "("):
            idx = marker + len("(zone")
            continue
        depth = 0
        end = None
        for i in range(marker, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            raise GateError(f"{board_path} has an unbalanced '(zone ...)' block at offset {marker}")
        block = text[marker:end]
        m = _ZONE_NAME_RE.search(block)
        if m:
            names.add(m.group(1))
        idx = end
    return names


# ---------------------------------------------------------------------------
# 3. Compartment-evidence field validation
# ---------------------------------------------------------------------------

PLACEHOLDER_VALUES = {"", "tbd", "todo", "n/a", "na", "none", "...", "?", "xxx", "unknown", "tbc"}

REQUIRED_STRING_FIELDS: tuple[tuple[str, str], ...] = (
    ("cover", "part_ref"),
    ("cover", "material"),
    ("gasket", "part_ref"),
    ("partition", "keepout_zone_name"),
    ("airflow_routing", "duct_geometry_doc"),
    ("airflow_routing", "duct_geometry_section"),
    ("inspection", "criterion_id"),
    ("inspection", "method"),
    ("sign_off", "verified_by"),
)

REQUIRED_POSITIVE_NUMERIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("cover", "length_mm"),
    ("cover", "width_mm"),
    ("cover", "thickness_mm"),
    ("gasket", "perimeter_length_mm"),
    ("gasket", "compression_mm"),
    ("inspection", "acceptance_max_gap_mm"),
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _get(d: object, *path: str) -> object:
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _is_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return True
    return value.strip().lower() in PLACEHOLDER_VALUES


def _is_positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def validate_evidence_fields(evidence: object, pd2_mm: float) -> list[str]:
    """Returns the sorted list of field-level violations. Empty means every
    structural criterion this gate can evaluate is satisfied -- it does NOT
    mean the compartment is real, only that the declaration is complete,
    non-placeholder, internally consistent, and (for the fields checked
    elsewhere in ``run()``) cross-referenced against real repository state.
    """
    if not isinstance(evidence, dict):
        return ["compartment evidence file's top level is not a YAML mapping"]

    violations: list[str] = []

    pd2_bar = evidence.get("pd2_bar_mm")
    if not _is_positive_number(pd2_bar) or abs(float(pd2_bar) - pd2_mm) > 1e-9:
        violations.append(
            f"pd2_bar_mm must equal the enforced PD2 bar read from "
            f"generate_kicad_dru.py ({pd2_mm}mm); found {pd2_bar!r}"
        )

    for path in REQUIRED_STRING_FIELDS:
        value = _get(evidence, *path)
        if _is_placeholder(value):
            violations.append(
                f"{'.'.join(path)} is missing or a placeholder value ({value!r}) -- "
                "a real, specific value is required, not prose intent"
            )

    for path in REQUIRED_POSITIVE_NUMERIC_FIELDS:
        value = _get(evidence, *path)
        if not _is_positive_number(value):
            violations.append(f"{'.'.join(path)} must be a positive number; found {value!r}")

    sep = _get(evidence, "partition", "separates_pcb_from_airflow")
    if sep is not True:
        violations.append(
            f"partition.separates_pcb_from_airflow must be the literal boolean "
            f"true; found {sep!r}"
        )

    crosses = _get(evidence, "airflow_routing", "duct_crosses_pcb_cavity")
    if crosses is not False:
        violations.append(
            "airflow_routing.duct_crosses_pcb_cavity must be the literal boolean "
            f"false (an explicit claim the duct is routed outside the compartment); "
            f"found {crosses!r}"
        )

    date = _get(evidence, "sign_off", "date")
    if not isinstance(date, str) or not _DATE_RE.match(date):
        violations.append(f"sign_off.date must be an ISO date (YYYY-MM-DD); found {date!r}")

    commit = _get(evidence, "sign_off", "commit")
    if not (commit == "UNKNOWN" or (isinstance(commit, str) and _COMMIT_RE.match(commit))):
        violations.append(
            "sign_off.commit must be 'UNKNOWN' or a 40-character lowercase hex "
            f"commit SHA; found {commit!r}"
        )

    doc_field = _get(evidence, "airflow_routing", "duct_geometry_doc")
    if isinstance(doc_field, str) and not _is_placeholder(doc_field):
        doc_path = REPO_ROOT / doc_field
        if not doc_path.is_file():
            violations.append(
                f"airflow_routing.duct_geometry_doc={doc_field!r} does not exist in "
                "the repository -- the airflow-routing claim must cite a real, "
                "committed document, not a fabricated path"
            )

    return sorted(violations)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    governs: str | None = None
    enforced_mm: float | None = None
    evidence_path: str = ""
    evidence_present: bool = False
    field_violations: list[str] = field(default_factory=list)
    zone_violations: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(dru_source_path: Path, evidence_path: Path, board_path: Path) -> tuple[str, Report]:
    report = Report(evidence_path=str(evidence_path))

    try:
        governs, enforced_mm, pd2_mm, _pd3_mm = load_enforced_bar(dru_source_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    report.governs = governs
    report.enforced_mm = enforced_mm

    if governs != "PD2":
        # PD3 (or, in principle, some other bar) governs -- the sealed-
        # compartment prerequisite this gate checks does not apply. This is
        # a real, positive verdict, not a skipped check.
        return "not_applicable", report

    if not evidence_path.is_file():
        report.field_violations.append(
            f"{evidence_path} does not exist -- the tree claims PD2/{enforced_mm}mm "
            "(generate_kicad_dru.py's HV_CREEPAGE_ENFORCED_MM) but no compartment "
            "evidence artifact has been committed"
        )
        return "violation", report

    try:
        with open(evidence_path, encoding="utf-8") as fh:
            evidence = yaml.safe_load(fh)
    except yaml.YAMLError as e:
        report.field_violations.append(f"{evidence_path} is not valid YAML: {e}")
        return "violation", report

    report.evidence_present = True
    report.field_violations = validate_evidence_fields(evidence, pd2_mm)

    zone_name = _get(evidence, "partition", "keepout_zone_name")
    if isinstance(zone_name, str) and not _is_placeholder(zone_name):
        try:
            board_zone_names = load_board_zone_names(board_path)
        except GateError as e:
            report.tool_errors.append(str(e))
            return "tool_error", report
        if zone_name not in board_zone_names:
            report.zone_violations.append(
                f"partition.keepout_zone_name={zone_name!r} matches no "
                f'(name "...") zone actually present in {board_path} -- the '
                "compartment's board-side boundary is not real board geometry"
            )

    if report.field_violations or report.zone_violations:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "PD2 compartment-evidence gate -- "
        f"tree currently claims {report.governs} "
        f"({report.enforced_mm}mm reinforced creepage)"
        if report.governs
        else "PD2 compartment-evidence gate -- could not determine governing bar"
    )

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")
        if state == "tool_error":
            print(
                "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
                "could not run a trustworthy check.",
                file=sys.stderr,
            )
            return

    if state == "not_applicable":
        print(
            "\nPD3 governs, not PD2 -- the sealed-compartment prerequisite this "
            "gate checks does not apply. NOT_APPLICABLE (treated as pass)."
        )
        return

    print(f"\nEvidence file: {report.evidence_path} (present: {report.evidence_present})")
    all_violations = report.field_violations + report.zone_violations
    print(f"\n=== VIOLATIONS: {len(all_violations)} ===")
    for v in all_violations:
        print(f"  VIOLATION {v}")

    if state == "clean":
        print(
            "\nPD2 compartment-evidence gate passed -- compartment evidence is "
            "complete, non-placeholder, and cross-checked against the real board."
        )
    elif state == "violation":
        print(
            f"\nFAILED -- {len(all_violations)} violation(s). The tree claims "
            f"PD2/{report.enforced_mm}mm without a complete, real compartment. "
            "See docs/evidence/2026-08-11-pd2-decision-record.md."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dru-source", type=Path, default=DEFAULT_DRU_SOURCE)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    args = parser.parse_args()

    state, report = run(args.dru_source, args.evidence, args.board)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### PD2 Compartment-Evidence Gate: {state}\n")
            f.write(
                f"- Governing bar: {report.governs} ({report.enforced_mm}mm)\n"
                f"- Evidence present: {report.evidence_present}\n"
                f"- Field violations: {len(report.field_violations)}\n"
                f"- Zone cross-check violations: {len(report.zone_violations)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
