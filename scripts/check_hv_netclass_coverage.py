#!/usr/bin/env python3
"""HV netclass coverage gate: every mains/HV net has a netclass, and every
declared netclass actually enforces something.

Motivating defect (confirmed on ``origin/main``, 2026-07-29 -- fixed on the
``fix/recover-stranded-netclass-safety`` branch this gate is designed
against):

  1. ``+170V_BUS``, the live 170V DC bus (declared under
     ``elec/domain_manifest.yaml``'s ``HV`` domain), resolved to NO
     netclass at all via ``TEMPER_NET_ASSIGNMENTS``
     (``packages/temper-placer/src/temper_placer/core/design_rules.py``).
     ``DesignRules.get_rules_for_net`` falls through to a default,
     low-voltage clearance/creepage figure for any net with no matching
     override, net-class assignment, or name-pattern match -- so this
     silently downgraded a live 170V DC rail to LV separation for every
     Python-side (CP-SAT placer, router_v6) decision.
  2. ``+15V_LS`` (the low-side gate-driver rail, referenced to
     ``DC_BUS_RTN`` -- floats within the HV domain per the manifest) was
     assigned the low-voltage ``Power`` class instead of ``HighVoltage``.
  3. ``HighVoltageIsolated`` -- the gate-drive floating bootstrap-supply
     netclass -- is a real, intentional netclass (declared with a
     safety-relevant clearance figure and description in
     ``pcb/temper.kicad_pro``'s ``net_settings.classes``, and in
     ``TEMPER_NET_CLASSES`` once added), but
     ``scripts/generate_kicad_dru.py`` emitted ZERO rules referencing it
     by name -- a class that exists and enforces nothing. Any net ever
     assigned this class inherited only KiCad's per-netclass baseline
     clearance and no creepage protection at all.

Two independent properties are checked. They are kept separate because
they are different failure shapes -- fixing one does not imply the other
is fixed, and each needs its own falsifier:

PROPERTY 1 -- HV net coverage
------------------------------
Every net ``elec/domain_manifest.yaml`` declares under its ``HV`` domain
(the hand-reviewed, human-curated SSOT for which nets are mains/HV-domain,
also relied on by ``scripts/check_domain_partition.py``) must have an
entry in ``TEMPER_NET_ASSIGNMENTS``. A manifest-HV net absent from that
table silently falls through to ``DesignRules``' LV default for any
Python-side clearance/routing decision -- see the ``+170V_BUS`` defect
above.

PROPERTY 2 -- netclass rule coverage
--------------------------------------
Every class this project declares as a real, intentional netclass must
have at least one rule in ``scripts/generate_kicad_dru.py``'s GENERATED
output (not its source text -- the trace-width rules are built from an
f-string template, so a textual grep of the script would false-negative)
that POSITIVELY matches that class by name (an ``A.NetClass == 'X'`` or
``B.NetClass == 'X'`` condition). A class mentioned only negatively
(``!= 'X'``, i.e. "everything except this class"), or not mentioned at
all, enforces nothing for any net assigned to it.

"Declared as a real, intentional netclass" is the union of:
  - every key of ``TEMPER_NET_CLASSES`` (the Python placer/router's own
    net-class model), and
  - every class in ``pcb/temper.kicad_pro``'s ``net_settings.classes``
    that carries a non-empty ``description`` (this project's convention
    for a deliberately-authored safety/routing netclass, confirmed against
    every entry as of this gate's writing: ACMains, HighVoltage,
    GateDrive, HighVoltageIsolated, FinePitch and Power all carry a
    voltage/current/clearance narrative; ``Differential`` -- a
    pre-existing USB-pair length/impedance-matching class, unrelated to
    the HV/SELV safety domain this gate targets and never touched by the
    defect this gate exists to catch -- carries none),
  MINUS the two KiCad-structural classes this gate deliberately excludes
  by name (see ``STRUCTURAL_KICAD_CLASSES`` below): ``Default`` (KiCad's
  universal fallback for any net with no explicit class -- already
  covered by ``generate_kicad_dru.py``'s type-based "Default routing"
  catch-all rule, which matches ``A.Type == 'Track'``, not a netclass
  name, so it would never show up as a positive ``NetClass == 'Default'``
  match even when it is working exactly as intended) and ``Differential``
  (see above -- a real, pre-existing gap of its own, but a DIFFERENT,
  unrelated defect this task was not asked to fix; flagging it here would
  make this gate permanently red on a change nobody made).

Why ``pcb/temper.kicad_pro`` at all, and not just ``TEMPER_NET_CLASSES``:
on ``origin/main`` right now, ``HighVoltageIsolated`` is declared ONLY in
``pcb/temper.kicad_pro`` (with a real, described 6.0mm-clearance class
entry) -- it is entirely absent from ``TEMPER_NET_CLASSES``. A check
scoped to ``TEMPER_NET_CLASSES`` alone could never see it, and so could
never name it as the "declared netclass with no rules" defect it actually
is. Reading ``pcb/temper.kicad_pro`` is read-only (never written by this
gate) and is explicitly permitted; only ``pcb/temper.kicad_pcb`` (the
board file, a different file) is off-limits.

Fail-closed contract (this repo's gate-family convention -- see
``check_domain_partition.py``, ``check_net_classification.py``): this
gate never exits 0 unless it positively confirms it ran a real check on
real, fresh data. It exits non-zero for every one of:
  - the domain manifest is missing, empty, malformed, or has no non-empty
    ``HV`` domain (delegates to ``check_domain_partition.load_manifest``,
    the same parser ``check_domain_partition.py`` itself trusts)
  - ``pcb/temper.kicad_pro`` is missing, not valid JSON, or has no
    non-empty ``net_settings.classes`` list
  - ``TEMPER_NET_ASSIGNMENTS`` or ``TEMPER_NET_CLASSES`` cannot be
    imported (e.g. the environment is not synced)
  - zero HV nets discovered, or zero declared netclasses discovered --
    an empty check is a broken gate, never a clean pass

Exit codes:
  0 - PASSED: every manifest-HV net has a netclass, and every declared
      netclass has at least one positive rule in the generated DRU output
  3 - VIOLATION: at least one manifest-HV net has no netclass, or at
      least one declared netclass has zero positive rules
  5 - GATE ERROR: the gate could not run a trustworthy check at all (see
      list above) -- never conflated with "0 violations"

Usage:
  uv run python scripts/check_hv_netclass_coverage.py
  uv run python scripts/check_hv_netclass_coverage.py --manifest PATH --kicad-pro PATH
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402
from check_domain_partition import GateError as _ManifestGateError  # noqa: E402
from check_domain_partition import load_manifest  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"
DEFAULT_KICAD_PRO = REPO_ROOT / "pcb" / "temper.kicad_pro"

# KiCad-structural classes deliberately excluded from PROPERTY 2's
# "declared netclass" registry -- see the module docstring's PROPERTY 2
# section for why each one is excluded.
STRUCTURAL_KICAD_CLASSES: frozenset[str] = frozenset({"Default", "Differential"})

_NETCLASS_EQ_RE = re.compile(r"[AB]\.NetClass\s*==\s*'([^']+)'")


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Property 1: HV net coverage
# ---------------------------------------------------------------------------


def load_hv_nets(manifest_path: Path) -> list[str]:
    """Return the exact list of net names declared under
    ``elec/domain_manifest.yaml``'s ``HV`` domain, via the same parser
    ``check_domain_partition.py`` trusts (so this gate can never silently
    diverge from that gate's own idea of what "HV domain" means).

    Raises GateError (fail-closed) for every malformed-manifest case
    ``check_domain_partition.load_manifest`` itself already raises on
    (missing file, empty file, not YAML, no domains, fewer than 2
    domains, a domain with no nets, a net claimed by two domains), plus
    if there is no domain literally named ``HV``.
    """
    try:
        manifest = load_manifest(manifest_path)
    except _ManifestGateError as e:
        raise GateError(f"domain manifest could not be loaded: {e}") from e

    hv_nets = manifest.domains.get("HV")
    if not hv_nets:
        raise GateError(
            f"domain manifest {manifest_path} declares no non-empty 'HV' "
            "domain -- nothing to check (this gate's whole premise is "
            "that domain_manifest.yaml's HV domain is the authoritative "
            "HV net set)"
        )
    return list(hv_nets)


def check_hv_net_coverage(hv_nets: list[str], net_assignments: dict[str, Any]) -> list[str]:
    """Return the sorted list of HV-domain nets with no entry in
    ``net_assignments`` (``TEMPER_NET_ASSIGNMENTS``)."""
    return sorted(n for n in hv_nets if n not in net_assignments)


# ---------------------------------------------------------------------------
# Property 2: netclass rule coverage
# ---------------------------------------------------------------------------


def load_kicad_pro_classes(kicad_pro_path: Path) -> dict[str, str]:
    """Return {class_name: description} for every class in
    ``pcb/temper.kicad_pro``'s ``net_settings.classes``. ``description``
    is ``""`` when the field is absent or empty (both are "no real
    description" for this gate's purposes).

    Raises GateError (fail-closed) if the file is missing, not valid
    JSON, has no ``net_settings.classes`` list, that list is empty, or
    any entry has no (or an empty) ``name``.
    """
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

    result: dict[str, str] = {}
    for entry in classes:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise GateError(
                f"{kicad_pro_path} has a 'net_settings.classes' entry with "
                f"no 'name': {entry!r}"
            )
        result[str(entry["name"])] = str(entry.get("description") or "")
    return result


def declared_netclasses(
    net_classes: dict[str, Any], kicad_pro_classes: dict[str, str]
) -> set[str]:
    """The union of TEMPER_NET_CLASSES keys and every described,
    non-structural class declared in pcb/temper.kicad_pro -- see the
    module docstring's PROPERTY 2 section for the full justification.
    """
    declared = set(net_classes.keys())
    for name, description in kicad_pro_classes.items():
        if name in STRUCTURAL_KICAD_CLASSES:
            continue
        if description:
            declared.add(name)
    return declared


def positively_referenced_classes(dru_content: str) -> set[str]:
    """Every KiCad netclass name that appears as the right-hand side of a
    POSITIVE ``A.NetClass == 'X'`` / ``B.NetClass == 'X'`` equality test
    anywhere in the rendered ``.kicad_dru`` content. A class mentioned
    only via ``!=`` (exclusion) does not count -- see the module
    docstring for why that is not "real coverage".
    """
    return set(_NETCLASS_EQ_RE.findall(dru_content))


def check_netclass_rule_coverage(
    declared: set[str],
    kicad_class_name_fn: Callable[[str], str],
    referenced: set[str],
) -> list[str]:
    """Return the sorted list of declared (Python-key) netclass names
    whose KiCad name has zero positive rule references."""
    return sorted(
        py_key for py_key in declared if kicad_class_name_fn(py_key) not in referenced
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    hv_nets_checked: int = 0
    unclassified_hv_nets: list[str] = field(default_factory=list)
    declared_netclasses_checked: int = 0
    classes_with_no_rules: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def _default_live_inputs() -> tuple[dict[str, Any], dict[str, Any], str, Callable[[str], str]]:
    """Import the real, live TEMPER_NET_CLASSES / TEMPER_NET_ASSIGNMENTS /
    generated DRU content / kicad_class_name from this repo's own
    packages. Raises GateError (fail-closed) if the environment is not
    synced (mirrors ``check_rust_drc_presence.py``'s treatment of an
    unimportable extension as a gate error, not a silent skip).
    """
    try:
        from temper_placer.core.design_rules import (  # noqa: PLC0415
            TEMPER_NET_ASSIGNMENTS,
            TEMPER_NET_CLASSES,
        )
    except ImportError as e:
        raise GateError(
            "could not import temper_placer.core.design_rules -- is the "
            f"environment synced (`uv sync`)? ({e})"
        ) from e

    try:
        from generate_kicad_dru import generate_dru, kicad_class_name  # noqa: PLC0415
    except ImportError as e:
        raise GateError(f"could not import scripts/generate_kicad_dru.py: {e}") from e

    dru_content = generate_dru()
    return dict(TEMPER_NET_CLASSES), dict(TEMPER_NET_ASSIGNMENTS), dru_content, kicad_class_name


def run(
    manifest_path: Path,
    kicad_pro_path: Path,
    net_classes: dict[str, Any] | None = None,
    net_assignments: dict[str, Any] | None = None,
    dru_content: str | None = None,
    kicad_class_name_fn: Callable[[str], str] | None = None,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation' | 'tool_error'.

    ``net_classes`` / ``net_assignments`` / ``dru_content`` /
    ``kicad_class_name_fn`` default to the real, live values imported from
    this repo's own packages -- tests override any subset of them to
    construct a mutation (an unclassified net, a class with no rules)
    without needing a second real copy of the package installed.
    """
    report = Report()

    live_needed = (
        net_classes is None
        or net_assignments is None
        or dru_content is None
        or kicad_class_name_fn is None
    )
    if live_needed:
        try:
            (
                live_net_classes,
                live_net_assignments,
                live_dru_content,
                live_kicad_class_name,
            ) = _default_live_inputs()
        except GateError as e:
            report.tool_errors.append(str(e))
            return "tool_error", report
        net_classes = live_net_classes if net_classes is None else net_classes
        net_assignments = live_net_assignments if net_assignments is None else net_assignments
        dru_content = live_dru_content if dru_content is None else dru_content
        kicad_class_name_fn = (
            live_kicad_class_name if kicad_class_name_fn is None else kicad_class_name_fn
        )
    assert net_classes is not None
    assert net_assignments is not None
    assert dru_content is not None
    assert kicad_class_name_fn is not None

    try:
        hv_nets = load_hv_nets(manifest_path)
        kicad_pro_classes = load_kicad_pro_classes(kicad_pro_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    if not dru_content.strip():
        report.tool_errors.append(
            "scripts/generate_kicad_dru.py's generate_dru() produced empty "
            "output -- vacuous run, not a clean pass"
        )
        return "tool_error", report

    declared = declared_netclasses(net_classes, kicad_pro_classes)
    if not declared:
        report.tool_errors.append(
            "zero declared netclasses discovered across TEMPER_NET_CLASSES "
            f"and {kicad_pro_path} -- vacuous run, not a clean pass"
        )
        return "tool_error", report

    report.hv_nets_checked = len(hv_nets)
    report.declared_netclasses_checked = len(declared)

    report.unclassified_hv_nets = check_hv_net_coverage(hv_nets, net_assignments)

    referenced = positively_referenced_classes(dru_content)
    report.classes_with_no_rules = check_netclass_rule_coverage(
        declared, kicad_class_name_fn, referenced
    )

    if report.unclassified_hv_nets or report.classes_with_no_rules:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "HV netclass coverage gate -- "
        f"{report.hv_nets_checked} HV-domain net(s) checked against "
        "TEMPER_NET_ASSIGNMENTS, "
        f"{report.declared_netclasses_checked} declared netclass(es) "
        "checked against scripts/generate_kicad_dru.py's generated rules"
    )

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")

    print(
        f"\n=== PROPERTY 1: UNCLASSIFIED HV NETS: {len(report.unclassified_hv_nets)} ==="
    )
    for net in report.unclassified_hv_nets:
        print(
            f"  VIOLATION net {net!r} is declared under elec/domain_manifest.yaml's "
            "HV domain but has NO entry in TEMPER_NET_ASSIGNMENTS -- it silently "
            "falls through to DesignRules' LV default clearance/creepage"
        )

    print(
        f"\n=== PROPERTY 2: NETCLASSES WITH NO RULES: {len(report.classes_with_no_rules)} ==="
    )
    for cls in report.classes_with_no_rules:
        print(
            f"  VIOLATION netclass {cls!r} is a declared netclass (TEMPER_NET_CLASSES "
            "and/or pcb/temper.kicad_pro) but scripts/generate_kicad_dru.py's "
            "generated output contains zero rules positively matching "
            f"NetClass == {cls!r} -- this class enforces nothing for any net "
            "assigned to it"
        )

    if state == "clean":
        print("\nHV netclass coverage gate passed")
    elif state == "violation":
        print(
            f"\nFAILED -- {len(report.unclassified_hv_nets)} unclassified HV net(s), "
            f"{len(report.classes_with_no_rules)} netclass(es) with no rules"
        )
    else:
        print(
            "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--kicad-pro", type=Path, default=DEFAULT_KICAD_PRO)
    args = parser.parse_args()

    state, report = run(args.manifest, args.kicad_pro)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### HV Netclass Coverage Gate: {state}\n")
            f.write(
                f"- HV-domain nets checked: {report.hv_nets_checked}\n"
                f"- Unclassified HV nets: {len(report.unclassified_hv_nets)}\n"
                f"- Declared netclasses checked: {report.declared_netclasses_checked}\n"
                f"- Netclasses with no rules: {len(report.classes_with_no_rules)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )
            if report.unclassified_hv_nets:
                f.write("\nUnclassified HV nets:\n")
                for net in report.unclassified_hv_nets:
                    f.write(f"- `{net}`\n")
            if report.classes_with_no_rules:
                f.write("\nNetclasses with no rules:\n")
                for cls in report.classes_with_no_rules:
                    f.write(f"- `{cls}`\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
