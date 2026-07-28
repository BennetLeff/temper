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
# Coating qualification gate -- fail closed.
#
# This file used to relax the "HV internal same footprint" clearance rule
# (below) on the strength of a conformal coating that does not exist: it is
# absent from the BOM and the assembly process, and it also could not
# deliver the credit it was claimed to, even if applied. IEC 60664-3 cl. 4.3
# (the standard IEC 60335-1 Annex J delegates to) grants Pollution Degree 1
# only for a creepage path whose ENTIRE length -- both conductive parts and
# every spacing between them -- is covered. Measured in
# docs/evidence/2026-07-28-conformal-coating-pd1.md: 100.0% of the shortest
# HV<->PELV surface path lies under the component body for every declared
# isolator with a body outline, and a post-reflow coating cannot be shown to
# reach under a seated package (that document's own cl. 5.4 qualification
# coupon is a bare, uncoated board). Separately, the old comment's "0.8mm at
# PD1" figure matched no cell of Table 17: the PD1 column at row iv
# (>250-400V) is 1.0mm, and clearance at PD1 is not derived from Table 17 at
# all (see docs/evidence/2026-07-28-conformal-coating-pd1.md sec 3.1).
#
# COATING_QUALIFIED must remain False until a human has recorded, for every
# path this flag would relax: (1) a coating process in the BOM, (2) an
# IEC 60664-3 Annex J qualification report (clause 5's test regime), and
# (3) a per-path IEC 60664-3 cl. 4.3 coverage argument. This board has none
# of those today. Flipping this flag without also replacing the placeholder
# figures below with a real, cited determination is exactly the defect this
# gate exists to prevent, so it fails loudly instead of silently relaxing.
COATING_QUALIFIED = False

if COATING_QUALIFIED:
    raise NotImplementedError(
        "COATING_QUALIFIED=True is not implemented. Flipping this flag "
        "requires a real IEC 60664-3 Annex J qualification (BOM entry, "
        "clause-5 test report, and a per-path clause-4.3 coverage argument) "
        "plus the corrected PD1 figures substituted into this script -- not "
        "the unqualified 0.8mm this file previously asserted. See "
        "docs/evidence/2026-07-28-conformal-coating-pd1.md and "
        "docs/evidence/2026-07-28-drc-coating-failopen-fix.md."
    )

# Fail-closed reinforced clearance for the mains<->PELV barrier, uncoated.
# IEC 60335-1 clause 29.1: rated impulse voltage 1500V (120V nominal, OVC II,
# Table 15) -> Table 16 basic clearance 0.5mm at that step -> clause 29.1.3
# "next higher step" for reinforced -> 1.5mm nominal, PLUS clause 29.1's
# +0.5mm soldered-construction adder (this is a soldered PCB, one of the
# clause's own named examples) = 2.0mm. See
# docs/evidence/2026-07-28-creepage-determination-brainstorm.md sec 4 and
# docs/evidence/2026-07-28-conformal-coating-pd1.md sec 3, item 3.
HV_INTERNAL_CLEARANCE_MM = 2.0

# Reinforced creepage at Pollution Degree 2 (IEC 60335-1 clause 29.2.3 x
# Table 17 row iv, working voltage >250-400V, material group IIIa/IIIb):
# basic 4.0mm x2 = 8.0mm. NOT emitted as a KiCad rule below -- this
# generator has no creepage constraint type today (only clearance and
# track_width), so this figure is not enforced anywhere in the generated
# file. Recorded here so the gap is visible rather than silent.
#
# IEC 60335-2-6 clause 29.2 Addition makes Pollution Degree 3 the DEFAULT
# for this appliance class (cooking ranges/hobs); PD2 must be earned by
# showing the insulation is enclosed or unlikely to be exposed to pollution,
# which no document in this repo establishes today (docs/ENVIRONMENTAL_SPEC.md
# asserts PD2 with no citation, and docs/CHASSIS_AIRFLOW_DESIGN.md describes
# forced airflow through the compartment, which argues the other way). If
# PD3 stands, the reinforced creepage requirement is 2 x 6.3mm = 12.6mm, not
# 8.0mm. THIS IS FLAGGED, NOT RESOLVED: a human must settle the pollution
# degree of the macroenvironment before either number can be asserted as
# correct. See docs/evidence/2026-07-28-conformal-coating-pd1.md sec "Verdict"
# item and docs/evidence/2026-07-28-creepage-determination-brainstorm.md sec 5.
HV_CREEPAGE_PD2_MM = 8.0
HV_CREEPAGE_PD3_MM = 12.6  # flagged default per IEC 60335-2-6 cl. 29.2; UNRESOLVED

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
    lines.append("# NOTE: This board carries NO qualified conformal coating.")
    lines.append(
        "# No coating process exists in the BOM or assembly, and IEC 60664-3"
        " cl. 4.3"
    )
    lines.append(
        "# requires full-path coverage for any Pollution Degree 1 credit --"
        " measured,"
    )
    lines.append(
        "# 100.0% of every declared isolator's shortest HV<->PELV path lies"
        " under its"
    )
    lines.append(
        "# own component body and cannot be shown to be coated. This file"
        " therefore"
    )
    lines.append(
        "# enforces FAIL-CLOSED, uncoated clearance figures throughout. See"
    )
    lines.append("# docs/evidence/2026-07-28-conformal-coating-pd1.md.")
    lines.append("#")
    lines.append(
        "# TO-247 IGBT packages have a 1.95mm edge-to-edge internal pin gap"
        " (see RULE"
    )
    lines.append(
        "# 5 below); this is a package-geometry fact, not something this"
        " script or a"
    )
    lines.append(
        "# coating can fix. Expect this rule to now flag those packages --"
        " that is"
    )
    lines.append("# the correct, honest result of removing the prior relaxation.")
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
    lines.append(_SEP)
    lines.append('(rule "Same footprint pads"')
    lines.append(
        "   (condition \"A.insideCourtyard('*')"
        " && B.insideCourtyard('*')"
        " && A.Footprint == B.Footprint\")"
    )
    lines.append("   (constraint clearance (min 0.1mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 1a: Fine-pitch IC pads (QFN, BGA with 0.4mm pitch)")
    lines.append(_SEP)
    lines.append('(rule "Fine pitch IC pads"')
    lines.append(
        "   (condition \"A.Type == 'Pad' && A.Attribute == 'SMD'"
        " && B.Type == 'Pad' && B.Attribute == 'SMD'"
        " && A.Footprint == B.Footprint\")"
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
    lines.append(_SEP)
    lines.append('(rule "AC Mains to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'ACMains'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'HighVoltage'\")"
    )
    lines.append("   (constraint clearance (min 6.0mm))")
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
    lines.append(_SEP)
    lines.append('(rule "HV to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltage'"
        " && B.NetClass != 'HighVoltage'"
        " && B.NetClass != 'ACMains'\")"
    )
    lines.append("   (constraint clearance (min 2.0mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 5: High Voltage internal - same footprint")
    lines.append("# TO-247 IGBTs have 5.45mm pin pitch (1.95mm edge-to-edge)")
    lines.append("#")
    lines.append(
        "# FAIL-CLOSED: no conformal coating is qualified on this board, so"
        " no"
    )
    lines.append(
        "# coating-based relaxation is granted here. This constraint is the"
    )
    lines.append(
        "# uncoated reinforced clearance requirement -- IEC 60335-1 cl. 29.1:"
        " 1500V"
    )
    lines.append(
        "# rated impulse voltage (120V nominal, OVC II) -> Table 16 basic"
        " 0.5mm ->"
    )
    lines.append(
        "# cl. 29.1.3 next-higher-step reinforced 1.5mm, + cl. 29.1's +0.5mm"
    )
    lines.append(
        "# soldered-construction adder (this is a soldered PCB) = 2.0mm. See"
    )
    lines.append("# docs/evidence/2026-07-28-conformal-coating-pd1.md sec 3.")
    lines.append("#")
    lines.append(
        "# TO-247's 1.95mm edge-to-edge gap is BELOW this requirement. That"
        " is a real"
    )
    lines.append(
        "# violation this rule is now expected to report, not a bug in this"
        " rule --"
    )
    lines.append(
        "# a coating was never a valid fix for it (see"
        " docs/evidence/2026-07-28-"
    )
    lines.append(
        "# conformal-coating-pd1.md sec 4, TO-247/SOIC-16W case). Resolving"
        " it needs"
    )
    lines.append(
        "# a BOM/footprint/placement change, none of which this script"
        " performs."
    )
    lines.append(_SEP)
    lines.append('(rule "HV internal same footprint"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltage'"
        " && B.NetClass == 'HighVoltage'"
        " && A.insideCourtyard(B.Reference)\")"
    )
    lines.append(f"   (constraint clearance (min {fmt_mm(HV_INTERNAL_CLEARANCE_MM)}))")
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
