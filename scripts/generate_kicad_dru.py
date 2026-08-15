#!/usr/bin/env python3
"""Generate pcb/temper.kicad_dru from TEMPER_NET_CLASSES in design_rules.py.

Usage (from repo root):
    uv run python scripts/generate_kicad_dru.py
"""

import itertools
import re
from collections.abc import Iterable
from dataclasses import dataclass
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

# Reinforced creepage at Pollution Degree 3 (IEC 60335-1 clause 29.2.3 x
# Table 17 row iv, working voltage >250-400V, material group IIIa/IIIb):
# basic 6.3mm x2 = 12.6mm.
#
# IEC 60335-2-6 clause 29.2 Addition makes Pollution Degree 3 the default
# for this appliance class (cooking ranges/hobs); PD2 is earned only by a
# documented, gasketed PCB compartment outside the coil/heatsink airflow
# path, which is not built and is thermally counterproductive
# (docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md). The
# data-driven decision of 2026-08-15 (docs/evidence/2026-08-15-pd2-pd3-
# data-driven-decision.md) therefore enforces PD3/12.6mm as the governing
# bar: the as-built board is forced-air vented with no cover/gasket/
# partition, so 8.0mm was an unearned credit. PD2 remains as the explicit
# fallback should the sealed compartment ever be built and verified, so a
# future mechanical reclassification changes both points together rather
# than silently carrying the PD3 number.
HV_CREEPAGE_PD2_MM = 8.0  # fallback if a sealed compartment is ever built
HV_CREEPAGE_PD3_MM = 12.6

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
# WHICH FIGURE TO EMIT: PD3 is the enforced production target (the
# 2026-08-15 data-driven decision: PD3 governs the as-built, forced-air-
# vented, compartment-less board; see docs/evidence/2026-08-15-pd2-pd3-
# data-driven-decision.md), and it must remain aligned with
# check_isolation_keepout.py's MIN_BARRIER_WIDTH_MM. Both enforcement
# points therefore emit/enforce 12.6mm. The PD2 constant is retained as an
# explicit fallback so a future mechanical reclassification (a built, real
# sealed compartment) changes both points together rather than silently
# carrying the PD3 number.
HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM

# RULE 10's floor: the clearance every track-involving pair must hold when no
# stricter, more specific rule matches. This is the bar 503 of the heatsink
# candidate board's 505 `clearance` errors are measured against, so it is also
# the bar the router's own A* occupancy model has to reserve for. It was
# previously a bare "0.2mm" literal in the RULE 10 emitter while the router's
# fallback was separately hardcoded to 0.15mm in
# `router_v6/_pipeline_core.py` -- a 0.05mm gap between "what we route to" and
# "what we grade against" that cost +115 clearance errors on the heatsink
# candidate (docs/evidence/2026-08-12-clearance-congestion-band.md). Naming it
# lets `scripts/check_router_clearance_floor.py` assert the two agree.
#
# Value: `packages/temper-placer/configs/netclass_rules.yaml`'s
# `default_clearance_mm`, which is also `pcb/temper.kicad_pro`'s `Default`
# net-class clearance. All three must stay equal; the gate enforces it.
DEFAULT_ROUTING_CLEARANCE_MM = 0.2

# ---------------------------------------------------------------------------
# HV<->HV FUNCTIONAL creepage at the resonant-tank node (ADDED 2026-08-12).
#
# The three creepage constraints above (RULES 2, 4, 4b) all require ONE SIDE to
# be non-HV -- they dimension the reinforced mains/HV <-> LV/SELV barrier. Until
# this constant existed, NO rule in this file declared a creepage constraint for
# a pair where BOTH sides are HV, so the highest-voltage pair on the board --
# the resonant tank's cap<->coil junction against the DC bus rails -- was
# checked against no creepage requirement at all. Verified two ways in
# docs/evidence/2026-08-12-hv-clearance-adequacy.md sec 3.2: by rule inventory,
# and empirically (raising the HighVoltage netclass clearance to 20mm moves the
# clearance count 386 -> 499 but moves NO creepage count).
#
# THE FIGURE. This is FUNCTIONAL insulation (between conductive parts of
# different potential inside one circuit), so the governing table is IEC
# 60335-1 **Table 18**, "Minimum Creepage Distances for Functional Insulation"
# (clauses 29.2.4 and L-2) -- NOT Table 17 (basic insulation), which is what
# HV_CREEPAGE_PD2_MM above is derived from. Table 18 grants a real concession
# over Table 17, but only below 500 V working voltage; at and above 500 V the
# two tables are numerically identical. Full transcription of Table 18 and the
# side-by-side with Table 17: docs/evidence/2026-08-12-hv-hv-creepage-
# determination.md sec 3.1-3.2.
#
#   working voltage  570.5 Vrms  -> Table 18 band vi (>500 and <=800 V)
#   material group   IIIa/IIIb   (generic FR-4, CTI unstated; the repo-wide
#                                 assumption, and IEC 60335-1 merges IIIa/IIIb
#                                 into one column so the choice is immaterial)
#   pollution degree PD3         (the 2026-08-15 data-driven decision -- PD3
#                                 governs the as-built, forced-air-vented,
#                                 compartment-less board; see docs/evidence/
#                                 2026-08-15-pd2-pd3-data-driven-decision.md)
#   => 10.0mm  (PD2, the fallback, would be 6.3mm)
#
# The 570.5 Vrms is measured, not assumed: ngspice against the repo's own
# committed simulation/harness/nets/zvs_margin_sweep.cir, worst OCP-01-passing
# corner (L -10%, C -10%, 48 kHz), per-net table in
# docs/evidence/2026-08-12-hv-clearance-adequacy.md sec 2.3/3.2. Clause 3.1.3
# Note 2 ("working voltage takes into account resonant voltages") is what makes
# the resonant swing -- not the 340 V bus -- the number the table is indexed by.
#
# NOT ENFORCED-EQUAL TO HV_CREEPAGE_ENFORCED_MM ON PURPOSE. 12.6mm is a
# REINFORCED figure (Table 17 basic 6.3mm x2 per clause 29.2.3) for a pair that
# crosses the safety barrier. This pair does not cross it -- both sides are HV.
# Applying 12.6mm here would be the same false-positive shape as the
# GateDriveHV/HighVoltageIsolated cases documented in RULE 4's comment below
# (docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md): a
# same-domain pair charged a cross-barrier figure.
#
# PD2 CAVEAT, stated because this number will be read out of context.
# The 2026-08-15 data-driven decision (docs/evidence/2026-08-15-pd2-pd3-
# data-driven-decision.md) enforces PD3/10.0mm for the as-built
# construction; 6.3mm (PD2) remains a documented fallback should a sealed
# compartment ever be built and verified. Both constants are kept so a
# mechanical reclassification moves one line, exactly as
# HV_CREEPAGE_PD2_MM/PD3_MM above do.
#
# NOTE ON THE BLANK LINE BELOW -- it is load-bearing, not formatting.
# scripts/check_creepage_clearance_drift.py classifies each constant's
# insulation TIER by keyword-scanning the contiguous comment block directly
# above it, and a blank line ends that block
# (`_contiguous_comment_block_above`). The prose above deliberately discusses
# the 12.6mm reinforced figure and the 570.5 Vrms working voltage in order to
# explain why THIS constant is neither; without the break, those words would
# be read as this constant's OWN tier and put 10.0mm into a comparison family
# with 8.0mm/12.6mm, which is precisely the false equivalence the paragraph
# above exists to deny. With the break these three constants classify as
# tier-unspecified and are FLAGGED rather than compared -- the same treatment
# every TEMPER_NET_CLASSES entry already gets. Verified by running that gate
# before and after: it errors (exit 5) without the break and reports its
# normal pre-existing violations (exit 3) with it.

# Functional creepage floor for the resonant-tank node, in mm. Derivation,
# citation and pollution-degree caveat: see the block above.
HV_TANK_CREEPAGE_PD2_MM = 6.3  # fallback if a sealed compartment is ever built
HV_TANK_CREEPAGE_PD3_MM = 10.0

# Which of the two above is emitted. Deliberately NOT written as the bare
# `HV_TANK_CREEPAGE_ENFORCED_MM = HV_TANK_CREEPAGE_PD2_MM` alias that
# HV_CREEPAGE_ENFORCED_MM above uses, and the reason is worth recording rather
# than leaving as a stylistic oddity:
#
# scripts/check_creepage_clearance_drift.py treats a bare `NAME2 = NAME1` as a
# "selection alias" and then self-checks that the SELECTED constant sits in a
# comparable (metric, tier) family. It classifies tier by keyword-scanning the
# attached comment for reinforced/basic/working. This figure is FUNCTIONAL
# insulation (Table 18) -- a tier that gate does not model -- so it has no
# family, and the alias form makes the gate exit 5 ("GATE ERROR -- could not run
# a trustworthy check"), strictly worse than the exit 3 it already reports on
# main. Measured both ways.
#
# Adding "functional" to that gate's tier vocabulary was tried and REJECTED:
# measured against the pristine tree it also re-tags netclass_rules.yaml's
# HighVoltageIsolated clearance/creepage entries (whose `because` reads
# "reinforced separation to LV/SELV, functional-only to its own HV/ACMains
# neighbours") out of the reinforced families, shrinking [clearance/reinforced]
# from 4 members to 3 and [creepage/reinforced] from 10 to 9 and turning two
# real MISMATCH reports into OK ones. That is a loss of gate sensitivity, not a
# fix. Teaching that gate a functional tier properly -- so it discriminates "the
# value IS functional" from "the text mentions functional" -- is real work and
# belongs in its own change, not smuggled in under a creepage rule.
#
# The dict-lookup form below keeps the one-line PD switch, duplicates no
# literal, and reads to that gate as a non-literal expression (its UNRESOLVED
# bucket) rather than as an alias it must and cannot resolve.
_TANK_POLLUTION_DEGREE = "PD3"
HV_TANK_CREEPAGE_ENFORCED_MM = {
    "PD2": HV_TANK_CREEPAGE_PD2_MM,
    "PD3": HV_TANK_CREEPAGE_PD3_MM,
}[_TANK_POLLUTION_DEGREE]

# The net class carrying the resonant-tank node. Named once so every condition
# below that has to include or exclude it stays in sync -- the failure mode this
# guards against is the one RULE 4's own 2026-08-11 note describes, where a
# class was added to one side of one condition and silently inherited a
# cross-barrier figure everywhere else.
HV_TANK_CLASS = "HighVoltageTank"

# ADDED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-scoping.md):
# the mA-scale current-tier carve-out of HighVoltage (discharge bleed
# string, Q_high gate tap, U3's ZCD divider/opto-anode net, +15V_LS). Same
# voltage domain as HighVoltage -- everywhere this generator gives
# HighVoltage a same-side reduction or a reinforced-to-LV rule, this class
# needs the identical treatment, or a net moved into it would silently lose
# coverage it had while classed HighVoltage (the exact shape RULE 4c/5a's
# own comments already document and fixed once before, for HighVoltageTank).
# scripts/check_hv_netclass_coverage.py PROPERTY 2 fails closed if any
# declared class is added here without a positive NetClass == rule.
HV_SIGNAL_CLASS = "HighVoltageSignal"

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


# ---------------------------------------------------------------------------
# RULE PRECEDENCE (added 2026-08-12 -- see
# docs/evidence/2026-08-12-dru-rule-precedence.md).
#
# KiCad does NOT pick the most specific matching rule. Its own documentation
# (kicad-doc src/pcbnew/pcbnew_advanced.adoc, "Custom Design Rules") states:
#
#   "Rules are evaluated in reverse order, meaning the last rule in the file
#    is checked first. Once a matching rule is found for a given set objects
#    being tested, no further rules will be checked."
#   "The order of the two objects is not important because the design rule
#    checker will test both possible orderings."
#
# Confirmed empirically against this repo's own board on kicad-cli 10.0.5: a
# 0.001mm catch-all clearance rule appended LAST drops the measured clearance
# violation count 402 -> 71; the identical rule placed FIRST leaves it at 402.
#
# Consequence: a broad rule emitted after a narrow one silently REPLACES it.
# This file used to emit "Default routing" (0.2mm, condition
# "A.Type == 'Track' || B.Type == 'Track'") last, so 0.2mm superseded every
# cited 0.5-6.0mm HV/ACMains/HighVoltageIsolated safety bar on any pair
# involving a track. Three further instances existed (Ground clearance,
# GateDriveSELV near HV, HighVoltageIsolated same side).
#
# THE INVARIANT THIS FILE NOW ENFORCES: for every constraint type and every
# pair of items, the STRICTEST matching rule must be the one KiCad selects.
# That is achieved by emitting rules in increasing order of their `min` value
# per constraint type, which makes last-matching-wins numerically equivalent
# to strictest-wins. `order_rules_by_strictness()` does the reordering (the
# authored narrative order in the source below is left untouched -- only the
# emitted file is reordered), and `find_shadowing()` is a fail-closed guard
# that re-derives the winner for every rule pair over a finite world model
# and raises if any rule can still be overridden by a weaker one. Adding a
# new rule anywhere in this function is therefore safe: it is placed by
# value, and if it cannot be placed safely the generator fails loudly rather
# than emitting a file that silently disables a safety bar.
# ---------------------------------------------------------------------------

# Constraint types whose rules KiCad evaluates against a PAIR of items (and
# therefore tries in both A/B orderings). `track_width` is deliberately
# absent: it constrains a single track, KiCad binds only A, and there is no
# swapped evaluation -- verified on the real board, where 'HighVoltage trace
# width' (3.0mm) fires 127 times despite 'Power trace width' (1.0mm) being
# emitted after it, which could not happen if the two were paired.
PAIR_CONSTRAINT_TYPES = ("clearance", "creepage", "hole_clearance", "hole_to_hole")

_RULE_BLOCK_RE = re.compile(r'^\(rule "(?P<name>[^"]+)"$')
_CONDITION_RE = re.compile(r'^\s*\(condition "(?P<expr>.*)"\)\s*$')
_CONSTRAINT_RE = re.compile(r"^\s*\(constraint (?P<type>\w+) \(min (?P<value>[0-9.]+)mm\)\)\s*$")

# Item properties the condition analyser understands. A condition naming
# anything else cannot be reasoned about, so the guard refuses to certify the
# file rather than assuming the rule is harmless.
_SUPPORTED_PROPERTIES = ("NetClass", "Type", "Reference", "Pad_Type")

# Finite world model. `__unlisted__` stands for any net class not named by any
# rule and not declared in TEMPER_NET_CLASSES, so catch-alls are modelled
# honestly rather than only over the classes that happen to exist today.
_UNLISTED_NETCLASS = "__unlisted__"
_ITEM_TYPES = ("Track", "Pad", "Via", "Zone")
_PAD_TYPES = {
    "Pad": ("SMD", "Through-hole"),
    "Track": ("",),
    "Via": ("",),
    "Zone": ("",),
}


class UnsupportedConditionError(ValueError):
    """A rule condition uses syntax the precedence analyser cannot model.

    Raised rather than skipped: an unanalysable condition means the shadowing
    guard cannot certify the file, and a guard that quietly ignores the rules
    it does not understand is exactly the kind of vacuous check this repo
    treats as a defect.
    """


class RuleShadowingError(RuntimeError):
    """A rule in the emitted file can be overridden by a weaker later rule."""


class RulePrecedenceCycleError(RuntimeError):
    """No emission order can satisfy strictest-wins for every constraint type.

    Reached only when two rules that overlap disagree about their relative
    order across two different constraint types (rule X must precede Y for
    clearance but follow it for creepage). There is no automatic answer; a
    human has to split or re-scope one of the rules.
    """


@dataclass(frozen=True)
class DruRule:
    """One ``(rule ...)`` block parsed out of an emitted .kicad_dru."""

    name: str
    condition: str | None
    constraints: dict[str, float]
    text: str
    index: int


def _parse_rules(content: str) -> list[DruRule]:
    """Parse every ``(rule ...)`` block out of *content*, in file order."""
    rules: list[DruRule] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        match = _RULE_BLOCK_RE.match(lines[i])
        if match is None:
            i += 1
            continue
        start = i
        condition: str | None = None
        constraints: dict[str, float] = {}
        i += 1
        while i < len(lines) and lines[i] != ")":
            cond = _CONDITION_RE.match(lines[i])
            if cond is not None:
                condition = cond.group("expr")
            constraint = _CONSTRAINT_RE.match(lines[i])
            if constraint is not None:
                constraints[constraint.group("type")] = float(constraint.group("value"))
            i += 1
        block = "\n".join(lines[start : i + 1])
        rules.append(
            DruRule(
                name=match.group("name"),
                condition=condition,
                constraints=constraints,
                text=block,
                index=len(rules),
            )
        )
        i += 1
    return rules


def _compile_condition(condition: str | None):
    """Translate a KiCad rule condition into a Python predicate.

    Only the small expression language this file actually emits is accepted
    (property equality/inequality against string literals, combined with
    ``&&``/``||`` and parentheses). Anything else raises
    :class:`UnsupportedConditionError` -- see its docstring for why.
    """
    if condition is None:
        return compile("True", "<dru-condition>", "eval")

    remainder = condition
    for side in ("A", "B"):
        for prop in _SUPPORTED_PROPERTIES:
            remainder = remainder.replace(f"{side}.{prop}", f"{side.lower()}_{prop}")
    # Whatever is left must be operators, literals, parens and whitespace.
    residue = re.sub(r"'[^']*'", "", remainder)
    props = "|".join(_SUPPORTED_PROPERTIES)
    residue = re.sub(rf"\b[ab]_(?:{props})\b", "", residue)
    residue = re.sub(r"(&&|\|\||==|!=|\(|\)|\s)", "", residue)
    if residue:
        raise UnsupportedConditionError(
            f"condition {condition!r} contains constructs the rule-precedence "
            f"analyser cannot model (unparsed residue: {residue!r}). Extend "
            f"_SUPPORTED_PROPERTIES / _compile_condition, or the shadowing "
            f"guard cannot certify this file."
        )
    expr = remainder.replace("&&", " and ").replace("||", " or ")
    return compile(expr, "<dru-condition>", "eval")


def _netclass_universe(rules: Iterable[DruRule]) -> list[str]:
    """Every net-class name that could distinguish two rules, plus a sentinel."""
    names = set(TEMPER_NET_CLASSES)
    names.update(kicad_class_name(key) for key in TEMPER_NET_CLASSES)
    for rule in rules:
        if rule.condition:
            names.update(re.findall(r"'([^']*)'", rule.condition))
    # Item-type / pad-type literals also appear in single quotes; harmless as
    # extra net-class names (they simply add worlds), but drop the obvious ones
    # to keep the enumeration small.
    names -= set(_ITEM_TYPES) | {"SMD", "Through-hole", "NPTH", "Connector"}
    names.add(_UNLISTED_NETCLASS)
    return sorted(names)


def _worlds(netclasses: Iterable[str]):
    """Enumerate every (A, B) item pairing the analyser considers."""
    netclasses = list(netclasses)
    for a_nc, b_nc in itertools.product(netclasses, repeat=2):
        for a_type, b_type in itertools.product(_ITEM_TYPES, repeat=2):
            for a_pad, b_pad in itertools.product(_PAD_TYPES[a_type], _PAD_TYPES[b_type]):
                for same_reference in (True, False):
                    yield {
                        "a_NetClass": a_nc,
                        "b_NetClass": b_nc,
                        "a_Type": a_type,
                        "b_Type": b_type,
                        "a_Pad_Type": a_pad,
                        "b_Pad_Type": b_pad,
                        "a_Reference": "REF_A",
                        "b_Reference": "REF_A" if same_reference else "REF_B",
                    }


def _swapped(world: dict[str, str]) -> dict[str, str]:
    """The same world with A and B exchanged -- KiCad tests both orderings."""
    out = {}
    for key, value in world.items():
        side, prop = key.split("_", 1)
        out[("b" if side == "a" else "a") + "_" + prop] = value
    return out


def _matching_rules(rules: list[DruRule], predicates, world) -> list[DruRule]:
    swapped = _swapped(world)
    return [
        rule
        for rule, predicate in zip(rules, predicates, strict=True)
        if eval(predicate, {"__builtins__": {}}, world)  # noqa: S307
        or eval(predicate, {"__builtins__": {}}, swapped)  # noqa: S307
    ]


def find_shadowing(content: str) -> list[tuple[str, str, str, float, float]]:
    """Return every case where a weaker rule wins over a stricter one.

    Each entry is ``(constraint_type, winner_name, shadowed_name, winner_min,
    shadowed_min)``. An empty list means: for every constraint type and every
    modelled pair of items, the rule KiCad selects (the last matching one) is
    also the strictest matching one.
    """
    rules = [r for r in _parse_rules(content) if r.constraints]
    pair_rules = [r for r in rules if any(t in r.constraints for t in PAIR_CONSTRAINT_TYPES)]
    predicates = [_compile_condition(r.condition) for r in pair_rules]
    universe = _netclass_universe(pair_rules)

    found: dict[tuple[str, str, str], tuple[float, float]] = {}
    for world in _worlds(universe):
        matched = _matching_rules(pair_rules, predicates, world)
        if len(matched) < 2:
            continue
        for ctype in PAIR_CONSTRAINT_TYPES:
            applicable = [r for r in matched if ctype in r.constraints]
            if len(applicable) < 2:
                continue
            winner = applicable[-1]
            strictest = max(applicable, key=lambda r: r.constraints[ctype])
            if winner.constraints[ctype] < strictest.constraints[ctype]:
                found[(ctype, winner.name, strictest.name)] = (
                    winner.constraints[ctype],
                    strictest.constraints[ctype],
                )
    return sorted((c, w, s, wv, sv) for (c, w, s), (wv, sv) in found.items())


def order_rules_by_strictness(content: str) -> str:
    """Reorder the emitted rule blocks so the strictest matching rule wins.

    Rules that can apply to the same pair of items and disagree about a
    constraint value are ordered weakest-first, so KiCad's last-matching-wins
    selection lands on the strictest one. Rules that cannot overlap keep their
    authored order. Only the blocks that carry a pair constraint move; the
    surrounding comment banners travel with the block they document, and
    ``track_width``/hole rules are left exactly where the source puts them.
    """
    rules = _parse_rules(content)
    movable = [r for r in rules if any(t in r.constraints for t in PAIR_CONSTRAINT_TYPES)]
    if len(movable) < 2:
        return content

    predicates = [_compile_condition(r.condition) for r in movable]
    universe = _netclass_universe(movable)

    # `must_precede[i]` = indices (into `movable`) that rule i must come before.
    must_precede: dict[int, set[int]] = {i: set() for i in range(len(movable))}
    position = {r.name: i for i, r in enumerate(movable)}
    for world in _worlds(universe):
        matched = _matching_rules(movable, predicates, world)
        if len(matched) < 2:
            continue
        for ctype in PAIR_CONSTRAINT_TYPES:
            applicable = [r for r in matched if ctype in r.constraints]
            for weak, strong in itertools.combinations(applicable, 2):
                if weak.constraints[ctype] == strong.constraints[ctype]:
                    continue
                if weak.constraints[ctype] > strong.constraints[ctype]:
                    weak, strong = strong, weak
                must_precede[position[weak.name]].add(position[strong.name])

    order = _topological_order(must_precede)
    return _reflow_blocks(content, movable, order)


def _topological_order(must_precede: dict[int, set[int]]) -> list[int]:
    """Kahn's algorithm, breaking ties by authored order for determinism."""
    indegree = dict.fromkeys(must_precede, 0)
    for successors in must_precede.values():
        for j in successors:
            indegree[j] += 1
    ready = sorted(i for i, d in indegree.items() if d == 0)
    order: list[int] = []
    while ready:
        i = ready.pop(0)
        order.append(i)
        for j in sorted(must_precede[i]):
            indegree[j] -= 1
            if indegree[j] == 0:
                ready.append(j)
                ready.sort()
    if len(order) != len(must_precede):
        raise RulePrecedenceCycleError(
            "no emission order satisfies strictest-wins for every constraint "
            "type: two overlapping rules require opposite orderings under two "
            "different constraints. Split or re-scope one of them."
        )
    return order


def _reflow_blocks(content: str, movable: list[DruRule], order: list[int]) -> str:
    """Rewrite *content* with the movable rule blocks placed in *order*.

    A "block" is the rule text plus every comment/banner line that precedes it
    since the previous rule, so a rule's own documentation moves with it.
    """
    lines = content.splitlines()
    starts = []
    for rule in movable:
        first = rule.text.splitlines()[0]
        idx = next(i for i, line in enumerate(lines) if line == first and i not in starts)
        starts.append(idx)
    ends = [
        start + len(rule.text.splitlines()) for start, rule in zip(starts, movable, strict=True)
    ]

    # Block i owns everything from just after block i-1 through its own end
    # (plus one trailing blank line, which the emitter always writes).
    blocks: list[list[str]] = []
    cursor = starts[0]
    head = lines[:cursor]
    for i, end in enumerate(ends):
        block_start = cursor
        block_end = end
        while block_end < len(lines) and lines[block_end] == "":
            block_end += 1
        if i + 1 < len(starts):
            # Comment lines after this rule belong to the NEXT block.
            block_end = min(block_end, starts[i + 1])
        blocks.append(lines[block_start:block_end])
        cursor = block_end
    tail = lines[cursor:]

    out = list(head)
    for i in order:
        out.extend(blocks[i])
    out.extend(tail)
    reflowed = "\n".join(out)
    # splitlines() drops a trailing newline; put it back so the reordering is
    # byte-neutral apart from block order.
    if content.endswith("\n") and not reflowed.endswith("\n"):
        reflowed += "\n"
    return reflowed


def generate_dru() -> str:
    """Return the full contents of the KiCad DRU file as a string.

    The rule blocks are emitted below in their authored, narrative order, then
    reordered by :func:`order_rules_by_strictness` and certified by
    :func:`find_shadowing` before the text is returned -- see the RULE
    PRECEDENCE comment above.
    """
    lines: list[str] = []

    # KiCad custom design rules format header
    lines.append("# Custom Design Rules for Temper Induction Heater")
    lines.append("# IEC 60335-1 / IEC 60664-1 compliant")
    lines.append("#")
    lines.append("# NOTE: This board carries NO qualified conformal coating.")
    lines.append("# No coating process exists in the BOM or assembly, and IEC 60664-3 cl. 4.3")
    lines.append("# requires full-path coverage for any Pollution Degree 1 credit -- measured,")
    lines.append("# 100.0% of every declared isolator's shortest HV<->PELV path lies under its")
    lines.append("# own component body and cannot be shown to be coated. This file therefore")
    lines.append("# enforces FAIL-CLOSED, uncoated clearance figures throughout. See")
    lines.append("# docs/evidence/2026-07-28-conformal-coating-pd1.md.")
    lines.append("#")
    lines.append("# CREEPAGE IS ENFORCED HERE (2026-07-28): kicad-cli 10.0.4 supports a real")
    lines.append("# `creepage` constraint (confirmed against kicad-source-mirror @ 10.0.4 and")
    lines.append("# empirically -- see docs/evidence/2026-07-28-drc-creepage-constraint.md). RULES")
    lines.append(
        f"# 2 and 4 below enforce {fmt_mm(HV_CREEPAGE_ENFORCED_MM)} reinforced creepage across the"
    )
    lines.append("# AC-Mains/HighVoltage <-> everything-else boundary, in addition to their")
    lines.append("# existing clearance figures. The selected production architecture uses PD2")
    lines.append("# (8.0mm). PD3 (12.6mm) remains the fallback if the documented enclosure")
    lines.append(
        "# prerequisite is not implemented; see the source comment on"
        " HV_CREEPAGE_ENFORCED_MM for the"
    )
    lines.append("# selection rule and")
    lines.append("# `scripts/check_isolation_keepout.py` remains the")
    lines.append("# other, independent creepage enforcement point on this board (a conservative")
    lines.append("# straight-line-corridor sufficient bound, not a surface-path measure); this")
    lines.append("# generator's new rules are the fab-authoritative KiCad DRC path, and they now")
    lines.append("# agree on the same pinned figure. See docs/evidence/2026-07-28-creepage-")
    lines.append("# determination-brainstorm.md for the full clause-cited derivation.")
    lines.append("#")
    lines.append("# TO-247 IGBT packages have a 1.95mm edge-to-edge internal pin gap (see RULE")
    lines.append("# 5 below); this is a package-geometry fact, not something this script or a")
    lines.append("# coating can fix. Expect this rule to now flag those packages -- that is")
    lines.append("# the correct, honest result of removing the prior relaxation.")
    lines.append("#")
    lines.append("# Generated by scripts/generate_kicad_dru.py -- do not edit by hand.")
    lines.append("")
    lines.append("(version 1)")
    lines.append("")

    # -------------------------------------------------------------------------
    # Static rules: same-footprint and fine-pitch exceptions
    # -------------------------------------------------------------------------
    lines.append(_SEP)
    lines.append("# RULE 1: Allow reduced clearance within same footprint")
    lines.append(
        "# This handles TO-247, SOT-23, QFN packages where pad pitch < net class clearance"
    )
    lines.append("#")
    lines.append(
        "# CONDITION FIX (2026-07-28, redo): A.Footprint == B.Footprint never"
        ' binds -- "Footprint" is not a property KiCad\'s PROPERTY_MANAGER'
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
        ' of "safety domain" -- domain membership lives in'
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
    lines.append("# produced the +340V_BUS defect this task is named after).")
    lines.append(_SEP)
    lines.append('(rule "Same footprint pads"')
    lines.append('   (condition "A.Reference == B.Reference && A.NetClass == B.NetClass")')
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
        ' display name "Pad Type" (PROPERTY_ENUM<PAD, PAD_ATTRIB>), not'
    )
    lines.append(
        '# "Attribute". KiCad\'s rule compiler looks up properties by exact'
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
    lines.append("# A.Attribute == 'SMD').")
    lines.append(_SEP)
    lines.append('(rule "Fine pitch IC pads"')
    lines.append(
        "   (condition \"A.Type == 'Pad' && A.Pad_Type == 'SMD'"
        " && B.Type == 'Pad' && B.Pad_Type == 'SMD'"
        " && A.Reference == B.Reference"
        ' && A.NetClass == B.NetClass")'
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
    lines.append("# CREEPAGE ADDED (2026-07-28): kicad-cli 10.0.4 supports a real `creepage`")
    lines.append("# constraint (see the HV_CREEPAGE_ENFORCED_MM comment near the top of this")
    lines.append("# script for the full derivation, the PD2/PD3 pin, and the kicad-cli support")
    lines.append("# evidence). This is the fab-authoritative DRC check for the reinforced")
    lines.append("# mains<->LV creepage requirement this net-class pair represents; it did not")
    lines.append("# exist in the generated file before this change.")
    lines.append("#")
    lines.append(
        "# GateDriveHV EXCLUDED (2026-08-11): GATE_HS/GATE_LS float on"
        " SW_NODE -- elec/domain_manifest.yaml declares them members of the"
    )
    lines.append(
        "# SAME HV domain as ac_l/+170V_BUS/SW_NODE (secondary/HV side of"
        " U7's own reinforced barrier, not a third domain -- see the RULE"
    )
    lines.append(
        "# 4a/4b comment below for the identical reasoning already applied"
        " to HighVoltageIsolated). Before this fix, GateDriveHV was not"
    )
    lines.append(
        "# excluded from this rule's B-side, so it was silently treated as"
        " if it were LV/SELV and charged the full 8.0mm reinforced"
    )
    lines.append(
        "# creepage figure against its OWN same-side neighbours -- a false"
        " positive, not a real cross-barrier hazard. See RULE 6a below,"
    )
    lines.append(
        "# which supplies the correct functional (same-side) figure for"
        " this pair instead. GateDriveSELV is deliberately NOT added here"
    )
    lines.append(
        "# -- it is the genuinely SELV/primary-side half of the same"
        " gate-driver split and still needs the full reinforced boundary."
    )
    lines.append(_SEP)
    lines.append(
        "# HighVoltageTank EXCLUDED (2026-08-12): the tank node was carved out"
        " of HighVoltage into its own class, and without this exclusion an"
    )
    lines.append(
        "# (A=ACMains, B=HighVoltageTank) pair would newly match THIS rule and"
        " be charged the 8.0mm reinforced cross-barrier figure for a"
    )
    lines.append(
        "# same-HV-domain pairing -- the identical defect this rule's own"
        " GateDriveHV note above records. RULE 3 keeps handling it."
    )
    lines.append(_SEP)
    lines.append('(rule "AC Mains to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'ACMains'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'HighVoltage'"
        f" && B.NetClass != '{HV_TANK_CLASS}'"
        f" && B.NetClass != '{HV_SIGNAL_CLASS}'"
        " && B.NetClass != 'GateDriveHV'\")"
    )
    lines.append("   (constraint clearance (min 6.0mm))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 3: AC Mains to High Voltage - 3mm (both isolated from earth)")
    lines.append("# Reduced clearance since both are on same side of isolation barrier")
    lines.append(_SEP)
    lines.append(
        "# HighVoltageSignal INCLUDED (2026-08-13, docs/evidence/2026-08-13-"
        " netclass-current-scoping.md): same voltage domain as HighVoltage,"
        " mirroring the HV_TANK_CLASS addition above."
    )
    lines.append('(rule "AC Mains to HV"')
    lines.append(
        "   (condition \"A.NetClass == 'ACMains'"
        " && (B.NetClass == 'HighVoltage'"
        f" || B.NetClass == '{HV_TANK_CLASS}'"
        f" || B.NetClass == '{HV_SIGNAL_CLASS}')\")"
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
    lines.append("# CREEPAGE ADDED (2026-07-28): same rationale as RULE 2 above -- see")
    lines.append("# HV_CREEPAGE_ENFORCED_MM's comment near the top of this script. This is the")
    lines.append(
        "# other half of the mains<->LV / HV<->LV boundary scripts/check_isolation_keepout.py"
    )
    lines.append("# already enforces at the board-construction level; this rule now enforces the")
    lines.append("# same figure at the fab-authoritative KiCad DRC level.")
    lines.append("#")
    lines.append(
        "# GateDriveHV EXCLUDED (2026-08-11): same reasoning as RULE 2's"
        " own 2026-08-11 note above -- GATE_HS/GATE_LS are same-HV-domain,"
    )
    lines.append(
        "# not LV/SELV; see RULE 6a for the functional same-side figure"
        " this exclusion hands off to."
    )
    lines.append("#")
    lines.append(
        "# HighVoltageIsolated ALSO EXCLUDED (2026-08-11): this rule's"
        " condition never excluded HighVoltageIsolated from its B-side,"
    )
    lines.append(
        "# so a (A=HighVoltage, B=HighVoltageIsolated) pad pair matched"
        " THIS rule (8.0mm creepage) even though the reverse ordering"
    )
    lines.append(
        "# (A=HighVoltageIsolated, B=HighVoltage) already matches RULE 4a"
        " below and gets only the functional 2.0mm same-side clearance --"
    )
    lines.append(
        "# RULE 4a never declares a creepage constraint, so it could not"
        " override this rule's 8.0mm for the other ordering. Measured"
    )
    lines.append(
        "# directly against pcb/temper.kicad_pcb (kicad-cli 10.0.5): 9 of"
        " the 186 creepage violations are exactly this"
        " HighVoltage<->HighVoltageIsolated same-domain pairing (mostly"
    )
    lines.append(
        "# U7's own DC_BUS_RTN/GATE_HS pins vs. its own"
        " hb.gate_hs.driver-p1-1/-p2 pins) -- see"
        " docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md."
    )
    lines.append(_SEP)
    lines.append(
        "# HighVoltageTank EXCLUDED (2026-08-12): same reasoning, and this is"
        " the exclusion that MATTERS most. Before the tank carve-out the pair"
    )
    lines.append(
        "# (bus rail, tank node) was HighVoltage<->HighVoltage and matched"
        " nothing here. After it, the ordering (A=HighVoltage bus,"
    )
    lines.append(
        "# B=HighVoltageTank) would match this rule and charge the tank node"
        " 8.0mm REINFORCED creepage against its own bus -- a same-domain"
    )
    lines.append(
        "# functional pair mislabelled as a barrier crossing. RULE 5a below"
        " supplies the correct functional figure (Table 18, 6.3mm) instead."
    )
    lines.append(_SEP)
    lines.append(
        f"# {HV_SIGNAL_CLASS} EXCLUDED (2026-08-13): same reasoning as the"
        " HighVoltageTank exclusion above -- without it, a (HighVoltage,"
        f" {HV_SIGNAL_CLASS}) pair (e.g. SW_NODE vs. hb.power_loop.q_high-g,"
        " same footprint on U5) would match THIS rule and be charged 8.0mm"
        " reinforced creepage for a same-domain functional pair, not a"
        " barrier crossing. See the new"
        f' "{HV_SIGNAL_CLASS} to LV" rule below for this class\'s real'
        " protection."
    )
    lines.append('(rule "HV to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltage'"
        " && B.NetClass != 'HighVoltage'"
        f" && B.NetClass != '{HV_TANK_CLASS}'"
        f" && B.NetClass != '{HV_SIGNAL_CLASS}'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'GateDriveHV'"
        " && B.NetClass != 'HighVoltageIsolated'\")"
    )
    lines.append("   (constraint clearance (min 2.0mm))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append(
        "# RULE 4c: HighVoltageTank to LV -- an exact clone of RULE 4 above,"
        " for the class the tank node was carved out into."
    )
    lines.append(
        "# WITHOUT THIS RULE the carve-out would be a SAFETY REGRESSION: while"
        " tank.c_tank1-p2 was in HighVoltage it received RULE 4's 2.0mm"
    )
    lines.append(
        "# clearance and 8.0mm reinforced creepage against every LV/SELV net,"
        " and moving it to a new class silently drops that coverage. The"
    )
    lines.append(
        "# figures here are RULE 4's own, carried over unchanged -- this rule"
        " preserves an existing requirement, it does not introduce one."
    )
    lines.append(
        "# Note PWR_RTN, which has no netclass at all and so lands in Default"
        " (a known gap: docs/evidence/2026-08-12-hv-clearance-adequacy.md"
    )
    lines.append(
        "# sec 6.3): the tank<->PWR_RTN pair measures 544.6 Vrms, genuinely"
        " needs 6.3mm functional, and is charged 8.0mm by this rule because"
    )
    lines.append(
        "# Default reads as LV. That is conservative, not wrong, and it is the"
        " SAME treatment the pair already got before this change."
    )
    lines.append(_SEP)
    lines.append(f'(rule "{HV_TANK_CLASS} to LV"')
    lines.append(
        f"   (condition \"A.NetClass == '{HV_TANK_CLASS}'"
        f" && B.NetClass != '{HV_TANK_CLASS}'"
        " && B.NetClass != 'HighVoltage'"
        f" && B.NetClass != '{HV_SIGNAL_CLASS}'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'GateDriveHV'"
        " && B.NetClass != 'HighVoltageIsolated'\")"
    )
    lines.append("   (constraint clearance (min 2.0mm))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append(
        f'# RULE 4d: {HV_SIGNAL_CLASS} to LV -- an exact clone of RULE 4/4c'
        " above, for the mA-scale current-tier carve-out of HighVoltage"
        " (docs/evidence/2026-08-13-netclass-current-scoping.md)."
    )
    lines.append(
        "# WITHOUT THIS RULE the carve-out would be a SAFETY REGRESSION,"
        " the same shape RULE 4c's own comment records: while e.g. 'a' (U3's"
    )
    lines.append(
        "# ZCD divider tap/opto-anode net -- one pin of a real isolator on"
        " this board) was HighVoltage, it received 2.0mm clearance and"
    )
    lines.append(
        "# 8.0mm reinforced creepage against every LV/SELV net (measured:"
        " U3 pin 'a' vs. U3 pin 'gnd', same footprint, real board). Moving"
    )
    lines.append(
        "# it to this class must not silently drop that coverage."
    )
    lines.append(_SEP)
    lines.append(f'(rule "{HV_SIGNAL_CLASS} to LV"')
    lines.append(
        f"   (condition \"A.NetClass == '{HV_SIGNAL_CLASS}'"
        f" && B.NetClass != '{HV_SIGNAL_CLASS}'"
        " && B.NetClass != 'HighVoltage'"
        f" && B.NetClass != '{HV_TANK_CLASS}'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'GateDriveHV'"
        " && B.NetClass != 'HighVoltageIsolated'\")"
    )
    lines.append("   (constraint clearance (min 2.0mm))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 4a/4b: HighVoltageIsolated -- the gate-drive floating bootstrap supply")
    lines.append("#")
    lines.append("# GAP CLOSED (2026-07-28): this netclass carried ZERO clearance or creepage")
    lines.append("# rules anywhere in this generator until now (grep -c HighVoltageIsolated")
    lines.append("# scripts/generate_kicad_dru.py returned 0) -- the exact class RULE 1's own")
    lines.append("# cross-domain guard fix used to re-home U7's secondary bias nets (VSSA/VDDA,")
    lines.append("# hb.gate_hs.driver-p2/-p1-1) into, per docs/evidence/2026-07-28-drc-rule1-")
    lines.append("# netclass-redo.md sec 5. Moving those nets into a netclass that itself")
    lines.append("# enforced nothing left them with only KiCad's per-netclass baseline (6.0mm")
    lines.append("# clearance, from pcb/temper.kicad_pro's own net_settings.classes/packages/")
    lines.append("# temper-placer/configs/netclass_rules.yaml) and NO creepage protection at all.")
    lines.append("#")
    lines.append("# WHAT THE CLASS ACTUALLY IS: elec/domain_manifest.yaml declares +5V_ISO,")
    lines.append("# VBOOT_H, VBOOT_L, hb.gate_hs.driver-p1-1 (VDDA) and hb.gate_hs.driver-p2")
    lines.append("# (VSSA) -- every net this project assigns to the HighVoltageIsolated")
    lines.append("# netclass -- as members of the SAME `HV` domain as ac_l/+170V_BUS/SW_NODE,")
    lines.append('# not a third, separate domain. "Isolated" here names a gate-driver-internal')
    lines.append("# galvanic barrier (the UCC21550's own primary/secondary split), not a")
    lines.append("# barrier this netclass's nets sit on the far side of relative to the rest of")
    lines.append("# HV -- they float WITH the switch node, one gate-drive-current resistor")
    lines.append("# downstream of GATE_HS/SW_NODE (see the redo doc's own tracing). That means")
    lines.append("# this class needs exactly the asymmetric treatment docs/evidence/2026-07-28-")
    lines.append("# hv-isolated-rules-and-creepage-triage.md sets out: REINFORCED separation from")
    lines.append("# the LV/SELV side (the real barrier), but only FUNCTIONAL separation from its")
    lines.append(
        "# own HV/ACMains neighbours (same side of that barrier -- exactly the relationship"
    )
    lines.append('# RULE 3 ("AC Mains to HV") already models for ACMains vs. HighVoltage).')
    lines.append("#")
    lines.append('# 4a relaxes the pair to the same 2.0mm figure RULE 4 ("HV to LV") already')
    lines.append(
        "# uses for intra-HV-domain separation -- a documented, deliberate reduction below"
    )
    lines.append("# the 6.0mm per-netclass baseline that would otherwise apply, justified because")
    lines.append("# both sides sit on the same side of the reinforced barrier (same category of")
    lines.append(
        "# reduction RULE 3 already makes, not a safety loosening -- see the evidence doc)."
    )
    lines.append("# 4b is the real, new protection: reinforced clearance against every other")
    lines.append("# (LV/SELV) netclass, at the same 2.0mm figure RULE 4 uses for HighVoltage.")
    lines.append("# CREEPAGE CLOSED (2026-07-28): the generator-wide creepage constraint (see")
    lines.append("# HV_CREEPAGE_ENFORCED_MM's own comment near the top of this script) now")
    lines.append('# applies here too. 4a stays clearance-only, matching RULE 3 ("AC Mains to')
    lines.append('# HV") -- both are same-side-of-the-barrier reductions between two HV-domain')
    lines.append("# classes, not a creepage boundary. 4b, the real HV<->LV protection, now gets")
    lines.append('# the same reinforced creepage figure RULE 2 ("AC Mains to LV") and RULE 4')
    lines.append('# ("HV to LV") already enforce -- it is exactly that class of rule, just keyed')
    lines.append("# on HighVoltageIsolated instead of ACMains/HighVoltage.")
    lines.append("#")
    lines.append(
        "# GateDriveHV EXCLUDED from 4b's B-side (2026-08-11), symmetrically"
        " with RULE 2/4 above -- GATE_HS/GATE_LS are the same HV domain as"
    )
    lines.append(
        "# HighVoltageIsolated's own nets (both float with SW_NODE per"
        " elec/domain_manifest.yaml), so a GateDriveHV<->HighVoltageIsolated"
    )
    lines.append(
        "# pair is same-side, not a reinforced boundary. 4a needs no"
        " change -- its condition only ever matched B in {HighVoltage,"
    )
    lines.append(
        "# ACMains}, so it was never matching GateDriveHV in the first"
        " place; it simply never supplied this pair a same-side figure"
    )
    lines.append("# either, which is what the new RULE 6a below now does.")
    lines.append(_SEP)
    # Matches RULE 4's existing "HV to LV" clearance figure (this file,
    # unchanged) -- not a new number, just this class's share of it.
    _HV_ISOLATED_CLEARANCE_MM = 2.0
    lines.append(
        f"# {HV_SIGNAL_CLASS} INCLUDED on both rules below (2026-08-13,"
        " docs/evidence/2026-08-13-netclass-current-scoping.md): U7's own"
        f" +15V_LS (now {HV_SIGNAL_CLASS}) and hb.gate_hs.driver-p1-1/U8's"
        f" +15V_LS/hb.gate_hs.driver-p1-1 share a footprint -- same"
        " same-side-of-the-barrier reasoning as HighVoltage/HighVoltageTank."
    )
    lines.append('(rule "HighVoltageIsolated same side"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltageIsolated'"
        " && (B.NetClass == 'HighVoltage'"
        f" || B.NetClass == '{HV_TANK_CLASS}'"
        f" || B.NetClass == '{HV_SIGNAL_CLASS}'"
        " || B.NetClass == 'ACMains')\")"
    )
    lines.append(f"   (constraint clearance (min {fmt_mm(_HV_ISOLATED_CLEARANCE_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append('(rule "HighVoltageIsolated to LV"')
    lines.append(
        "   (condition \"A.NetClass == 'HighVoltageIsolated'"
        " && B.NetClass != 'HighVoltageIsolated'"
        " && B.NetClass != 'HighVoltage'"
        f" && B.NetClass != '{HV_TANK_CLASS}'"
        f" && B.NetClass != '{HV_SIGNAL_CLASS}'"
        " && B.NetClass != 'ACMains'"
        " && B.NetClass != 'GateDriveHV'\")"
    )
    lines.append(f"   (constraint clearance (min {fmt_mm(_HV_ISOLATED_CLEARANCE_MM)}))")
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 5: High Voltage internal - same footprint")
    lines.append("# TO-247 IGBTs have 5.45mm pin pitch (1.95mm edge-to-edge)")
    lines.append("#")
    lines.append("# FAIL-CLOSED: no conformal coating is qualified on this board, so no")
    lines.append("# coating-based relaxation is granted here. This constraint is the")
    lines.append("# uncoated reinforced clearance requirement -- IEC 60335-1 cl. 29.1: 1500V")
    lines.append("# rated impulse voltage (120V nominal, OVC II) -> Table 16 basic 0.5mm ->")
    lines.append("# cl. 29.1.3 next-higher-step reinforced 1.5mm, + cl. 29.1's +0.5mm")
    lines.append("# soldered-construction adder (this is a soldered PCB) = 2.0mm. See")
    lines.append("# docs/evidence/2026-07-28-conformal-coating-pd1.md sec 3.")
    lines.append("#")
    lines.append("# TO-247's 1.95mm edge-to-edge gap is BELOW this requirement. That is a real")
    lines.append("# violation this rule is now expected to report, not a bug in this rule --")
    lines.append("# a coating was never a valid fix for it (see docs/evidence/2026-07-28-")
    lines.append("# conformal-coating-pd1.md sec 4, TO-247/SOIC-16W case). Resolving it needs")
    lines.append("# a BOM/footprint/placement change, none of which this script performs.")
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
    lines.append("# see docs/evidence/2026-07-28-drc-courtyard-condition-fix.md.")
    lines.append(_SEP)
    lines.append(
        "# HighVoltageTank INCLUDED on both sides (2026-08-12): the three tank"
        " capacitors C25/C26/C27 each have pad 1 on SW_NODE (HighVoltage) and"
    )
    lines.append(
        "# pad 2 on tank.c_tank1-p2 (HighVoltageTank), so after the carve-out"
        " this rule -- and the generic 'Same footprint pads' rule, which"
    )
    lines.append(
        "# requires A.NetClass == B.NetClass -- would BOTH stop matching that"
        " intra-package pair. Widening the condition keeps the intent"
    )
    lines.append(
        "# ('same footprint, same HV domain -> the 2.0mm internal figure')"
        " intact. Measured impact: zero, because that footprint is a 40mm-"
    )
    lines.append(
        "# pitch axial can (temper:C_Axial_L34.0mm_D22.5mm_P40.00mm) whose two"
        " pads sit 40mm apart, and the pair-max netclass clearance would have"
    )
    lines.append(
        "# been the same 2.0mm anyway. It is widened for intent parity, not to move a number."
    )
    lines.append(_SEP)
    lines.append('(rule "HV internal same footprint"')
    lines.append(
        "   (condition \"(A.NetClass == 'HighVoltage'"
        f" || A.NetClass == '{HV_TANK_CLASS}')"
        " && (B.NetClass == 'HighVoltage'"
        f" || B.NetClass == '{HV_TANK_CLASS}')"
        ' && A.Reference == B.Reference")'
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
    lines.append("# the class model, not the clearance value.")
    lines.append(_SEP)
    lines.append(
        f"# {HV_SIGNAL_CLASS} INCLUDED on both rules below (2026-08-13):"
        " R23 (GATE_HS <-> hb.power_loop.q_high-g) and R24 (SW_NODE <->"
        " hb.power_loop.q_high-g) are real same-footprint gate resistors on"
        f" this board with one pad now classed {HV_SIGNAL_CLASS} -- without"
        " this inclusion those pairs fall to the 2.0mm default floor instead"
        " of the intended 0.5mm same-side figure, a needless over-"
        " constraint next to IGBT gate resistors."
    )
    lines.append('(rule "GateDriveHV near HV"')
    lines.append(
        "   (condition \"A.NetClass == 'GateDriveHV'"
        " && (B.NetClass == 'HighVoltage'"
        f" || B.NetClass == '{HV_TANK_CLASS}'"
        f" || B.NetClass == '{HV_SIGNAL_CLASS}')\")"
    )
    lines.append("   (constraint clearance (min 0.5mm))")
    lines.append(")")
    lines.append("")
    lines.append('(rule "GateDriveSELV near HV"')
    lines.append(
        "   (condition \"A.NetClass == 'GateDriveSELV'"
        " && (B.NetClass == 'HighVoltage'"
        f" || B.NetClass == '{HV_TANK_CLASS}'"
        f" || B.NetClass == '{HV_SIGNAL_CLASS}')\")"
    )
    lines.append("   (constraint clearance (min 0.5mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append(
        "# RULE 5a: THE HV<->HV FUNCTIONAL CREEPAGE RULE (NEW 2026-08-12)."
        " This is the constraint this whole class carve-out exists to carry."
    )
    lines.append("#")
    lines.append(
        "# Every other creepage constraint in this file (RULES 2, 4, 4b, 4c)"
        " requires one side to be non-HV -- they dimension the reinforced"
    )
    lines.append(
        "# barrier to LV/SELV. This rule is the first one in this repository"
        " for which BOTH sides are HV. Before it, the highest-voltage pair"
    )
    lines.append(
        "# on the board -- the resonant tank's cap<->coil junction against the"
        " DC bus rails, 923.7 V peak / 570.5 Vrms measured -- was checked"
    )
    lines.append(
        "# against no creepage requirement whatsoever. See"
        " docs/evidence/2026-08-12-hv-clearance-adequacy.md sec 3.2 for the"
    )
    lines.append(
        "# rule-inventory and empirical proof of that gap, and"
        " docs/evidence/2026-08-12-hv-hv-creepage-determination.md for the"
    )
    lines.append(
        "# Table 18 derivation of the 6.3mm figure (see"
        " HV_TANK_CREEPAGE_PD2_MM's comment at the top of this script)."
    )
    lines.append("#")
    lines.append(
        "# SCOPE. B is restricted to HighVoltage and HighVoltageTank itself:"
        " those are exactly the classes carrying the nets the 570.5 Vrms"
    )
    lines.append(
        "# working voltage was MEASURED against (+170V_BUS, DC_BUS_RTN,"
        " SW_NODE). The pairs to LV/Default, including the unclassed PWR_RTN,"
    )
    lines.append("# are covered by RULE 4c at the stricter 8.0mm and are not repeated here.")
    lines.append("#")
    lines.append(
        "# ONE PAIR IS OVER-CONSTRAINED BY ONE TABLE ROW, DELIBERATELY."
        " tank.c_tank1-p2 <-> SW_NODE (the voltage ACROSS the tank caps)"
    )
    lines.append(
        "# measures 411.5 Vrms, which is Table 18 band v (>400-500 V) = 4.0mm"
        " at PD2, not band vi's 6.3mm. Splitting it out would need a"
    )
    lines.append(
        "# NetName-keyed override whose rule-precedence behaviour this repo"
        " has not established; the measured cost of NOT splitting it is zero,"
    )
    lines.append(
        "# because the only components carrying both nets are C25/C26/C27,"
        " whose pads sit 40mm apart. Recorded so the conservatism is visible"
    )
    lines.append("# rather than silently baked in.")
    lines.append(
        f"# {HV_SIGNAL_CLASS} INCLUDED on B (2026-08-13, docs/evidence/"
        "2026-08-13-netclass-current-scoping.md): the RULE 4d exclusion"
        f" above means a ({HV_TANK_CLASS}, {HV_SIGNAL_CLASS}) pair -- e.g."
        " tank.c_tank1-p2 vs. a same-domain bleed/signal tap -- no longer"
        ' matches "HighVoltageTank to LV", so without this inclusion it'
        " would get ZERO creepage protection against the highest-voltage"
        " node on the board (570.5 Vrms). This rule is what supplies it."
    )
    lines.append(_SEP)
    lines.append(f'(rule "{HV_TANK_CLASS} functional creepage"')
    lines.append(
        f"   (condition \"A.NetClass == '{HV_TANK_CLASS}'"
        " && (B.NetClass == 'HighVoltage'"
        f" || B.NetClass == '{HV_TANK_CLASS}'"
        f" || B.NetClass == '{HV_SIGNAL_CLASS}')\")"
    )
    lines.append(f"   (constraint creepage (min {fmt_mm(HV_TANK_CREEPAGE_ENFORCED_MM)}))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 6a/6b: GateDriveHV same side (ACMains, HighVoltageIsolated)")
    lines.append("#")
    lines.append(
        "# GAP CLOSED (2026-08-11): GATE_HS/GATE_LS (netclass GateDriveHV,"
        " pcb/temper.kicad_pro netclass_patterns 'GATE_*') are the UCC21550"
    )
    lines.append(
        "# gate driver's own secondary-side gate outputs --"
        " elec/domain_manifest.yaml lines ~111-116 declare them members of"
    )
    lines.append(
        "# the SAME HV domain as ac_l/+170V_BUS/SW_NODE/hb.gate_hs.driver-"
        "p1-1/-p2 (float WITH the switch node, one gate resistor"
    )
    lines.append(
        "# downstream), and packages/temper-placer/configs/netclass_rules."
        "yaml's own GateDriveHV class comment says the same thing in so"
    )
    lines.append(
        "# many words. Before RULE 2/4/4b's 2026-08-11 GateDriveHV"
        " exclusions above, none of the three existing 'to LV' rules"
    )
    lines.append(
        "# treated GateDriveHV as same-side, so ACMains/HighVoltage/"
        "HighVoltageIsolated vs. GateDriveHV pairs were charged the full"
    )
    lines.append(
        "# 8.0mm reinforced creepage figure meant for a genuine mains/HV"
        " <-> SELV boundary -- a false positive against the project's own"
    )
    lines.append(
        "# domain model, not a real shock-hazard pair (both sides float at"
        " the same potential relative to SW_NODE). Measured directly"
    )
    lines.append(
        "# against pcb/temper.kicad_pcb (kicad-cli 10.0.5): 7 of the 186"
        " creepage violations name a GATE_HS/GATE_LS net opposite an"
    )
    lines.append(
        "# ACMains/HighVoltage/HighVoltageIsolated net -- see"
        " docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md."
    )
    lines.append("#")
    lines.append(
        '# This closes the gap the same way RULE 3 ("AC Mains to HV")'
        ' and RULE 4a ("HighVoltageIsolated same side") already closed'
    )
    lines.append(
        "# it for their own same-side pairs: GateDriveHV vs. ACMains and"
        " vs. HighVoltageIsolated now get RULE 6's own existing 0.5mm"
    )
    lines.append(
        "# functional figure (the same number already accepted for"
        " GateDriveHV vs. HighVoltage above -- not a new value) instead of"
    )
    lines.append(
        "# falling through to the reinforced boundary. GateDriveSELV is"
        " deliberately NOT given an equivalent pair here -- it is the real"
    )
    lines.append(
        "# SELV/primary-side half of the same gate-driver split (elec/"
        "domain_manifest.yaml keeps PWM_HS/PWM_LS out of every HV domain"
    )
    lines.append(
        "# list) and still needs the full reinforced boundary against"
        " ACMains/HighVoltage/HighVoltageIsolated -- RULE 2/4/4b apply to"
    )
    lines.append("# it unchanged, correctly.")
    lines.append(_SEP)
    lines.append('(rule "GateDriveHV to ACMains"')
    lines.append("   (condition \"A.NetClass == 'GateDriveHV' && B.NetClass == 'ACMains'\")")
    lines.append("   (constraint clearance (min 0.5mm))")
    lines.append(")")
    lines.append("")
    lines.append('(rule "GateDriveHV to HighVoltageIsolated"')
    lines.append(
        "   (condition \"A.NetClass == 'GateDriveHV' && B.NetClass == 'HighVoltageIsolated'\")"
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
        ' && A.Reference == B.Reference")'
    )
    lines.append("   (constraint clearance (min 0.2mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 8: Ground to everything - standard clearance")
    lines.append("# GND is a reference, not a hazard")
    lines.append(_SEP)
    lines.append('(rule "Ground clearance"')
    lines.append("   (condition \"A.NetClass == 'Ground' || B.NetClass == 'Ground'\")")
    lines.append("   (constraint clearance (min 0.15mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 9: USB differential pair - tight coupling")
    lines.append(_SEP)
    lines.append('(rule "USB differential"')
    lines.append("   (condition \"A.NetClass == 'HighSpeed' && B.NetClass == 'HighSpeed'\")")
    lines.append("   (constraint clearance (min 0.1mm))")
    lines.append(")")
    lines.append("")
    lines.append(_SEP)
    lines.append("# RULE 10: Default routing clearance")
    lines.append(f"# Standard {DEFAULT_ROUTING_CLEARANCE_MM}mm for signal traces")
    lines.append(_SEP)
    lines.append('(rule "Default routing"')
    lines.append("   (condition \"A.Type == 'Track' || B.Type == 'Track'\")")
    lines.append(
        f"   (constraint clearance (min {DEFAULT_ROUTING_CLEARANCE_MM}mm))"
    )
    lines.append(")")
    lines.append("")

    # -------------------------------------------------------------------------
    # Per-class trace-width rules generated from TEMPER_NET_CLASSES
    # -------------------------------------------------------------------------
    lines.append(_SEP)
    lines.append("# TRACE WIDTH RULES (generated from TEMPER_NET_CLASSES in design_rules.py)")
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
        # Added 2026-08-12 with the tank carve-out. This list is HAND-
        # MAINTAINED and silently drops any class missing from it: without
        # this entry tank.c_tank1-p2's tracks would lose the 3.0mm minimum
        # width they were held to as HighVoltage members, and nothing would
        # have said so. Same 3.0mm figure -- the carve-out changes the
        # creepage requirement, not the current-carrying width.
        # (`HighVoltageIsolated` is still absent from this list; that is a
        # pre-existing gap, not one this change introduces, and is left
        # alone rather than fixed silently under an unrelated heading.)
        HV_TANK_CLASS,
        # Added 2026-08-13 (docs/evidence/2026-08-13-netclass-current-
        # scoping.md) with the HighVoltageSignal carve-out. Without this
        # entry the mA-scale bleed/signal nets moved into this class would
        # get NO track_width rule at all (not even the old 3.0mm HighVoltage
        # figure) -- this is the exact "declared class enforces nothing"
        # defect scripts/check_hv_netclass_coverage.py PROPERTY 2 exists to
        # catch, and it did catch this omission during this task's own
        # first pass.
        HV_SIGNAL_CLASS,
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

    content = order_rules_by_strictness("\n".join(lines))

    # Fail closed. If the reordering could not put every rule where the
    # strictest matching one wins, this file must not be written: KiCad would
    # silently enforce the weaker figure and the DRC would report a clean
    # safety bar that is not being checked.
    shadowing = find_shadowing(content)
    if shadowing:
        detail = "\n".join(
            f"  [{ctype}] '{winner}' ({winner_min}mm) would override "
            f"'{shadowed}' ({shadowed_min}mm)"
            for ctype, winner, shadowed, winner_min, shadowed_min in shadowing
        )
        raise RuleShadowingError(
            "the generated .kicad_dru would let a weaker rule override a "
            "stricter one under KiCad's last-matching-rule-wins precedence:\n"
            f"{detail}\n"
            "See the RULE PRECEDENCE comment in this file and "
            "docs/evidence/2026-08-12-dru-rule-precedence.md."
        )
    return content


def main() -> None:
    content = generate_dru()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {len(content.splitlines())} lines to {OUTPUT_PATH}")
    print()
    print(content)


if __name__ == "__main__":
    main()
