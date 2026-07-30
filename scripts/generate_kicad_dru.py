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
# basic 4.0mm x2 = 8.0mm.
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
HV_CREEPAGE_PD3_MM = 12.6  # settled 2026-07-30 per IEC 60335-2-6 cl. 29.2 Addition

# ---------------------------------------------------------------------------
# Creepage IS NOW EMITTED as a real KiCad DRC constraint (2026-07-28) --
# this used to be a documented, unenforced gap ("this generator has no
# creepage constraint type today"). It is not a gap anymore.
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
# WHICH FIGURE TO EMIT: the PD2 (8.0mm) vs PD3 (12.6mm) question above was
# resolved on 2026-07-30: IEC 60335-2-6 clause 29.2 makes PD3 the default
# microenvironment for cooking appliances, and this project's mechanical
# evidence does not earn the PD2 exception. See
# docs/evidence/2026-07-30-pollution-degree-determination.md. This constant
# mirrors check_isolation_keepout.py's MIN_BARRIER_WIDTH_MM so the two gates
# enforce the same safety figure.
#
# If a human resolves PD3 (or the board's physical slot geometry is
# re-targeted for it), change this ONE line to HV_CREEPAGE_PD3_MM -- and
# change scripts/check_isolation_keepout.py's MIN_BARRIER_WIDTH_MM to match
# in the same change, so the two gates never enforce two different figures
# for the same requirement.
HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM

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
        "# PD3 12.6mm) is SETTLED as of 2026-07-30; PD3 governs this "
        "cooking appliance. See"
    )
    lines.append(
        "# docs/evidence/2026-07-30-pollution-degree-determination.md. "
        "`scripts/"
    )
    lines.append(
        "# check_isolation_keepout.py` remains the other independent "
        "creepage gate."
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
        " docs/evidence/2026-07-28-creepage-"
    )
    lines.append("# determination-brainstorm.md for the full clause-cited derivation.")
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
    lines.append("#")
    lines.append(
        "# CONDITION FIX (2026-07-28, redo): A.Footprint == B.Footprint never"
        " binds -- \"Footprint\" is not a property KiCad's PROPERTY_MANAGER"
    )
    lines.append(
        "# registers on Pad or Footprint (confirmed against pcbnew/pad.cpp"
        " and pcbnew/footprint.cpp at kicad-cli 10.0.4/10.0.5), so this rule"
    )
    lines.append(
        "# silently matched zero pad pairs, on the fixture AND on the real"
        " board. Replaced the same-footprint-instance test with"
    )
    lines.append(
        "# A.Reference == B.Reference, the same construction already"
        " confirmed to bind for Rules 5/7 (see"
    )
    lines.append(
        "# docs/evidence/2026-07-28-drc-courtyard-condition-fix.md) and"
        " directly measured against pcb/temper.kicad_pcb to produce 214"
    )
    lines.append(
        "# violations as a lone condition at a 999mm threshold (see"
        " docs/evidence/2026-07-28-drc-rule1-netclass-redo.md)."
    )
    lines.append("#")
    lines.append(
        "# CROSS-DOMAIN GUARD (new): the bare same-footprint test is too"
        " broad on its own -- several declared isolators in"
    )
    lines.append(
        "# elec/domain_manifest.yaml (the gate driver, the aux supply, the"
        " Y-cap, the relays) have HV-side and SELV-side pins on the SAME"
    )
    lines.append(
        "# footprint instance, and this rule must never grant THOSE pin"
        " pairs a manufacturability allowance meant for a single package's"
    )
    lines.append(
        "# own tight pin pitch. KiCad's rule language has no direct notion"
        " of \"safety domain\" -- domain membership lives in"
    )
    lines.append(
        "# elec/domain_manifest.yaml, which a static per-pad kicad-cli rule"
        " cannot reference. A.NetClass == B.NetClass is the finest dynamic"
    )
    lines.append(
        "# proxy KiCad actually offers: NetClass, unlike Footprint, IS a"
        " specially-handled property that resolves correctly (measured:"
    )
    lines.append(
        "# 499 violations as a lone condition at 999mm -- see the evidence"
        " doc). Net class is not a perfect stand-in for safety domain --"
    )
    lines.append(
        "# it is a NECESSARY but not SUFFICIENT proxy, and the evidence doc"
        " documents one measured real-board counterexample (U7, the"
    )
    lines.append(
        "# UCC21550 gate driver: its GateDrive netclass spans both the"
        " primary-side PWM input pins and the secondary-side gate-output"
    )
    lines.append(
        "# pins across its own reinforced-isolation barrier) where same-"
        "NetClass does not imply same-domain. Reported, not fixed here --"
    )
    lines.append(
        "# fixing it means re-partitioning the GateDrive net class itself,"
        " which is a design_rules.py/elec modeling decision out of this"
    )
    lines.append(
        "# generator's scope, not a DRC-rule-syntax defect. Still a strict"
        " improvement over the previous always-dead condition and over a"
    )
    lines.append(
        "# hardcoded literal-net-name exclusion (which reproduces the exact"
        " failure mode -- an unnoticed net rename orphaning the rule -- that"
    )
    lines.append(
        "# produced the +340V_BUS defect this task is named after)."
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
        "# Same condition-fix and same cross-domain guard as RULE 1 above --"
        " see that rule's comment."
    )
    lines.append("#")
    lines.append(
        "# SECOND CONDITION FIX (2026-07-28, redo): A.Attribute is ALSO not a"
        " registered KiCad property -- confirmed against pcbnew/pad.cpp at"
    )
    lines.append(
        "# kicad-cli 10.0.4/10.0.5, which registers this pad field under the"
        " display name \"Pad Type\" (PROPERTY_ENUM<PAD, PAD_ATTRIB>), not"
    )
    lines.append(
        "# \"Attribute\". KiCad's rule compiler looks up properties by exact"
        " display name (underscores in the rule field become spaces before"
    )
    lines.append(
        "# the lookup), so A.Attribute resolved to nothing and this half of"
        " the condition never bound either -- a third, independent instance"
    )
    lines.append(
        "# of the same undefined-property failure class as A.Footprint"
        " (see docs/evidence/2026-07-28-drc-rule1-netclass-redo.md). Replaced"
    )
    lines.append(
        "# with A.Pad_Type == 'SMD' (measured to bind: 483 matches as a lone"
        " condition at a 999mm threshold on the real board, vs. 0 for"
    )
    lines.append(
        "# A.Attribute == 'SMD')."
    )
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
    lines.append("#")
    lines.append(
        "# BLACKLIST-COMPLETENESS FIX (2026-07-30): GateDriveHV and "
        "HighVoltageIsolated are the same physical HV domain as HighVoltage."
    )
    lines.append(
        "# Excluding them prevents same-domain pairs from being treated as "
        "genuine HV-to-LV creepage crossings. See the measured triage in "
        "docs/evidence/2026-07-30-creepage-205-triage.md."
    )
    lines.append(_SEP)
    lines.append('(rule "AC Mains to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'ACMains'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'HighVoltage'"
        " && B.NetClass != 'GateDriveHV'"
        " && B.NetClass != 'HighVoltageIsolated'"
        " && B.NetClass != 'HighCurrent'\")"
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
    lines.append("# GateDriveHV and HighVoltageIsolated are excluded because "
                 "they share the HV domain; see the 2026-07-30 triage.")
    lines.append(_SEP)
    lines.append('(rule "HV to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltage'"
        " && B.NetClass != 'HighVoltage'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'GateDriveHV'"
        " && B.NetClass != 'HighVoltageIsolated'"
        " && B.NetClass != 'HighCurrent'\")"
    )
    lines.append("   (constraint clearance (min 2.0mm))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append(
        "# RULE 4a/4b: HighVoltageIsolated -- the gate-drive floating"
        " bootstrap supply"
    )
    lines.append("#")
    lines.append(
        "# GAP CLOSED (2026-07-28): this netclass carried ZERO clearance or"
        " creepage"
    )
    lines.append(
        "# rules anywhere in this generator until now (grep -c"
        " HighVoltageIsolated"
    )
    lines.append(
        "# scripts/generate_kicad_dru.py returned 0) -- the exact class RULE"
        " 1's own"
    )
    lines.append(
        "# cross-domain guard fix used to re-home U7's secondary bias nets"
        " (VSSA/VDDA,"
    )
    lines.append(
        "# hb.gate_hs.driver-p2/-p1-1) into, per"
        " docs/evidence/2026-07-28-drc-rule1-"
    )
    lines.append(
        "# netclass-redo.md sec 5. Moving those nets into a netclass that"
        " itself"
    )
    lines.append(
        "# enforced nothing left them with only KiCad's per-netclass"
        " baseline (6.0mm"
    )
    lines.append(
        "# clearance, from pcb/temper.kicad_pro's own"
        " net_settings.classes/packages/"
    )
    lines.append(
        "# temper-placer/configs/netclass_rules.yaml) and NO creepage"
        " protection at all."
    )
    lines.append("#")
    lines.append(
        "# WHAT THE CLASS ACTUALLY IS: elec/domain_manifest.yaml declares"
        " +5V_ISO,"
    )
    lines.append(
        "# VBOOT_H, VBOOT_L, hb.gate_hs.driver-p1-1 (VDDA) and"
        " hb.gate_hs.driver-p2"
    )
    lines.append(
        "# (VSSA) -- every net this project assigns to the"
        " HighVoltageIsolated"
    )
    lines.append(
        "# netclass -- as members of the SAME `HV` domain as ac_l/+170V_BUS/"
        "SW_NODE,"
    )
    lines.append(
        "# not a third, separate domain. \"Isolated\" here names a"
        " gate-driver-internal"
    )
    lines.append(
        "# galvanic barrier (the UCC21550's own primary/secondary split),"
        " not a"
    )
    lines.append(
        "# barrier this netclass's nets sit on the far side of relative to"
        " the rest of"
    )
    lines.append(
        "# HV -- they float WITH the switch node, one gate-drive-current"
        " resistor"
    )
    lines.append(
        "# downstream of GATE_HS/SW_NODE (see the redo doc's own tracing)."
        " That means"
    )
    lines.append(
        "# this class needs exactly the asymmetric treatment"
        " docs/evidence/2026-07-28-"
    )
    lines.append(
        "# hv-isolated-rules-and-creepage-triage.md sets out: REINFORCED"
        " separation from"
    )
    lines.append(
        "# the LV/SELV side (the real barrier), but only FUNCTIONAL"
        " separation from its"
    )
    lines.append(
        "# own HV/ACMains neighbours (same side of that barrier -- exactly"
        " the relationship"
    )
    lines.append(
        "# RULE 3 (\"AC Mains to HV\") already models for ACMains vs."
        " HighVoltage)."
    )
    lines.append("#")
    lines.append(
        "# 4a relaxes the pair to the same 2.0mm figure RULE 4 (\"HV to"
        " LV\") already"
    )
    lines.append(
        "# uses for intra-HV-domain separation -- a documented, deliberate"
        " reduction below"
    )
    lines.append(
        "# the 6.0mm per-netclass baseline that would otherwise apply,"
        " justified because"
    )
    lines.append(
        "# both sides sit on the same side of the reinforced barrier (same"
        " category of"
    )
    lines.append(
        "# reduction RULE 3 already makes, not a safety loosening -- see the"
        " evidence doc)."
    )
    lines.append(
        "# 4b is the real, new protection: reinforced clearance against"
        " every other"
    )
    lines.append(
        "# (LV/SELV) netclass, at the same 2.0mm figure RULE 4 uses for"
        " HighVoltage."
    )
    lines.append(
        "# CREEPAGE CLOSED (2026-07-28): the generator-wide creepage"
        " constraint (see"
    )
    lines.append(
        "# HV_CREEPAGE_ENFORCED_MM's own comment near the top of this"
        " script) now"
    )
    lines.append(
        "# applies here too. 4a stays clearance-only, matching RULE 3"
        " (\"AC Mains to"
    )
    lines.append(
        "# HV\") -- both are same-side-of-the-barrier reductions between"
        " two HV-domain"
    )
    lines.append(
        "# classes, not a creepage boundary. 4b, the real HV<->LV"
        " protection, now gets"
    )
    lines.append(
        "# the same reinforced creepage figure RULE 2 (\"AC Mains to LV\")"
        " and RULE 4"
    )
    lines.append(
        "# (\"HV to LV\") already enforce -- it is exactly that class of"
        " rule, just keyed"
    )
    lines.append("# on HighVoltageIsolated instead of ACMains/HighVoltage.")
    lines.append(_SEP)
    # Matches RULE 4's existing "HV to LV" clearance figure (this file,
    # unchanged) -- not a new number, just this class's share of it.
    _HV_ISOLATED_CLEARANCE_MM = 2.0
    lines.append('(rule "HighVoltageIsolated same side"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltageIsolated'"
        " && (B.NetClass == 'HighVoltage'"
        " || B.NetClass == 'ACMains'"
        " || B.NetClass == 'GateDriveHV'"
        " || B.NetClass == 'HighCurrent')\")"
    )
    lines.append(f"   (constraint clearance (min {fmt_mm(_HV_ISOLATED_CLEARANCE_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append('(rule "HighVoltageIsolated to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltageIsolated'"
        " && B.NetClass != 'HighVoltageIsolated'"
        " && B.NetClass != 'HighVoltage'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'GateDriveHV'"
        " && B.NetClass != 'HighCurrent'\")"
    )
    lines.append(f"   (constraint clearance (min {fmt_mm(_HV_ISOLATED_CLEARANCE_MM)}))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
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
    lines.append("#")
    lines.append(
        "# CONDITION FIX (2026-07-28): the same-footprint test used to be"
        " A.insideCourtyard(B.Reference), which does not match anything in"
    )
    lines.append(
        "# kicad-cli 10.0.4/10.0.5 -- intersectsCourtyard()'s argument is"
        " matched against a footprint reference/wildcard string, but the"
    )
    lines.append(
        "# dynamic B.Reference form (as opposed to a literal string) never"
        " binds, so this rule silently matched zero pad pairs. Replaced"
    )
    lines.append(
        "# with A.Reference == B.Reference, a direct property-equality test"
        " confirmed (kicad-cli 10.0.4, isolated fixture) to fire correctly:"
    )
    lines.append(
        "# see docs/evidence/2026-07-28-drc-courtyard-condition-fix.md."
    )
    lines.append(_SEP)
    lines.append('(rule "HV internal same footprint"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltage'"
        " && B.NetClass == 'HighVoltage'"
        " && A.Reference == B.Reference\")"
    )
    lines.append(f"   (constraint clearance (min {fmt_mm(HV_INTERNAL_CLEARANCE_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 6: Gate drive signals near HV - 0.5mm minimum")
    lines.append("# Gate resistors placed close to IGBTs")
    lines.append("#")
    lines.append(
        "# Split into two rules 2026-07-28 (R4) alongside the GateDrive ->"
        " GateDriveHV/GateDriveSELV class split -- a single condition"
    )
    lines.append(
        "# naming the old 'GateDrive' string would now match zero nets"
        " (silent, always-dead coverage; see docs/solutions/best-practices/"
    )
    lines.append(
        "# a-rule-that-matches-nothing-reads-as-coverage-2026-07-28.md)."
        " Both halves keep the original 0.5mm figure -- this unit changes"
    )
    lines.append(
        "# the class model, not the clearance value."
    )
    lines.append(_SEP)
    lines.append('(rule "GateDriveHV near HV"')
    lines.append(
        "   (condition \"A.NetClass == 'GateDriveHV'"
        " && B.NetClass == 'HighVoltage'\")"
    )
    lines.append("   (constraint clearance (min 0.5mm))")
    lines.append(")")
    lines.append("")
    lines.append('(rule "GateDriveSELV near HV"')
    lines.append(
        "   (condition \"A.NetClass == 'GateDriveSELV'"
        " && B.NetClass == 'HighVoltage'\")"
    )
    lines.append("   (constraint clearance (min 0.5mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 7: Power nets internal - allow SOT-23 pitch")
    lines.append("#")
    lines.append(
        "# CONDITION FIX (2026-07-28): same defect and same fix as RULE 5 --"
        " A.insideCourtyard(B.Reference) does not match anything in kicad-cli"
    )
    lines.append(
        "# 10.0.4/10.0.5; replaced with A.Reference == B.Reference. See"
        " docs/evidence/2026-07-28-drc-courtyard-condition-fix.md."
    )
    lines.append(_SEP)
    lines.append('(rule "Power internal same footprint"')
    lines.append(
        "   (condition \"A.NetClass == 'Power'"
        " && B.NetClass == 'Power'"
        " && A.Reference == B.Reference\")"
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
        # Split 2026-07-28 (R4): "GateDrive" no longer exists as a key in
        # TEMPER_NET_CLASSES -- both halves must be listed or this loop
        # KeyErrors.
        "GateDriveHV",
        "GateDriveSELV",
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
