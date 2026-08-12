#!/usr/bin/env python3
"""Net-class correspondence gate, two properties:

PROPERTY 1 -- parameter correspondence. For every netclass name declared
in both ``pcb/temper.kicad_pro`` and ``TEMPER_NET_CLASSES``
(``packages/temper-placer/src/temper_placer/core/design_rules.py``), the
four scalar routing fields (clearance, trace width, via diameter, via
drill) must agree.

PROPERTY 2 -- referenced-class existence. For every net named in
``TEMPER_NET_ASSIGNMENTS`` (same module), the class it maps to must
actually be declared in BOTH ``pcb/temper.kicad_pro``'s
``net_settings.classes`` and ``TEMPER_NET_CLASSES``. This is the gate that
would have caught the ``"gnd": "GND"`` / ``"PWR_RTN": "GND"`` defect
(docs/evidence/2026-08-12-nonexistent-gnd-class-mapping.md): ``"GND"`` was
(and, via the still-open ``"CGND": "GND"`` entry, remains) a real,
non-empty ``NetClassRules`` row in ``TEMPER_NET_CLASSES`` -- PROPERTY 1
would never flag it, because PROPERTY 1 only ever compares classes already
agreed to be declared in both tables by name, and ``"GND"`` never was.
Naming a class in an *assignment* is a different claim from *declaring*
that class, and nothing checked the former implied the latter until this
property.

Why this gate exists
---------------------
``pcb/temper.kicad_pro``'s ``net_settings.netclass_assignments`` (which NET
belongs to which CLASS) and ``net_settings.classes`` (what each CLASS's
clearance/trace-width/via figures ARE) are two different sections of the
same file, checked by two different mechanisms in this repo -- and only
one of them was ever verified against ``design_rules.py``.

PR #1023 ("correct kicad_pro netclass case/coverage mismatch") and PR
#1025 ("full sync of kicad_pro netclass_assignments from design_rules.py
SSOT") both title themselves as reconciling ``kicad_pro`` against
``design_rules.py``. Read closely, both only ever touch
``netclass_assignments`` -- confirmed by diff:

    $ git show 8e92559e2 -- pcb/temper.kicad_pro | grep '"clearance"'
    (no output)
    $ git show 28de4543d -- pcb/temper.kicad_pro | grep '"clearance"'
    (no output)

Neither PR's diff, and no gate in this repo before this one
(``scripts/sync_kicad_netclass_assignments.py`` -- see its
``load_declared_classes``, which reads only class *names* via
``{c["name"] for c in classes}``, never a class's own field values; and
``scripts/check_hv_netclass_coverage.py``'s PROPERTY 2, which checks that a
declared class has *at least one rule of any kind*, not that the rule's
*value* is right), ever compares the *class parameter tables* the two
files independently hand-maintain. The two "sync" PRs' own titles describe
a broader reconciliation than either one's diff, or any gate, actually
performs.

Confirmed live on ``origin/main`` right now, by this gate's own
``run()`` against the real files:

    HighVoltage  clearance     design_rules.py=6.0   kicad_pro=2.0
    Power        clearance     design_rules.py=0.25  kicad_pro=0.5
    Power        trace_width   design_rules.py=0.5   kicad_pro=1.0
    Power        via_diameter  design_rules.py=0.8   kicad_pro=1.0
    Power        via_drill     design_rules.py=0.4   kicad_pro=0.5

This gate does not decide which side is correct for any of the five --
that is a separate, explicit human/domain call (the same category of
decision ``check_hv_netclass_coverage.py``'s docstring reserves for
``PWR_RTN``, and Gate 3's docstring reserves for the harder half of its 31
broken keys). It only asserts that a value mismatch between the two
declared-SSOT tables must never pass silently.

Scope, deliberately narrow
---------------------------
PROPERTY 1 compares only classes present in BOTH tables by name. A class
present in only one (e.g. ``HighCurrent``/``HighSpeed``/``Signal`` exist
only in ``TEMPER_NET_CLASSES``; ``Default``/``Differential`` exist only in
``pcb/temper.kicad_pro``) has nothing to disagree with and is not a
defect PROPERTY 1's invariant covers -- that is class-set coverage, not
class-parameter agreement.

Class-set coverage itself splits into two different failure shapes, only
one of which PROPERTY 2 (added alongside PROPERTY 1) covers. A class
*declared* in one table but never *referenced* by any net assignment
(``HighCurrent``/``HighSpeed``/``Signal`` above; also
``check_hv_netclass_coverage.py``'s PROPERTY 2, which checks that a
declared class enforces at least one DRU rule) is still out of scope here
-- an unused class is inert, not unsound. A class *referenced* by
``TEMPER_NET_ASSIGNMENTS`` but never *declared* anywhere real enough to
back it (``"GND"``, this gate's own PROPERTY 2) is the shape that actually
misclassified 86 real pads on the fabrication-invisible path -- that is
what PROPERTY 2 below checks.

Only the four scalar routing fields both schemas actually share by
meaning are compared: ``clearance``, ``trace_width`` (spelled
``track_width`` in ``pcb/temper.kicad_pro``'s JSON), ``via_diameter``, and
``via_drill`` -- ``NetClassRules``' own docstring in
``core/netclass_rules_gen.py`` calls these "the four scalar routing
fields". Fields with no ``pcb/temper.kicad_pro`` equivalent
(``creepage_mm``, ``voltage_v``, ``routing_strategy``, ``dru_priority``,
``safety_category``, ...) are out of scope -- there is nothing on the
KiCad side to compare them against.

Fail-closed contract (this repo's gate-family convention): this gate
exits non-zero for every one of:
  - ``pcb/temper.kicad_pro`` is missing, not valid JSON, or has no
    non-empty ``net_settings.classes`` list
  - ``TEMPER_NET_CLASSES``/``TEMPER_NET_ASSIGNMENTS`` cannot be imported
    (environment not synced)
  - zero classes are declared in both tables by name -- an empty
    comparison is a broken gate, never a clean pass
  - ``TEMPER_NET_ASSIGNMENTS`` is empty -- PROPERTY 2 would vacuously pass

Exit codes:
  0 - PASSED: every class declared in both tables agrees on all four
      scalar routing fields (PROPERTY 1), and every class referenced by
      ``TEMPER_NET_ASSIGNMENTS`` is declared in both tables (PROPERTY 2)
  3 - VIOLATION: at least one shared class disagrees on at least one field
      (PROPERTY 1), or at least one assignment names a class missing from
      ``pcb/temper.kicad_pro`` and/or ``TEMPER_NET_CLASSES`` (PROPERTY 2)
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_netclass_class_param_correspondence.py
  uv run python scripts/check_netclass_class_param_correspondence.py --kicad-pro PATH
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_KICAD_PRO = REPO_ROOT / "pcb" / "temper.kicad_pro"

# (design_rules.py NetClassRules attribute -> pcb/temper.kicad_pro JSON key)
# -- "the four scalar routing fields" per core/netclass_rules_gen.py's own
# docstring. Order is display order, not significant otherwise.
FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("clearance", "clearance"),
    ("trace_width", "track_width"),
    ("via_diameter", "via_diameter"),
    ("via_drill", "via_drill"),
)


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def load_kicad_pro_class_params(kicad_pro_path: Path) -> dict[str, dict[str, Any]]:
    """Return {class_name: {json_field: value}} for every entry in
    ``pcb/temper.kicad_pro``'s ``net_settings.classes``."""
    if not kicad_pro_path.is_file():
        raise GateError(f"KiCad project file not found: {kicad_pro_path}")
    try:
        data = json.loads(kicad_pro_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GateError(f"{kicad_pro_path} is not valid JSON: {e}") from e

    classes = data.get("net_settings", {}).get("classes") if isinstance(data, dict) else None
    if not isinstance(classes, list) or not classes:
        raise GateError(
            f"{kicad_pro_path} has no non-empty 'net_settings.classes' "
            "list -- an empty or absent netclass declaration must fail "
            "the gate, not pass it vacuously"
        )

    result: dict[str, dict[str, Any]] = {}
    for entry in classes:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise GateError(
                f"{kicad_pro_path} has a 'net_settings.classes' entry with no 'name': {entry!r}"
            )
        result[str(entry["name"])] = entry
    return result


def _default_live_net_classes() -> dict[str, Any]:
    """Import the real, live TEMPER_NET_CLASSES. Raises GateError
    (fail-closed) if the environment is not synced -- mirrors
    ``check_hv_netclass_coverage.py``'s ``_default_live_inputs``."""
    try:
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES  # noqa: PLC0415
    except ImportError as e:
        raise GateError(
            "could not import temper_placer.core.design_rules -- is the "
            f"environment synced (`uv sync`)? ({e})"
        ) from e
    return dict(TEMPER_NET_CLASSES)


def _default_live_net_assignments() -> dict[str, str]:
    """Import the real, live TEMPER_NET_ASSIGNMENTS (PROPERTY 2's input) --
    the net-name -> class-name table, distinct from TEMPER_NET_CLASSES
    (the class-name -> parameters table PROPERTY 1 checks). Raises
    GateError (fail-closed) if the environment is not synced."""
    try:
        from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS  # noqa: PLC0415
    except ImportError as e:
        raise GateError(
            "could not import temper_placer.core.design_rules -- is the "
            f"environment synced (`uv sync`)? ({e})"
        ) from e
    return dict(TEMPER_NET_ASSIGNMENTS)


# ---------------------------------------------------------------------------
# Correspondence check
# ---------------------------------------------------------------------------


@dataclass
class FieldMismatch:
    class_name: str
    field_name: str
    kicad_pro_field: str
    design_rules_value: Any
    kicad_pro_value: Any


def compare_class_params(
    net_classes: dict[str, Any], kicad_pro_classes: dict[str, dict[str, Any]]
) -> tuple[list[str], list[FieldMismatch]]:
    """Return (shared_class_names, mismatches) for every class declared in
    both tables. A field present on the design_rules.py side but absent
    from the kicad_pro entry is reported as a mismatch against ``None``
    (never silently skipped)."""
    shared = sorted(set(net_classes) & set(kicad_pro_classes))
    mismatches: list[FieldMismatch] = []
    for cls in shared:
        dr_rules = net_classes[cls]
        kc_entry = kicad_pro_classes[cls]
        for dr_field, kc_field in FIELD_MAP:
            dr_val = getattr(dr_rules, dr_field)
            kc_val = kc_entry.get(kc_field)
            if dr_val != kc_val:
                mismatches.append(
                    FieldMismatch(
                        class_name=cls,
                        field_name=dr_field,
                        kicad_pro_field=kc_field,
                        design_rules_value=dr_val,
                        kicad_pro_value=kc_val,
                    )
                )
    return shared, mismatches


@dataclass
class UnresolvedClassReference:
    net_name: str
    class_name: str
    missing_from_kicad_pro: bool
    missing_from_design_rules: bool


# Net names PROPERTY 2 reports but does not block on. A single, narrow,
# explicitly-documented carve-out -- the same convention
# check_hv_netclass_coverage.py already uses for its own "KiCad-structural
# classes deliberately excluded" and "PWR_RTN ... deliberately NOT
# enforced" scope notes -- not a general escape hatch. Each entry needs its
# own citation; do not add to this set without one.
#
# "CGND": design_rules.py's TEMPER_NET_ASSIGNMENTS still maps
# ``"CGND": "GND"`` (the same nonexistent-in-kicad_pro class this gate's
# fixed defect used to name from "gnd"/"PWR_RTN" too), and that line's own
# comment is explicit that resolving it is a separate, deliberately-
# reserved decision ("the GND-family reclassification ... is an open,
# deliberately-reserved decision ... removing it is that decision's job,
# not this line's"). CGND names zero nets on the real board (0 references
# in pcb/temper.kicad_pcb, checked 2026-08-11 and again 2026-08-12), so the
# unresolvable reference is real but inert, not a live hazard -- reported
# every run (never silently dropped), just not blocking. Promoting this
# entry to blocking is exactly the follow-up the design_rules.py comment
# already names; do that instead of widening this set.
_KNOWN_UNRESOLVED_ASSIGNMENTS: frozenset[str] = frozenset({"CGND"})


def check_referenced_classes_exist(
    net_assignments: dict[str, str],
    net_classes: dict[str, Any],
    kicad_pro_classes: dict[str, dict[str, Any]],
) -> tuple[list[UnresolvedClassReference], list[UnresolvedClassReference]]:
    """PROPERTY 2: every class named in ``net_assignments`` (``net -> class``)
    must be declared in BOTH ``net_classes`` (``TEMPER_NET_CLASSES``) and
    ``kicad_pro_classes`` (``pcb/temper.kicad_pro``'s ``net_settings.classes``).

    Returns ``(blocking, known)`` -- findings for net names in
    ``_KNOWN_UNRESOLVED_ASSIGNMENTS`` are split into ``known`` (reported,
    never silent, but does not fail the gate); everything else is
    ``blocking``.

    A class present in ``net_classes`` but absent from ``kicad_pro_classes``
    (the ``"gnd"``/``"PWR_RTN"`` -> ``"GND"`` defect this property exists to
    catch) is real Python-side design-rules data -- ``get_rules_for_net``
    resolves it to a genuine, non-default ``NetClassRules`` row, so nothing
    about the resolution *looks* broken from inside the placer -- but it is
    invisible to every kicad_pro/kicad-cli-driven check, because kicad_pro
    never declared a class by that name. The reverse (present in
    ``kicad_pro_classes`` but absent from ``net_classes``) is reported with
    equal weight: an assignment naming either gap is unresolvable on that
    side, not just the ``"GND"`` direction seen in practice so far.
    """
    blocking: list[UnresolvedClassReference] = []
    known: list[UnresolvedClassReference] = []
    for net_name, class_name in sorted(net_assignments.items()):
        missing_kicad = class_name not in kicad_pro_classes
        missing_dr = class_name not in net_classes
        if missing_kicad or missing_dr:
            finding = UnresolvedClassReference(
                net_name=net_name,
                class_name=class_name,
                missing_from_kicad_pro=missing_kicad,
                missing_from_design_rules=missing_dr,
            )
            (known if net_name in _KNOWN_UNRESOLVED_ASSIGNMENTS else blocking).append(finding)
    return blocking, known


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    classes_checked: list[str] = field(default_factory=list)
    mismatches: list[FieldMismatch] = field(default_factory=list)
    assignments_checked: list[str] = field(default_factory=list)
    unresolved_references: list[UnresolvedClassReference] = field(default_factory=list)
    known_unresolved_references: list[UnresolvedClassReference] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(
    kicad_pro_path: Path,
    net_classes: dict[str, Any] | None = None,
    kicad_pro_classes: dict[str, dict[str, Any]] | None = None,
    net_assignments: dict[str, str] | None = None,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation' | 'tool_error'.

    ``net_classes`` / ``kicad_pro_classes`` / ``net_assignments`` default to
    the real, live values (imported ``TEMPER_NET_CLASSES`` /
    ``TEMPER_NET_ASSIGNMENTS`` / parsed ``kicad_pro_path``) -- tests
    override any of them to construct a mutation without needing a second
    real copy of the package or a scratch ``.kicad_pro`` file on disk.
    """
    report = Report()

    try:
        if net_classes is None:
            net_classes = _default_live_net_classes()
        if kicad_pro_classes is None:
            kicad_pro_classes = load_kicad_pro_class_params(kicad_pro_path)
        if net_assignments is None:
            net_assignments = _default_live_net_assignments()
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    shared, mismatches = compare_class_params(net_classes, kicad_pro_classes)

    if not shared:
        report.tool_errors.append(
            "zero netclass names are declared in both TEMPER_NET_CLASSES and "
            f"{kicad_pro_path}'s net_settings.classes -- vacuous run, not a "
            "clean pass"
        )
        return "tool_error", report

    if not net_assignments:
        report.tool_errors.append(
            "TEMPER_NET_ASSIGNMENTS is empty -- PROPERTY 2 (referenced-class "
            "existence) would vacuously pass, not a clean run"
        )
        return "tool_error", report

    report.classes_checked = shared
    report.mismatches = mismatches
    report.assignments_checked = sorted(net_assignments)
    blocking, known = check_referenced_classes_exist(net_assignments, net_classes, kicad_pro_classes)
    report.unresolved_references = blocking
    report.known_unresolved_references = known

    if report.mismatches or report.unresolved_references:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "Net-class correspondence gate -- PROPERTY 1: "
        f"{len(report.classes_checked)} class(es) checked (declared in both "
        "TEMPER_NET_CLASSES and pcb/temper.kicad_pro), 4 scalar routing "
        f"field(s) each. PROPERTY 2: {len(report.assignments_checked)} "
        "net assignment(s) checked (TEMPER_NET_ASSIGNMENTS) for referenced-"
        "class existence in both tables."
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

    print(f"\n=== PROPERTY 1 -- FIELD MISMATCHES: {len(report.mismatches)} ===")
    for m in report.mismatches:
        print(
            f"  VIOLATION netclass {m.class_name!r} field {m.field_name!r}: "
            f"design_rules.py TEMPER_NET_CLASSES={m.design_rules_value!r} but "
            f"pcb/temper.kicad_pro net_settings.classes[{m.class_name!r}]"
            f"[{m.kicad_pro_field!r}]={m.kicad_pro_value!r} -- neither PR #1023 "
            "nor PR #1025 (both titled as syncing kicad_pro against "
            "design_rules.py) ever compared this field; both only touched "
            "netclass_assignments (which NET maps to which CLASS), never a "
            "class's own parameter values"
        )

    print(
        f"\n=== PROPERTY 2 -- UNRESOLVED CLASS REFERENCES (BLOCKING): "
        f"{len(report.unresolved_references)} ==="
    )
    for u in report.unresolved_references:
        gaps = []
        if u.missing_from_kicad_pro:
            gaps.append("pcb/temper.kicad_pro net_settings.classes")
        if u.missing_from_design_rules:
            gaps.append("TEMPER_NET_CLASSES")
        print(
            f"  VIOLATION net {u.net_name!r} -> class {u.class_name!r}, not "
            f"declared in: {', '.join(gaps)}"
        )

    if report.known_unresolved_references:
        print(
            "\n=== PROPERTY 2 -- KNOWN UNRESOLVED (INFORMATIONAL, not "
            f"blocking, see _KNOWN_UNRESOLVED_ASSIGNMENTS): "
            f"{len(report.known_unresolved_references)} ==="
        )
        for u in report.known_unresolved_references:
            gaps = []
            if u.missing_from_kicad_pro:
                gaps.append("pcb/temper.kicad_pro net_settings.classes")
            if u.missing_from_design_rules:
                gaps.append("TEMPER_NET_CLASSES")
            print(
                f"  KNOWN net {u.net_name!r} -> class {u.class_name!r}, not "
                f"declared in: {', '.join(gaps)}"
            )

    if state == "clean":
        print("\nNet-class correspondence gate passed")
    elif state == "violation":
        print(
            f"\nFAILED -- {len(report.mismatches)} field mismatch(es), "
            f"{len(report.unresolved_references)} unresolved class reference(s)"
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-pro", type=Path, default=DEFAULT_KICAD_PRO)
    args = parser.parse_args()

    state, report = run(args.kicad_pro)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Net-Class Correspondence Gate: {state}\n")
            f.write(
                f"- PROPERTY 1 -- classes checked: {len(report.classes_checked)}\n"
                f"- PROPERTY 1 -- field mismatches: {len(report.mismatches)}\n"
                f"- PROPERTY 2 -- assignments checked: {len(report.assignments_checked)}\n"
                f"- PROPERTY 2 -- unresolved class references (blocking): "
                f"{len(report.unresolved_references)}\n"
                f"- PROPERTY 2 -- known unresolved (informational): "
                f"{len(report.known_unresolved_references)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )
            if report.mismatches:
                f.write("\nMismatches:\n")
                for m in report.mismatches:
                    f.write(
                        f"- `{m.class_name}.{m.field_name}`: "
                        f"design_rules.py=`{m.design_rules_value}` "
                        f"kicad_pro=`{m.kicad_pro_value}`\n"
                    )
            if report.unresolved_references:
                f.write("\nUnresolved class references:\n")
                for u in report.unresolved_references:
                    f.write(f"- `{u.net_name}` -> `{u.class_name}`\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
