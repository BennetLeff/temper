#!/usr/bin/env python3
"""Net-class *parameter* correspondence gate: for every netclass name
declared in both ``pcb/temper.kicad_pro`` and ``TEMPER_NET_CLASSES``
(``packages/temper-placer/src/temper_placer/core/design_rules.py``), the
four scalar routing fields (clearance, trace width, via diameter, via
drill) must agree.

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
Only classes present in BOTH tables by name are compared. A class present
in only one (e.g. ``GND``/``HighCurrent``/``HighSpeed``/``Signal`` exist
only in ``TEMPER_NET_CLASSES``; ``Default``/``Differential`` exist only in
``pcb/temper.kicad_pro``) has nothing to disagree with and is not a
defect this gate's invariant covers -- that is class-set coverage, a
different property already partially covered by
``check_hv_netclass_coverage.py``'s PROPERTY 2, not class-parameter
agreement.

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
  - ``TEMPER_NET_CLASSES`` cannot be imported (environment not synced)
  - zero classes are declared in both tables by name -- an empty
    comparison is a broken gate, never a clean pass

Exit codes:
  0 - PASSED: every class declared in both tables agrees on all four
      scalar routing fields
  3 - VIOLATION: at least one shared class disagrees on at least one field
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


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    classes_checked: list[str] = field(default_factory=list)
    mismatches: list[FieldMismatch] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(
    kicad_pro_path: Path,
    net_classes: dict[str, Any] | None = None,
    kicad_pro_classes: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation' | 'tool_error'.

    ``net_classes`` / ``kicad_pro_classes`` default to the real, live
    values (imported ``TEMPER_NET_CLASSES`` / parsed ``kicad_pro_path``) --
    tests override either to construct a mutation without needing a second
    real copy of the package or a scratch ``.kicad_pro`` file on disk.
    """
    report = Report()

    try:
        if net_classes is None:
            net_classes = _default_live_net_classes()
        if kicad_pro_classes is None:
            kicad_pro_classes = load_kicad_pro_class_params(kicad_pro_path)
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

    report.classes_checked = shared
    report.mismatches = mismatches

    if report.mismatches:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "Net-class parameter correspondence gate -- "
        f"{len(report.classes_checked)} class(es) checked (declared in both "
        "TEMPER_NET_CLASSES and pcb/temper.kicad_pro), 4 scalar routing "
        "field(s) each"
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

    print(f"\n=== FIELD MISMATCHES: {len(report.mismatches)} ===")
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

    if state == "clean":
        print("\nNet-class parameter correspondence gate passed")
    elif state == "violation":
        print(f"\nFAILED -- {len(report.mismatches)} field mismatch(es)")


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
            f.write(f"\n### Net-Class Parameter Correspondence Gate: {state}\n")
            f.write(
                f"- Classes checked: {len(report.classes_checked)}\n"
                f"- Field mismatches: {len(report.mismatches)}\n"
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

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
