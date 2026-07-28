#!/usr/bin/env python3
"""Generate pcb/temper.kicad_dru from TEMPER_NET_CLASSES in design_rules.py.

Usage (from repo root):
    uv run python scripts/generate_kicad_dru.py
"""

from pathlib import Path

from temper_placer.core.design_rules import TEMPER_NET_CLASSES

# Repo root is two levels up from this script (scripts/generate_kicad_dru.py)
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "pcb" / "temper.kicad_dru"

# ---------------------------------------------------------------------------
# Creepage IS NOW EMITTED as a real KiCad DRC constraint (2026-07-28) --
# this generator previously had no creepage constraint type at all (only
# clearance and track_width), so every creepage figure established for this
# board was enforced solely by check_isolation_keepout.py's straight-line
# corridor approximation -- a documented sufficient-but-not-necessary bound,
# not the fab-authoritative KiCad DRC check. It is not a gap anymore.
#
# kicad-cli 10.0.4 DOES implement a `creepage` constraint
# (CREEPAGE_CONSTRAINT / DRCE_CREEPAGE), confirmed two independent ways:
# (1) against kicad-source-mirror @ the 10.0.4 tag itself --
#     pcbnew/drc/drc_rule.h's DRC_CONSTRAINT_T enum, the `T_creepage` keyword
#     mapping in pcbnew/drc/drc_rule_parser.cpp, and a dedicated, registered
#     test provider, pcbnew/drc/drc_test_provider_creepage.cpp
#     (`DRC_REGISTER_TEST_PROVIDER<DRC_TEST_PROVIDER_CREEPAGE>`) that runs a
#     real surface-path graph solver (CREEPAGE_GRAPH), not an alias for
#     clearance; (2) empirically, on an isolated kicad-cli 10.0.4 fixture:
#     a lone `(constraint creepage (min 999mm))` rule produced a real
#     `type: "creepage"` violation with a measured `actual` distance, and
#     adding a board slot between two pads at a fixed 5.0mm straight-line
#     gap changed the reported actual creepage from 5.0000mm to 41.0526mm --
#     proof this is a genuine path-around-obstacles solver, not a relabeled
#     clearance check. See docs/evidence/2026-07-28-drc-creepage-constraint.md.
#
# Reinforced creepage at Pollution Degree 2 (IEC 60335-1 clause 29.2.3 x
# Table 17 row iv, working voltage >250-400V, material group IIIa/IIIb):
# basic 4.0mm x2 = 8.0mm. This is the figure
# scripts/check_isolation_keepout.py's MIN_BARRIER_WIDTH_MM already enforces
# as this board's authoritative creepage decision at the board-construction
# level; PD3 (2 x 6.3mm = 12.6mm, IEC 60335-2-6 clause 29.2 Addition's
# default for this appliance class) is recorded here as the alternate
# candidate but NOT adopted -- resolving PD2-vs-PD3 is a separate, larger
# policy question this recovery does not settle.
#
# WHICH FIGURE TO EMIT: pinned to HV_CREEPAGE_PD2_MM, reusing -- not
# re-deciding -- the identical figure scripts/check_isolation_keepout.py
# already enforces for the same barrier, so the two enforcement points
# cannot silently diverge. If a human later resolves the PD2-vs-PD3 question
# in favor of PD3, change this ONE line to HV_CREEPAGE_PD3_MM and update
# scripts/check_isolation_keepout.py's MIN_BARRIER_WIDTH_MM to match in the
# same change.
HV_CREEPAGE_PD2_MM = 8.0
HV_CREEPAGE_PD3_MM = 12.6  # IEC 60335-2-6 cl. 29.2 Addition default; not adopted here
HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM

# KiCad uses "Ground" as the net-class name; our Python dict uses "GND"
KICAD_NAME_MAP = {
    "GND": "Ground",
}

_SEP = "# " + "=" * 66


def kicad_class_name(python_key: str) -> str:
    """Return the KiCad net-class name for a given Python dict key."""
    return KICAD_NAME_MAP.get(python_key, python_key)


def fmt_mm(value: float) -> str:
    """Format a float as a KiCad mm string (no trailing zeros beyond 4 dp)."""
    # Use up to 4 decimal places, strip unnecessary trailing zeros after the dot
    s = f"{value:.4f}".rstrip("0").rstrip(".")
    # Always keep at least one decimal digit so "3" becomes "3.0"
    if "." not in s:
        s += ".0"
    return f"{s}mm"


def generate_dru() -> str:
    """Return the full contents of the KiCad DRU file as a string."""
    lines: list[str] = []

    # KiCad custom design rules format header
    lines.append("# Custom Design Rules for Temper Induction Heater")
    lines.append("# IEC 60335-1 / IEC 60664-1 compliant")
    lines.append("#")
    lines.append("# IMPORTANT: This board REQUIRES conformal coating for safety!")
    lines.append(
        "# Without coating, TO-247 packages violate IEC 60664-1 clearances."
    )
    lines.append(
        "# CREEPAGE IS ENFORCED HERE (2026-07-28): kicad-cli 10.0.4 supports a"
        " real"
    )
    lines.append(
        "# `creepage` constraint (confirmed against kicad-source-mirror @"
        " 10.0.4 and"
    )
    lines.append(
        "# empirically -- see docs/evidence/2026-07-28-drc-creepage-"
        "constraint.md). RULES"
    )
    lines.append(
        f"# 2 and 4 below enforce {fmt_mm(HV_CREEPAGE_ENFORCED_MM)} reinforced"
        " creepage across the"
    )
    lines.append(
        "# AC-Mains/HighVoltage <-> everything-else boundary, in addition to"
        " their"
    )
    lines.append(
        "# existing clearance figures. The pollution-degree question (PD2"
        " 8.0mm vs"
    )
    lines.append(
        "# PD3 12.6mm) is UNRESOLVED and this file does not resolve it --"
        " see"
    )
    lines.append(
        "# HV_CREEPAGE_ENFORCED_MM's own comment in this script for which"
        " figure is"
    )
    lines.append(
        "# currently pinned, why, and how to change it in one line once a"
        " human"
    )
    lines.append(
        "# settles the question. `scripts/check_isolation_keepout.py`"
        " remains the"
    )
    lines.append(
        "# other, independent creepage enforcement point on this board (a"
        " conservative"
    )
    lines.append(
        "# straight-line-corridor sufficient bound, not a surface-path"
        " measure); this"
    )
    lines.append(
        "# generator's new rules are the fab-authoritative KiCad DRC path,"
        " and they now"
    )
    lines.append(
        "# agree on the same pinned figure. See"
        " docs/evidence/2026-07-28-drc-creepage-constraint.md"
    )
    lines.append("# for the full derivation.")
    lines.append("#")
    lines.append(
        "# Generated by scripts/generate_kicad_dru.py"
        " -- do not edit by hand."
    )
    lines.append("")
    lines.append("(version 1)")
    lines.append("")

    # -------------------------------------------------------------------------
    # Static rules: same-footprint and fine-pitch exceptions
    # -------------------------------------------------------------------------
    lines.append(_SEP)
    lines.append("# RULE 1: Allow reduced clearance within same footprint")
    lines.append(
        "# This handles TO-247, SOT-23, QFN packages"
        " where pad pitch < net class clearance"
    )
    lines.append("#")
    lines.append(
        "# CONDITION FIX (2026-07-28, recovered from the stranded"
        " place-and-route branch): A.Footprint == B.Footprint never binds --"
    )
    lines.append(
        "# \"Footprint\" is not a property KiCad's rule engine registers on"
        " Pad, so this rule silently matched zero pad pairs. Worse: an"
    )
    lines.append(
        "# earlier rule referencing this undefined property was observed to"
        " suppress evaluation of LATER rules' constraints for unrelated pad"
    )
    lines.append(
        "# pairs (confirmed empirically while recovering the creepage"
        " constraint below -- a same-footprint HV/LV fixture with this"
    )
    lines.append(
        "# condition present upstream of \"HV to LV\" silently zeroed the"
        " creepage violation that same fixture produces when this rule is"
    )
    lines.append(
        "# absent or fixed). Replaced with A.Reference == B.Reference, a"
        " property that does resolve. Also added a cross-domain guard,"
    )
    lines.append(
        "# A.NetClass == B.NetClass, so the same-footprint relaxation does"
        " not apply across an isolator's own HV/SELV barrier for a"
    )
    lines.append(
        "# component with both sides on one footprint reference. NetClass is"
        " a necessary-but-not-sufficient proxy for domain, not a full fix --"
    )
    lines.append(
        "# see docs/evidence/2026-07-28-drc-rule1-netclass-redo.md."
    )
    lines.append(_SEP)
    lines.append('(rule "Same footprint pads"')
    lines.append(
        "   (condition \"A.Reference == B.Reference"
        " && A.NetClass == B.NetClass\")"
    )
    lines.append("   (constraint clearance (min 0.1mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 1a: Fine-pitch IC pads (QFN, BGA with 0.4mm pitch)")
    lines.append(
        "# Same condition fix and cross-domain guard as RULE 1 above."
        " A.Attribute is ALSO not a registered KiCad property -- it"
    )
    lines.append(
        "# registers this pad field as \"Pad Type\", not \"Attribute\", so"
        " that half of the condition never bound either. Replaced with"
    )
    lines.append("# A.Pad_Type == 'SMD'.")
    lines.append(_SEP)
    lines.append('(rule "Fine pitch IC pads"')
    lines.append(
        "   (condition \"A.Type == 'Pad' && A.Pad_Type == 'SMD'"
        " && B.Type == 'Pad' && B.Pad_Type == 'SMD'"
        " && A.Reference == B.Reference"
        " && A.NetClass == B.NetClass\")"
    )
    lines.append("   (constraint clearance (min 0.1mm))")
    lines.append(")")
    lines.append("")

    # -------------------------------------------------------------------------
    # Inter-class clearance rules (static constants — derived from IEC standards
    # and physical package constraints, not from TEMPER_NET_CLASSES directly)
    # -------------------------------------------------------------------------
    lines.append(_SEP)
    lines.append("# RULE 2: AC Mains isolation - 6mm to everything except itself")
    lines.append("# IEC 60335-1 basic insulation for 240V AC")
    lines.append("#")
    lines.append(
        "# CREEPAGE ADDED (2026-07-28): kicad-cli 10.0.4 supports a real"
        " `creepage`"
    )
    lines.append(
        "# constraint (see the HV_CREEPAGE_ENFORCED_MM comment near the top"
        " of this"
    )
    lines.append(
        "# script for the full derivation, the PD2/PD3 pin, and the"
        " kicad-cli support"
    )
    lines.append(
        "# evidence). This is the fab-authoritative DRC check for the"
        " reinforced"
    )
    lines.append(
        "# mains<->LV creepage requirement this net-class pair represents;"
        " it did not"
    )
    lines.append("# exist in the generated file before this change.")
    lines.append(_SEP)
    lines.append('(rule "AC Mains to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'ACMains'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'HighVoltage'\")"
    )
    lines.append("   (constraint clearance (min 6.0mm))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append(
        "# RULE 3: AC Mains to High Voltage - 3mm"
        " (both isolated from earth)"
    )
    lines.append(
        "# Reduced clearance since both are on same side of isolation barrier"
    )
    lines.append(_SEP)
    lines.append('(rule "AC Mains to HV"')
    lines.append(
        "   (condition \"A.NetClass == 'ACMains'"
        " && B.NetClass == 'HighVoltage'\")"
    )
    lines.append("   (constraint clearance (min 3.0mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 4: High Voltage DC bus - 2mm to LV")
    lines.append("# 400V DC bus after rectification")
    lines.append(
        "# NOTE: IEC 60664-1 at 400V working voltage may require"
        " 3.0mm+ clearance -- verify before HV bring-up"
    )
    lines.append("#")
    lines.append(
        "# CREEPAGE ADDED (2026-07-28): same rationale as RULE 2 above --"
        " see"
    )
    lines.append(
        "# HV_CREEPAGE_ENFORCED_MM's comment near the top of this script."
        " This is the"
    )
    lines.append(
        "# other half of the mains<->LV / HV<->LV boundary"
        " scripts/check_isolation_keepout.py"
    )
    lines.append(
        "# already enforces at the board-construction level; this rule"
        " now enforces the"
    )
    lines.append("# same figure at the fab-authoritative KiCad DRC level.")
    lines.append(_SEP)
    lines.append('(rule "HV to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltage'"
        " && B.NetClass != 'HighVoltage'"
        " && B.NetClass != 'ACMains'\")"
    )
    lines.append("   (constraint clearance (min 2.0mm))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 5: High Voltage internal - relaxed for same footprint")
    lines.append("# TO-247 IGBTs have 5.45mm pin pitch (1.95mm edge-to-edge)")
    lines.append("#")
    lines.append("# WARNING: This violates IEC 60664-1 PD2 (needs 2.0mm for 400V)")
    lines.append(
        "# REQUIRES: Conformal coating to achieve PD1 (needs 0.8mm for 400V)"
    )
    lines.append(_SEP)
    lines.append('(rule "HV internal same footprint"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltage'"
        " && B.NetClass == 'HighVoltage'"
        " && A.insideCourtyard(B.Reference)\")"
    )
    lines.append("   (constraint clearance (min 1.5mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 6: Gate drive signals near HV - 0.5mm minimum")
    lines.append("# Gate resistors placed close to IGBTs")
    lines.append(_SEP)
    lines.append('(rule "GateDrive near HV"')
    lines.append(
        "   (condition \"A.NetClass == 'GateDrive'"
        " && B.NetClass == 'HighVoltage'\")"
    )
    lines.append("   (constraint clearance (min 0.5mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 7: Power nets internal - allow SOT-23 pitch")
    lines.append(_SEP)
    lines.append('(rule "Power internal same footprint"')
    lines.append(
        "   (condition \"A.NetClass == 'Power'"
        " && B.NetClass == 'Power'"
        " && A.insideCourtyard(B.Reference)\")"
    )
    lines.append("   (constraint clearance (min 0.2mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 8: Ground to everything - standard clearance")
    lines.append("# GND is a reference, not a hazard")
    lines.append(_SEP)
    lines.append('(rule "Ground clearance"')
    lines.append(
        "   (condition \"A.NetClass == 'Ground' || B.NetClass == 'Ground'\")"
    )
    lines.append("   (constraint clearance (min 0.15mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 9: USB differential pair - tight coupling")
    lines.append(_SEP)
    lines.append('(rule "USB differential"')
    lines.append(
        "   (condition \"A.NetClass == 'HighSpeed'"
        " && B.NetClass == 'HighSpeed'\")"
    )
    lines.append("   (constraint clearance (min 0.1mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 10: Default routing clearance")
    lines.append("# Standard 0.2mm for signal traces")
    lines.append(_SEP)
    lines.append('(rule "Default routing"')
    lines.append("   (condition \"A.Type == 'Track' || B.Type == 'Track'\")")
    lines.append("   (constraint clearance (min 0.2mm))")
    lines.append(")")
    lines.append("")

    # -------------------------------------------------------------------------
    # Per-class trace-width rules generated from TEMPER_NET_CLASSES
    # -------------------------------------------------------------------------
    lines.append(_SEP)
    lines.append(
        "# TRACE WIDTH RULES"
        " (generated from TEMPER_NET_CLASSES in design_rules.py)"
    )
    lines.append(_SEP)
    lines.append("")

    # Emit in a stable order (same as definition order in design_rules.py)
    class_order = [
        "ACMains",
        "HighVoltage",
        "FinePitch",
        "Power",
        "GateDrive",
        "GND",
        "HighSpeed",
        "Signal",
        "HighCurrent",
    ]

    for py_key in class_order:
        nc = TEMPER_NET_CLASSES[py_key]
        kicad_name = kicad_class_name(py_key)
        width_str = fmt_mm(nc.trace_width)
        rule_label = f"{kicad_name} trace width"
        cond = f"A.Type == 'Track' && A.NetClass == '{kicad_name}'"
        lines.append(f'(rule "{rule_label}"')
        lines.append(f'   (condition "{cond}")')
        lines.append(f"   (constraint track_width (min {width_str}))")
        lines.append(")")
        lines.append("")

    # -------------------------------------------------------------------------
    # Hole clearance rules (static)
    # -------------------------------------------------------------------------
    lines.append(_SEP)
    lines.append("# HOLE CLEARANCE RULES")
    lines.append(_SEP)
    lines.append("")
    lines.append('(rule "Via hole clearance"')
    lines.append("   (constraint hole_clearance (min 0.25mm))")
    lines.append(")")
    lines.append("")
    lines.append('(rule "PTH hole to hole"')
    lines.append("   (constraint hole_to_hole (min 0.5mm))")
    lines.append(")")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    content = generate_dru()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {len(content.splitlines())} lines to {OUTPUT_PATH}")
    print()
    print(content)


if __name__ == "__main__":
    main()
