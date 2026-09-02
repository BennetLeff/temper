#!/usr/bin/env python3
"""Scalar fact-drift gate: a non-creepage/clearance value declared in more
than one place must agree, or the gate fails closed.

Motivation
----------
``scripts/check_creepage_clearance_drift.py`` (PR #1238) already gates
creepage/clearance millimetre figures. It deliberately does not scan for
other kinds of duplicated fact -- the 2026-08-17 fact-deduplication audit
(``docs/evidence/2026-08-17-fact-dedup-inventory-and-gate.md``) found the
same "one fact, many homes, drifting" shape recurring for values that are
not creepage or clearance: most concretely, this board's own **mains
voltage** and **pollution degree** (SafetySpec).

The concrete finding this gate encodes
----------------------------------------
This design is a US 120V RMS +-10% appliance (``docs/specs/REQUIREMENTS.md``
REQ-SYS-01: "AC Input Voltage: 120V RMS +-10%, US residential mains"),
confirmed independently by:

  - ``elec/src/main.ato`` -- ``v_ac_nominal = 120V``, with its own assertion
    ``assert v_ac_nominal within 100V to 130V`` (NEMA 5-15 tolerance).
  - ``docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`` -- the voltage-doubler exists
    *specifically* so the appliance needs no 240V input ("Compatible with
    120V/15A outlet (no 240V required)").
  - ``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 2.1 (revision 1.4,
    2026-08-14) -- corrected its own "120-240V RMS" row to "120V RMS +-10%"
    to match REQ-SYS-01, and explicitly states "No 240V variant is intended
    for this design."

And the pollution degree this board enforces is **PD3** (2026-08-15,
``docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`` + PR #1224/#1229:
"PD3 governs (12.6mm reinforced, 10.0mm tank)").

Despite both being unambiguously decided, THREE other declaration sites
carried the pre-decision values and had never been updated. As of
2026-08-17, ONE of the three is fixed:

  - ``packages/temper-design-bundle/src/specification_contracts.rs`` -- the
    Rust ``SafetySpec`` pyclass's own ``#[new]`` default was
    ``mains_voltage_v: opt_or(py, mains_voltage_v, 230.0_f64)``,
    ``pollution_degree: opt_or(py, pollution_degree, 2_i64)``. **FIXED**:
    now defaults to 120.0/3. Its pinned oracle
    (``tests/core/_specification_py_oracle.py``) was re-pinned in the same
    change (exhaustive-divergence evidence: the full
    ``test_specification.py`` + ``test_specification_rust_differential.py``
    suite -- 27 tests -- passes with exactly one expected assertion change,
    ``test_safety_spec_defaults``, corrected alongside; no production code
    constructs ``SafetySpec()`` bare, confirmed by a repo-wide grep, so this
    was a latent-trap default, not a live divergence). See
    ``docs/evidence/2026-08-17-safetyspec-default-repin.md``.

  Still open, both left deliberately red:

  - ``packages/temper-placer/configs/pcb_spec.yaml`` -- ``safety:
    mains_voltage_v: 230.0`` / ``pollution_degree: 2``. Feeds
    ``pipeline/derivation.py``'s ``hv_lv_isolation_mm`` derivation (consumed
    by the regression/scoring oracle, NOT the board's enforced DRC gate --
    see ``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 2.1 revision-history
    entry 1.4 for the prior, deliberately-not-fixed investigation of this
    exact site).
  - ``packages/temper-placer/src/temper_placer/core/design_rules.py`` --
    the ``ACMains`` net-class carries ``voltage_v=240.0``. Consumed by
    ``temper-drc-rs``'s ``partial_discharge.rs`` (>=60V HV-inner-layer
    filter -- both 120V and 240V clear the 60V threshold identically, so
    this specific consumer's *behaviour* does not change) and marshalled
    verbatim into WASM board-serialization and ``drc_ratchet.py`` reports
    (cosmetic passthrough). This exact site was already identified stale by
    the 2026-08-14 correction above and deliberately left unfixed pending an
    owner ("should be reconciled to 120V by whoever owns that config").

Why this gate does not fix these two itself
------------------------------------------
The correct VALUES are not in question (120.0 / PD3) -- this is NOT a
judgment call like the drift gate's own open ``[clearance/reinforced]``
family. What blocks a mechanical fix of the remaining two sites:

  - ``design_rules.py``'s ACMains ``voltage_v=240.0`` is differentially
    compared, field-for-field, against the PINNED oracle
    ``tests/core/_design_rules_py_oracle.py`` (hash-pinned in
    ``scripts/oracle_hashes.json``; also carries its own ``voltage_v=240.0``
    for the matching class). Changing production without the oracle would
    fail ``test_design_rules_field_parity.py``/``test_design_rules_rust_
    differential.py``; changing the oracle requires the separate, deliberate
    re-pin ceremony this repo's own rules reserve for oracle changes -- not
    yet done for this site (only ``_specification_py_oracle.py`` has been,
    above).
  - ``pcb_spec.yaml`` itself is NOT oracle-pinned and could be edited
    directly, but its value flows into the SAME oracle-compared derivation
    surface (``_physics_oracle_py_oracle.py`` defaults to loading this exact
    file when no explicit spec path is given), so fixing it in isolation,
    without also verifying the physics-oracle differential surface end to
    end, risks silently breaking a pinned comparison this gate has not
    exhaustively swept.

So: this is a MECHANIZED, VERIFIED, currently-failing gate, deliberately
left red for these two remaining sites. Un-redding it fully requires a
coordinated PR that (1) updates both remaining production sites to
120.0/3, (2) re-pins ``_design_rules_py_oracle.py`` per the standing oracle
re-pin ceremony with the required exhaustive-divergence evidence, after
first sweeping ``pcb_spec.yaml``'s physics-oracle derivation surface, and
(3) fixes any correspondingly-affected tests. That remains a deliberate,
attributed, single act -- explicitly NOT something this gate, or the agent
that wrote it, may do by fiat.

Design
------
Unlike ``check_creepage_clearance_drift.py``'s whole-repo AST discovery,
this gate is an EXPLICIT registry (mirrors ``duplicate_predicate_registry.
py``'s own rationale: a hand-reviewed, falsifiable list of sites already
proven to hold this fact, not a repo-wide sweep for arbitrary numbers named
"voltage" -- most such numbers are unrelated per-component ratings, not
declarations of the system's own mains input). Adding a new fact is a
reviewed act, matching this repo's established convention for narrowly
scoped ``check_*.py`` gates.

Exit codes (mirrors check_creepage_clearance_drift.py / check_duplicate_predicates.py)
------------------------------------------------------------------------------------------
  0 - CLEAN: registry non-empty, every home found and matched its pattern,
      every home's value equals its fact's authoritative value.
  3 - VIOLATION: at least one home's extracted value diverges from its
      fact's authoritative value.
  5 - TOOL ERROR: registry empty (vacuous), a home file is missing, or a
      home's pattern failed to match at all (the site drifted structurally
      -- e.g. renamed field -- and the gate can no longer trust its own
      scan; never conflated with "0 violations").

Usage
-----
  uv run --no-sync python scripts/check_fact_registry_drift.py

2026-08-17 (session 2) extension
---------------------------------
See docs/evidence/2026-08-17-fact-registry-drift-gate-extension.md for the
full writeup. Five more fact families were added, motivated by the task
brief's own incident table (a HighVoltageSignal via diameter/drill
mismatch put 56 vias below the JLCPCB annular-ring fab floor for 4 days):

  - ``default_via_diameter_mm`` / ``default_via_drill_mm`` -- the board-
    wide via-geometry fallback every unassigned net resolves to. RED: the
    Rust ``DesignRules::new()`` pyo3 constructor's bare-call default is a
    vestigial 0.6mm, not the 0.9mm every other home carries (currently
    unreachable in production, oracle-pinned, not fixed here).
  - 26 per-netclass ``via_diameter_mm``/``via_drill_mm`` facts (13 classes
    x 2 fields), table-driven -- the family that actually bit this project.
    All CLEAN as of 2026-08-17; this is the regression guard.
  - ``gate_drive_hs_net_name`` / ``gate_drive_ls_net_name`` -- the real
    board net names (GATE_HS/GATE_LS), registered as a regression guard for
    PhysicsGate._GATE_NETS's PR #1310 fix (same-day, earlier session).
  - ``gate_hs_net_current_rating_a`` / ``gate_ls_net_current_rating_a`` --
    a NEW divergence this changeset's sweep found: unlike _GATE_NETS,
    StackupGate._DEFAULT_NET_CURRENTS and temper_drc_rs::ipc::
    net_currents() were never updated from GATE_H/GATE_L to GATE_HS/
    GATE_LS, so the real board's gate-drive nets silently get the
    ampacity gate's 0.1A unlisted-net default instead of their intended
    2.0A citation. Registered as TOOL ERRORS (missing citation). Not
    fixed here -- the fix ripples into router_v6/trace_width_assignment.
    py's current-derivation cascade, unverified end to end in this
    worktree (no pyo3 build available).
  - ``hv_lv_separation_gate_threshold_mm`` -- gates.py hardcodes 6.0mm in
    two places (PhysicsGate._CREEPAGE_MIN_MM, IECCreepageGate's inline
    Violation(...) literal) against the board's actual enforced 12.6mm
    PD3 creepage figure. RED, NOT FIXED: forbidden by the hard rule
    against changing creepage thresholds, and IECCreepageGate/DeltaMapper
    are sibling-owned territory this session. DeltaMapper.to_delta() reads
    ``violation.threshold`` directly from this gate, so the stale figure
    also sets the real placement-feedback separation distance, not just a
    report label -- flagged as an open finding needing a sibling/owner
    decision, including whether this "creepage" gate is even measuring
    the right kicad-cli DRC rule type (it filters ``clearance``, not
    ``creepage``).

The mechanism itself grew ``value_kind="str"`` support (previously float/
int only), used for the two net-name-valued families above.

2026-08-18 addition
-------------------
  - ``min_via_annular_ring_mm`` -- the annular-ring fab FLOOR itself (as
    opposed to the via pad/drill pairs above, which are the values chosen
    to clear it). Registered because PR #1316 gave the fact a second home
    the same week: ``Via::new`` (temper-orchestration) now enforces the
    floor at construction, so the crate carries its own copy of a number
    ``pcb/temper.kicad_pro`` already declared at DRC severity ``error``.
    CLEAN in both homes.

    Motivation is the same failure shape this gate exists for, caught one
    step earlier: that Rust change ALSO left eight ``router_v6`` tests
    holding the pre-floor 0.6mm via pad, with nothing connecting the two
    sides. Because the constant lives in a compiled extension, those
    eight passed or failed according to when the reader last ran
    ``maturin develop`` -- a suite whose verdict tracked build state, not
    code state, which cost several agents a session. The tests were
    repaired to DERIVE the geometry from the crate (the constant is now
    exported as ``temper_orchestration.MIN_ANNULAR_RING_MM``); this fact
    is the mechanical half of that link and
    ``packages/temper-placer/tests/router_v6/
    test_via_annular_floor_guard.py`` is the behavioural half.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_CLEAN = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass(frozen=True)
class FactSite:
    """One declaration site for a Fact."""

    file: str  # repo-relative path
    description: str
    pattern: str  # regex with exactly one capture group: the value
    scope_anchor: str | None = None  # optional regex; search is scoped to
    # the window starting at the anchor's match, so the same field name
    # elsewhere in the file (a different net class, a different struct)
    # cannot be matched by accident.
    scope_lines: int = 40


@dataclass(frozen=True)
class Fact:
    name: str
    category: str
    authoritative_value: float | str
    value_kind: str  # "float" | "int" | "str" (controls comparison + rendering)
    authoritative_source: str
    homes: tuple[FactSite, ...]
    notes: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: tuple[Fact, ...] = (
    Fact(
        name="mains_voltage_v",
        category="board-spec",
        authoritative_value=120.0,
        value_kind="float",
        authoritative_source=(
            "docs/specs/REQUIREMENTS.md REQ-SYS-01 ('AC Input Voltage: 120V "
            "RMS +-10%, US residential mains'); cross-confirmed by elec/src/"
            "main.ato's own 'assert v_ac_nominal within 100V to 130V' and "
            "docs/hardware/VOLTAGE_DOUBLER_DESIGN.md ('Compatible with "
            "120V/15A outlet (no 240V required)'). No 240V (or 120/240V "
            "dual-input) variant is declared as a design target anywhere."
        ),
        homes=(
            FactSite(
                file="elec/src/main.ato",
                description="atopile SSOT nominal AC input",
                pattern=r"v_ac_nominal\s*=\s*([\d.]+)V",
            ),
            FactSite(
                file="packages/temper-placer/configs/pcb_spec.yaml",
                description="placer physical-spec safety.mains_voltage_v",
                pattern=r"mains_voltage_v:\s*([\d.]+)",
            ),
            FactSite(
                file=(
                    "packages/temper-placer/src/temper_placer/core/"
                    "design_rules.py"
                ),
                description="ACMains net-class metadata voltage_v",
                pattern=r"voltage_v=([\d.]+),",
                scope_anchor=r'"ACMains":\s*NetClassRules\(',
            ),
            FactSite(
                file="packages/temper-design-bundle/src/specification_contracts.rs",
                description="Rust SafetySpec::new() default mains_voltage_v",
                pattern=r"mains_voltage_v,\s*([\d.]+)_f64",
            ),
        ),
        notes=(
            "PARTIALLY FIXED 2026-08-17: specification_contracts.rs's "
            "SafetySpec default corrected to 120.0/PD3 and its oracle "
            "(_specification_py_oracle.py) re-pinned -- see "
            "docs/evidence/2026-08-17-safetyspec-default-repin.md. "
            "design_rules.py remains pinned-oracle-entangled "
            "(_design_rules_py_oracle.py) and pcb_spec.yaml's fix was ruled "
            "out of scope pending a full differential-suite sweep of its "
            "derivation surface (pipeline/derivation.py's hv_lv_isolation_mm) "
            "-- both still KNOWN RED, see module docstring."
        ),
    ),
    Fact(
        name="pollution_degree",
        category="board-spec",
        authoritative_value=3.0,
        value_kind="int",
        authoritative_source=(
            "docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md + PR "
            "#1224/#1229: 'PD3 governs (12.6mm reinforced, 10.0mm tank)'."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/configs/pcb_spec.yaml",
                description="placer physical-spec safety.pollution_degree",
                pattern=r"pollution_degree:\s*(\d+)",
            ),
            FactSite(
                file="packages/temper-design-bundle/src/specification_contracts.rs",
                description="Rust SafetySpec::new() default pollution_degree",
                pattern=r"pollution_degree,\s*(\d+)_i64",
            ),
        ),
        notes=(
            "PARTIALLY FIXED 2026-08-17: specification_contracts.rs's "
            "SafetySpec default corrected to 120.0/PD3 and its oracle "
            "re-pinned -- see docs/evidence/2026-08-17-safetyspec-default-"
            "repin.md. pcb_spec.yaml remains KNOWN RED, ruled out of scope "
            "pending a full differential-suite sweep of its derivation "
            "surface (see module docstring)."
        ),
    ),
    Fact(
        name="gatedrive_class_pairs_completeness",
        category="netclass-class-pairs",
        authoritative_value=6.0,
        value_kind="float",
        authoritative_source=(
            "packages/temper-placer/configs/netclass_rules.yaml's own "
            "established convention: every other HV-domain class "
            "(ACMains/HighVoltage/HighVoltageTank/HighVoltageIsolated/"
            "HighVoltageSignal) carries class_pairs rows to its LV "
            "neighbours at this SAME 6.0mm figure (PR #1226, 'label 6.0mm "
            "legacy family UNSOURCED' -- an explicitly documented, "
            "deliberately-conservative placer-feasibility figure, NOT a "
            "fab-authoritative safety value; see that file's own header "
            "comment). See docs/evidence/2026-08-17-gatedrive-class-pairs-"
            "gap.md."
        ),
        homes=(
            # GateDriveHV/GateDriveSELV were split from the single
            # "GateDrive" class on 2026-07-28 (PR #434) but never received
            # class_pairs rows (unlike their sibling HighVoltageIsolated,
            # closed in the SAME commit). Dormant until PR #1322 switched
            # netclass_constraints.py's classifier to the manifest-backed
            # design_rules.get_rules_for_net() -- the only caller that can
            # actually resolve a component to these two class names -- at
            # which point 33+ real cross-domain component pairs on the
            # board silently fell through to a weaker
            # max(class_a.clearance, class_b.clearance) default (as low as
            # 0.25mm) instead of this 6.0mm figure. Each home below is one
            # of the 10 rows added to close that gap
            # (docs/evidence/2026-08-17-gatedrive-class-pairs-gap.md); if
            # any is deleted, this gate's pattern match fails (TOOL ERROR,
            # exit 5) rather than silently reporting clean, and if any
            # value is edited away from 6.0mm without also updating this
            # registry, the gate reports a VIOLATION (exit 3). Either way:
            # a future missing/changed GateDrive class_pairs row is a gate
            # failure, not a silent weakening.
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveHV-FinePitch",
                pattern=r"GateDriveHV-FinePitch:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveHV-GND",
                pattern=r"GateDriveHV-GND:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveHV-Power",
                pattern=r"GateDriveHV-Power:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveHV-Signal",
                pattern=r"GateDriveHV-Signal:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveHV-GateDriveSELV",
                pattern=r"GateDriveHV-GateDriveSELV:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs ACMains-GateDriveSELV",
                pattern=r"ACMains-GateDriveSELV:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveSELV-HighVoltage",
                pattern=r"GateDriveSELV-HighVoltage:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveSELV-HighVoltageTank",
                pattern=r"GateDriveSELV-HighVoltageTank:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveSELV-HighVoltageIsolated",
                pattern=r"GateDriveSELV-HighVoltageIsolated:\s*\{clearance:\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/configs/netclass_rules.yaml",
                description="class_pairs GateDriveSELV-HighVoltageSignal",
                pattern=r"GateDriveSELV-HighVoltageSignal:\s*\{clearance:\s*([\d.]+)",
            ),
        ),
        notes=(
            "FIXED 2026-08-17 (docs/evidence/2026-08-17-gatedrive-class-"
            "pairs-gap.md): added, not derived from the DRU-generated SSOT "
            "(pair_clearance.generated.yaml/pair_creepage.generated.yaml) "
            "-- class_pairs is a deliberate, separate, looser "
            "placer-feasibility model (PR #1226), and deriving from the "
            "DRU tables would silently substitute the real 12.6mm PD3 "
            "figures, an uncoordinated safety-value change with a large, "
            "unverified connectivity cost (see PR #1321's measured "
            "63/139->50/139 full-reroute cost from doing exactly that). "
            "Verified pairwise against the real board: zero genuine "
            "cross-domain (HV/AC vs LV) regressions relative to main "
            "before PR #1322."
        ),
    ),
    # -------------------------------------------------------------------
    # 2026-08-17 (session 2) extension -- docs/evidence/2026-08-17-fact-
    # registry-drift-gate-extension.md. Motivated directly by the incident
    # table in that day's task brief: a HighVoltageSignal via diameter/
    # drill mismatch between netclass_rules.yaml (0.8/0.4) and
    # design_rules.py's TEMPER_NET_CLASSES (1.0/0.4) put 56 vias below the
    # JLCPCB annular-ring fab floor, discovered four days after the
    # divergence was introduced. Both per-class values now agree (fixed
    # 2026-08-17, prior to this changeset) -- these entries are the
    # regression guard so the SAME shape of bug cannot silently return
    # uncaught, plus the *board-wide default* (the class-less fallback
    # every unassigned net falls through to, the exact "vestigial but
    # live" shape #1311's docstring warned about) and a genuinely new
    # divergence this sweep found in it (see below).
    # -------------------------------------------------------------------
    Fact(
        name="default_via_diameter_mm",
        category="via-geometry",
        authoritative_value=0.9,
        value_kind="float",
        authoritative_source=(
            "packages/temper-placer/src/temper_placer/core/design_rules.py "
            "create_temper_design_rules()'s own comment: 'RAISED 0.6 -> "
            "0.9mm 2026-08-13 (docs/evidence/2026-08-13-jlcpcb-fab-"
            "capability-envelope.md): 0.6mm/0.3mm gave a 0.15mm annular "
            "ring, below JLCPCB's 2oz PTH annular-ring floor (0.254mm). "
            "This is the fallback used for any net that resolves to no "
            "declared class.' Independently corroborated by the identical "
            "value and citation in stage0_data.py and "
            "constraints_design_rules.py."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/src/temper_placer/core/design_rules.py",
                description="create_temper_design_rules() DesignRules(...) default_via_diameter",
                pattern=r"default_via_diameter=([\d.]+),",
                scope_anchor=r"def create_temper_design_rules\(\)",
                scope_lines=25,
            ),
            FactSite(
                file="packages/temper-placer/src/temper_placer/io/_parse_nets.py",
                description="_extract_design_rules() fallback default_via_diameter",
                pattern=r"default_via_diameter\s*=\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/src/temper_placer/router_v6/stage0_data.py",
                description="stage0_data.DesignRules dataclass field default",
                pattern=r"default_via_diameter_mm:\s*float\s*=\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/src/temper_placer/router_v6/constraints_design_rules.py",
                description="constraints_design_rules.DesignRules dataclass field default",
                pattern=r"default_via_diameter:\s*float\s*=\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-design-bundle/src/design_rules.rs",
                description=(
                    "Rust DesignRules::new() #[pyo3(signature=...)] bare-"
                    "constructor default (KNOWN RED -- see notes)"
                ),
                pattern=r"default_via_diameter=([\d.]+),",
                # Anchored on the immediately-preceding literal default
                # (default_trace_width=0.2,), NOT the generic
                # "#[pyo3(signature = (" marker -- that marker appears 3x
                # in this file (ViaTemplate::new, DesignRules::new, and a
                # third pymethod), and .search() would otherwise silently
                # lock onto the WRONG occurrence (ViaTemplate::new's, which
                # has no default_via_diameter field at all -- verified by
                # grep before writing this).
                scope_anchor=r"default_trace_width=0\.2,",
                scope_lines=6,
            ),
        ),
        notes=(
            "NEW DIVERGENCE found by the 2026-08-17 (session 2) sweep, "
            "KNOWN RED, deliberately not fixed here. design_rules.rs's "
            "pyo3 #[new] constructor default is 0.6mm, not 0.9mm -- the "
            "exact pre-2026-08-13 stale figure every OTHER home of this "
            "fact was raised away from. It is reachable only via a bare "
            "`DesignRules()` construction (no kwargs), which does not "
            "occur in production Python (both call sites that bare-"
            "construct a 'DesignRules' -- router_v6/_astar_nlayer.py:1035, "
            "router_v6/_astar_reconstruct.py:117 -- import the UNRELATED "
            "stage0_data.DesignRules Python dataclass, not this Rust "
            "pyclass, confirmed by import-site grep), so it is currently "
            "vestigial, same shape as the historical _parse_nets.py "
            "'vestigial but live' incident this family's own motivation "
            "cites -- one accidental refactor (e.g. a caller switching "
            "which DesignRules it imports, or a future bare construction "
            "of core.design_rules.DesignRules) turns it live. NOT fixed "
            "here: this exact default is field-for-field pinned by the "
            "PINNED oracle tests/core/_design_rules_py_oracle.py (its own "
            "`default_via_diameter: float = 0.6` dataclass field default, "
            "line ~200), so a mechanical fix requires the standing oracle "
            "re-pin ceremony -- not an agent fiat action, same rule that "
            "blocked mains_voltage_v's remaining two sites above."
        ),
    ),
    Fact(
        name="default_via_drill_mm",
        category="via-geometry",
        authoritative_value=0.3,
        value_kind="float",
        authoritative_source=(
            "Same citation as default_via_diameter_mm above -- the drill "
            "diameter did not change in the 2026-08-13 fab-floor fix "
            "(0.6->0.9mm was the pad diameter; drill stayed 0.3mm), so "
            "0.3mm is unanimous across every home including the Rust "
            "pyo3 constructor (unlike the diameter fact above)."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/src/temper_placer/core/design_rules.py",
                description="create_temper_design_rules() DesignRules(...) default_via_drill",
                pattern=r"default_via_drill=([\d.]+),",
                scope_anchor=r"def create_temper_design_rules\(\)",
                scope_lines=25,
            ),
            FactSite(
                file="packages/temper-placer/src/temper_placer/io/_parse_nets.py",
                description="_extract_design_rules() fallback default_via_drill",
                pattern=r"default_via_drill\s*=\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/src/temper_placer/router_v6/stage0_data.py",
                description="stage0_data.DesignRules dataclass field default",
                pattern=r"default_via_drill_mm:\s*float\s*=\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-placer/src/temper_placer/router_v6/constraints_design_rules.py",
                description="constraints_design_rules.DesignRules dataclass field default",
                pattern=r"default_via_drill:\s*float\s*=\s*([\d.]+)",
            ),
            FactSite(
                file="packages/temper-design-bundle/src/design_rules.rs",
                description="Rust DesignRules::new() #[pyo3(signature=...)] bare-constructor default",
                pattern=r"default_via_drill=([\d.]+),",
                # See the diameter FactSite above for why this is anchored
                # on the preceding literal default, not the generic
                # "#[pyo3(signature = (" marker (3 occurrences in this
                # file; .search() would lock onto the wrong one).
                scope_anchor=r"default_trace_width=0\.2,",
                scope_lines=6,
            ),
        ),
        notes=(
            "Companion to default_via_diameter_mm above. Expected CLEAN -- "
            "included so the pair is checked together and so a future "
            "drill-only drift (independent of the known-red diameter "
            "divergence) cannot hide next to it."
        ),
    ),
    # -------------------------------------------------------------------
    # The annular-ring fabrication FLOOR itself (as opposed to the via
    # pad/drill pairs above, which are the values chosen to CLEAR it).
    #
    # 968d1a33d (PR #1316) gave this fact a second home: `Via::new`
    # (temper-orchestration) now enforces the floor at construction, so
    # the crate carries its own copy of a number the board file already
    # declared. Two homes, no link -- precisely the shape this gate
    # exists for, and precisely the shape that had just cost this project
    # 56 unfabricable vias. Registered the day the second home appeared,
    # rather than the day they drift.
    # -------------------------------------------------------------------
    Fact(
        name="min_via_annular_ring_mm",
        category="via-geometry",
        authoritative_value=0.254,
        value_kind="float",
        authoritative_source=(
            "pcb/temper.kicad_pro board.design_settings.rules."
            "min_via_annular_width = 0.254, enforced by KiCad DRC at "
            "severity 'error' (board.design_settings.rule_severities."
            "annular_width) -- i.e. the board does not fabricate below "
            "it. Sourced from JLCPCB's 2oz-copper PTH minimum per "
            "docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md, "
            "the same floor the 2026-08-13 board-wide sweep raised every "
            "net-class via pair (default_via_diameter_mm above) to clear. "
            "It is a fabricator constraint, not a tunable: a mismatch "
            "here is fixed by correcting whichever home moved, never by "
            "lowering the floor."
        ),
        homes=(
            FactSite(
                file="pcb/temper.kicad_pro",
                description="board DRC rule min_via_annular_width (the fab SSOT)",
                pattern=r'"min_via_annular_width":\s*([\d.]+)',
            ),
            FactSite(
                file="packages/temper-orchestration/src/pipeline_route.rs",
                description="Via::new's construction-time annular floor (PR #1316)",
                pattern=r"pub const MIN_ANNULAR_RING_MM: f64 = ([\d.]+);",
            ),
        ),
        notes=(
            "Expected CLEAN. Registered 2026-08-18 alongside the repair of "
            "the eight router_v6 tests that PR #1316 left holding the "
            "pre-floor 0.6mm via pad. Those eight rotted because a Rust "
            "behaviour change had no link to the Python side; this entry "
            "is the mechanical half of the link (the Rust constant is now "
            "also exported to Python as "
            "temper_orchestration.MIN_ANNULAR_RING_MM, and "
            "packages/temper-placer/tests/router_v6/"
            "test_via_annular_floor_guard.py pins the behaviour). Note "
            "this gate reads pcb/temper.kicad_pro, NOT the board file "
            "pcb/temper.kicad_pcb."
        ),
    ),
    # -------------------------------------------------------------------
    # Gate-drive net names: GATE_HS/GATE_LS are the real board net names
    # (verified against pcb/temper.kicad_pcb -- 'GATE_H'/'GATE_L' do not
    # exist as board nets). PhysicsGate._GATE_NETS carried the stale
    # 'GATE_H'/'GATE_L' pair until PR #1310 fixed it 2026-08-17 (same day,
    # earlier session) -- these two facts are the regression guard for
    # that exact fix, per the coordination instruction to register an
    # invariant a sibling's fix already removed so it cannot silently
    # return. String-valued facts (value_kind="str") -- exercises the
    # extension to the registry mechanism this changeset adds (previously
    # float/int only).
    # -------------------------------------------------------------------
    Fact(
        name="gate_drive_hs_net_name",
        category="net-name",
        authoritative_value="GATE_HS",
        value_kind="str",
        authoritative_source=(
            "pcb/temper.kicad_pcb's own net table (grep -o 'GATE_H[A-Z]*' "
            "-- the board declares GATE_HS, never bare GATE_H). U7 "
            "(UCC21550 gate driver) OUTA drives this net -- see "
            "packages/temper-placer/configs/gate_driver_constraints.yaml's "
            "own 'was \"GATE_H\" -- real board net' comment."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py",
                description="PhysicsGate._GATE_NETS[0] (high-side gate-drive net)",
                pattern=r'_GATE_NETS:\s*tuple\[str, str\]\s*=\s*\("([^"]+)"',
            ),
            FactSite(
                file="packages/temper-placer/configs/gate_driver_constraints.yaml",
                description="high-side gate-drive loop entry name:",
                pattern=r'-\s*name:\s*"([^"]+)"\s*#\s*was "GATE_H"',
            ),
        ),
    ),
    Fact(
        name="gate_drive_ls_net_name",
        category="net-name",
        authoritative_value="GATE_LS",
        value_kind="str",
        authoritative_source=(
            "Same as gate_drive_hs_net_name above -- U7 OUTB drives GATE_LS."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py",
                description="PhysicsGate._GATE_NETS[1] (low-side gate-drive net)",
                pattern=r'_GATE_NETS:\s*tuple\[str, str\]\s*=\s*\("[^"]+",\s*"([^"]+)"\)',
            ),
            FactSite(
                file="packages/temper-placer/configs/gate_driver_constraints.yaml",
                description="low-side gate-drive loop entry name:",
                pattern=r'-\s*name:\s*"([^"]+)"\s*#\s*was "GATE_L"',
            ),
        ),
    ),
    # -------------------------------------------------------------------
    # FIXED 2026-08-17 (docs/evidence/2026-08-17-gate-drive-ampacity-key-
    # rename-fix.md). Originally registered as a TOOL ERROR by PR #1320
    # (docs/evidence/2026-08-17-fact-registry-drift-gate-extension.md
    # SS3.3) and deliberately left unfixed there: the per-net expected-
    # current table StackupGate uses for its IPC-2221B ampacity check (and
    # the Rust kernel it's differentially compared against) was never
    # updated from 'GATE_H'/'GATE_L' to 'GATE_HS'/'GATE_LS' -- unlike
    # PhysicsGate._GATE_NETS above, which PR #1310 DID fix. Traced effect,
    # confirmed both statically and by running this gate script itself
    # (which went from reporting a TOOL ERROR at both homes to CLEAN once
    # the keys were added, with no other fact's state affected): a real
    # net named "GATE_HS" looked up via
    # StackupGate._resolve_net_current("GATE_HS") used to exact-match-MISS
    # in `_DEFAULT_NET_CURRENTS` (only "GATE_H" was a key) and fall to the
    # 0.1A default, even though temper_drc_rs.get_net_current("GATE_HS")'s
    # case-insensitive SUBSTRING match found 2.0A via the stale "GATE_H"
    # key -- the disagreement made `_resolve_net_current`'s own documented
    # dispatch rule keep the WRONG (Python exact-table) answer, 0.1A.
    # Separately verified: the production trace-WIDTH-ASSIGNMENT path
    # (router_v6/trace_width_assignment.py's `_resolve_current_a`) calls
    # `temper_drc_rs.get_net_current` directly (not through this Python
    # table), so it already resolved "GATE_HS"/"GATE_LS" to 2.0A via the
    # same substring coincidence -- the bug this fact guards was confined
    # to the DRC-gate CHECK (which is itself only reachable via
    # `--all-gates`, not the default CI-run gate list), not to what sized
    # the board's copper. See the evidence doc for the full trace and the
    # measured before/after DRC and trace-width consequence.
    # -------------------------------------------------------------------
    Fact(
        name="gate_hs_net_current_rating_a",
        category="net-name",
        authoritative_value="GATE_HS",
        value_kind="str",
        authoritative_source=(
            "Same real-board net name as gate_drive_hs_net_name above. "
            "The 2.0A rating itself is not in question (it is already "
            "correctly cited for the stale 'GATE_H' key, W2 R3 "
            "requirements) -- only the KEY is wrong. This fact's pattern "
            "therefore searches for a 'GATE_HS' key specifically (not a "
            "value comparison) so a missing citation reports as a TOOL "
            "ERROR, not a false CLEAN."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py",
                description="StackupGate._DEFAULT_NET_CURRENTS 'GATE_HS' key (MISSING)",
                pattern=r'"(GATE_HS)":\s*[\d.]+,',
                scope_anchor=r"_DEFAULT_NET_CURRENTS:\s*dict\[str, float\]\s*=\s*\{",
                scope_lines=20,
            ),
            FactSite(
                file="packages/temper-drc-rs/src/ipc.rs",
                description="net_currents() 'GATE_HS' map key (MISSING)",
                pattern=r'map\.insert\("(GATE_HS)"\.into\(\),',
                scope_anchor=r"pub fn net_currents\(\)",
                scope_lines=25,
            ),
        ),
        notes=(
            "FIXED 2026-08-17 (docs/evidence/2026-08-17-gate-drive-"
            "ampacity-key-rename-fix.md) -- now CLEAN at both homes. "
            "See the block comment above this entry for the full traced "
            "effect and the measured consequence."
        ),
    ),
    Fact(
        name="gate_ls_net_current_rating_a",
        category="net-name",
        authoritative_value="GATE_LS",
        value_kind="str",
        authoritative_source="Same as gate_hs_net_current_rating_a above.",
        homes=(
            FactSite(
                file="packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py",
                description="StackupGate._DEFAULT_NET_CURRENTS 'GATE_LS' key (MISSING)",
                pattern=r'"(GATE_LS)":\s*[\d.]+,',
                scope_anchor=r"_DEFAULT_NET_CURRENTS:\s*dict\[str, float\]\s*=\s*\{",
                scope_lines=20,
            ),
            FactSite(
                file="packages/temper-drc-rs/src/ipc.rs",
                description="net_currents() 'GATE_LS' map key (MISSING)",
                pattern=r'map\.insert\("(GATE_LS)"\.into\(\),',
                scope_anchor=r"pub fn net_currents\(\)",
                scope_lines=25,
            ),
        ),
        notes="See gate_hs_net_current_rating_a's notes.",
    ),
    # -------------------------------------------------------------------
    # HV<->LV separation gate threshold. UPDATED 2026-08-17 (merge of PR
    # #1322, docs/evidence/2026-08-17-netclass-classifier-manifest-and-
    # ieccreepagegate-liveness.md): this fact family previously described
    # gates.py hardcoding 6.0mm in TWO places (PhysicsGate._CREEPAGE_MIN_MM,
    # and an inline literal inside IECCreepageGate.check()'s Violation(...)
    # construction), "KNOWN RED, NOT FIXED". PR #1322 fixed both:
    # `_CREEPAGE_MIN_MM` was confirmed dead (zero read sites anywhere in the
    # file, a stale duplicate despite its own "SSOT -- do not duplicate"
    # comment) and DELETED rather than repaired -- there is no longer a site
    # here to compare. `IECCreepageGate.check()`'s `context={"required_mm":
    # ...}` no longer holds a literal; it now reads the module constant
    # `HV_LV_CREEPAGE_MM`, itself computed from the SAME safety-SSOT lookup
    # `scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_PD3_MM` uses (IEC
    # 60335-1 Table 17 row iv, >250-400V, material group IIIa/IIIb, PD3
    # basic 6.3mm x2 per cl.29.2.3 reinforced = 12.6mm --
    # docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md + PR
    # #1224/#1229), rather than a second, independently-hardcoded number.
    #
    # Both `HV_LV_CREEPAGE_MM` and `HV_CREEPAGE_PD3_MM` are now DERIVED
    # expressions (a Rust SSOT call), not literals, so neither can be
    # regex-captured as a numeric value the way the old hardcoded 6.0mm
    # could. This registry cannot execute Python/Rust to prove the two
    # derived values are equal, so it proves the next-best, fully static
    # thing instead: the two sites invoke `creepage_table_lookup` with
    # byte-identical arguments (PD level, material group, voltage band,
    # table) and the identical `* 2.0` reinforced-insulation multiplier --
    # which structurally guarantees an identical computed result (same
    # function, same inputs) without evaluating either call. See the
    # separate str-valued fact `hv_lv_creepage_derivation_parity` below.
    # `packages/temper-placer/src/temper_placer/core/isolation_constants.
    # py`'s `MIN_BARRIER_WIDTH_MM` remains a genuine literal (12.6, unlike
    # gates.py/generate_kicad_dru.py) and is kept as this fact's one
    # float-comparable home.
    #
    # STILL AN OPEN FINDING, not resolved by this merge and not this
    # agent's to resolve unilaterally (a sibling's territory per the
    # original note): DeltaMapper.to_delta() reads `violation.threshold`
    # directly from the Violation IECCreepageGate constructs
    # (packages/temper-placer/src/temper_placer/placer/cp_sat/
    # delta_mapper.py, `min_dist = violation.threshold`) -- now correctly
    # 12.6mm end-to-end per PR #1322's own verification, so the specific
    # leak this note originally warned about (a stale 6.0mm reaching
    # DeltaMapper) is FIXED. The separate interpretive question -- whether
    # IECCreepageGate filtering kicad-cli DRC `rule == "clearance"` errors
    # (not the `creepage` rule type scripts/generate_kicad_dru.py emits)
    # and calling the result "creepage" is the right DRC rule type to
    # track -- remains open, a judgment call, not resolved here.
    # -------------------------------------------------------------------
    Fact(
        name="hv_lv_separation_gate_threshold_mm",
        category="gate-threshold",
        authoritative_value=12.6,
        value_kind="float",
        authoritative_source=(
            "scripts/generate_kicad_dru.py's HV_CREEPAGE_ENFORCED_MM = "
            "HV_CREEPAGE_PD3_MM (IEC 60335-1 Table 17 row iv, >250-400V, "
            "material group IIIa/IIIb, PD3 basic 6.3mm x2 per cl.29.2.3 "
            "reinforced = 12.6mm), matching "
            "packages/temper-placer/src/temper_placer/core/"
            "isolation_constants.py's MIN_BARRIER_WIDTH_MM = 12.6. See "
            "docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md + PR "
            "#1224/#1229."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/src/temper_placer/core/isolation_constants.py",
                description="MIN_BARRIER_WIDTH_MM literal",
                pattern=r"MIN_BARRIER_WIDTH_MM\s*=\s*([\d.]+)",
            ),
        ),
        notes=(
            "FIXED 2026-08-17 by PR #1322 (merged in): both gates.py sites "
            "this fact originally tracked as hardcoded-6.0mm are gone -- "
            "_CREEPAGE_MIN_MM deleted as confirmed-dead code, and "
            "IECCreepageGate's inline literal replaced with a reference to "
            "HV_LV_CREEPAGE_MM, an SSOT-derived (not hardcoded) constant. "
            "See the block comment above and the companion "
            "hv_lv_creepage_derivation_parity fact below, which verifies "
            "gates.py and generate_kicad_dru.py derive that constant "
            "identically."
        ),
    ),
    Fact(
        name="hv_lv_creepage_derivation_parity",
        category="gate-threshold",
        authoritative_value=(
            'creepage_table_lookup(3, "IIIa/IIIb", ">250-400", "17").value_mm() * 2.0'
        ),
        value_kind="str",
        authoritative_source=(
            "scripts/generate_kicad_dru.py's HV_CREEPAGE_PD3_MM -- the "
            "fab-authoritative derivation; packages/temper-placer/src/"
            "temper_placer/placer/cp_sat/gates.py's HV_LV_CREEPAGE_MM "
            "(added by PR #1322) must invoke the identical SSOT lookup "
            "with identical arguments, or the two enforcement points can "
            "silently diverge again the way the hardcoded 6.0mm/12.6mm "
            "figures did before."
        ),
        homes=(
            FactSite(
                file="scripts/generate_kicad_dru.py",
                description="HV_CREEPAGE_PD3_MM derivation call",
                pattern=(
                    r"HV_CREEPAGE_PD3_MM\s*=\s*_tdb\."
                    r'(creepage_table_lookup\([^)]*\)\.value_mm\(\)\s*\*\s*[\d.]+)'
                ),
            ),
            FactSite(
                file="packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py",
                description="HV_LV_CREEPAGE_MM derivation call",
                pattern=(
                    r"HV_LV_CREEPAGE_MM:\s*float\s*=\s*\(\s*\n\s*_tdb\."
                    r'(creepage_table_lookup\([^)]*\)\.value_mm\(\)\s*\*\s*[\d.]+)'
                ),
            ),
        ),
        notes=(
            "NEW 2026-08-17 (docs/evidence/2026-08-17-gatedrive-class-"
            "pairs-gap.md), added when merging PR #1322's gates.py rewrite "
            "into this registry. Structural parity, not a value re-"
            "derivation: both sites call the same Rust SafetyValue lookup "
            "with the same PD level, material group, voltage band, table, "
            "and reinforced-insulation multiplier, which is the strongest "
            "static guarantee obtainable without executing the Rust "
            "kernel. If either site's call is edited without the other, "
            "this fact fails (VIOLATION or TOOL ERROR), catching the "
            "divergence before it repeats the fabricated/mismatched-figure "
            "shape this project's history is full of."
        ),
    ),
    # -------------------------------------------------------------------
    # hb-gnd classification: elec/domain_manifest.yaml (PR #1145) declares
    # this net HV (the half-bridge low-side switch's return conductor --
    # power_loop.q_low.E in elec/src/modules.ato:379 -- ~-170V relative to
    # signal ground, one CT-primary-winding, not a galvanic isolator, from
    # the already-declared HV net DC_BUS_RTN). Verified independently
    # against elec/src/main.ato's own topology (dc_bus_minus/DC_BUS_RTN is
    # ~-170V from power_return, the doubler midpoint main.ato's own
    # comment calls "signal ground") -- the manifest's trace is correct,
    # not merely asserted. See docs/evidence/2026-08-17-hb-gnd-design-
    # rules-classification-blast-radius.md.
    #
    # Three homes previously disagreed (a fourth instance of "one fact,
    # many homes, drifting", on top of the three PR #1322's evidence doc
    # already found in netclass_constraints.py/gates.py):
    #   1. elec/domain_manifest.yaml's HV domain list -- always correct.
    #   2. router_v6.clearance_check's retained manifest loader feeds the
    #      Rust-only backend; its consumer test asserts the literal entry.
    #   3. core.design_rules.TEMPER_NET_ASSIGNMENTS -- had NO entry for
    #      hb-gnd at all (confirmed live: scripts/check_hv_netclass_
    #      coverage.py PROPERTY 1 flagged it, a currently-red, CI-blocking
    #      violation). FIXED by this changeset ("HighVoltage", matching
    #      DC_BUS_RTN's existing entry).
    #   4. pcb/temper.kicad_pro's net_settings.netclass_assignments -- the
    #      file kicad-cli's DRC actually reads. Still has NO entry for
    #      hb-gnd (falls to KiCad's "Default" 0.2mm/no-creepage class on
    #      the real fab-authoritative DRC path -- weaker than even a
    #      generic LV class). scripts/check_hv_netclass_coverage.py
    #      PROPERTY 3 already flags this, independently of fact #3 above.
    #      LEFT RED, NOT FIXED HERE: measured impact of syncing this entry
    #      is 28 newly-surfaced clearance/creepage violations against 18
    #      distinct LV/SELV nets physically close to hb-gnd's routed
    #      copper (WDT_KICK x8, +3V3, I_SENSE, RTD_SDI, i2c_sda_ui,
    #      thermal.j_fan-p1, etc. -- see the evidence doc) -- real,
    #      previously-invisible exposure that needs routing/placement
    #      remediation (moving copper), which this task's hard rules
    #      forbid an agent from doing unilaterally. Registered as a KNOWN
    #      TOOL ERROR (missing citation, not a wrong value) so it cannot
    #      silently regress further AND so it stays visible until an
    #      owner authorizes the board-write + remediation.
    #
    # Two facts, split by vocabulary (mirrors why check_hv_netclass_
    # coverage.py keeps PROPERTY 1 and PROPERTY 3 separate -- different
    # homes spell the same verdict differently: domain-manifest/
    # clearance_check use "HV", design_rules.py/kicad_pro use the class
    # name "HighVoltage"). Fixing TEMPER_NET_ASSIGNMENTS without also
    # touching the pinned oracle (_design_rules_py_oracle.py,
    # scripts/oracle_hashes.json) intentionally leaves
    # test_design_rules_rust_differential.py::test_module_constants_
    # identical / test_create_temper_design_rules_identical RED -- per
    # this task's hard rule against re-pinning oracle hashes. That is a
    # separate, deliberate, evidenced act for a future PR, not silently
    # avoided by leaving the classification wrong.
    # -------------------------------------------------------------------
    Fact(
        name="hb_gnd_hv_domain_membership",
        category="net-name",
        authoritative_value="hb-gnd",
        value_kind="str",
        authoritative_source=(
            "elec/domain_manifest.yaml's HV domain list (PR #1145, "
            "netlist-traced) is the SSOT for domain membership. "
            "packages/temper-placer/tests/router_v6/test_clearance_check.py"
            "'s manifest-loader consumer test is the primary production "
            "proof that the literal entry reaches the Rust adapter."
        ),
        homes=(
            FactSite(
                file="elec/domain_manifest.yaml",
                description="HV domain nets list entry",
                pattern=r"(?:^|\n)\s*-\s*(hb-gnd)\b",
                scope_anchor=r"\n  HV:\n",
                scope_lines=320,
            ),
            FactSite(
                file="packages/temper-placer/tests/router_v6/test_clearance_check.py",
                description=(
                    "retained Rust adapter manifest-loader assertion"
                ),
                pattern=r'assert\s+"(hb-gnd)"\s+in\s+_load_manifest_hv_net_names\(\)',
            ),
        ),
    ),
    Fact(
        name="hb_gnd_temper_net_assignment_class",
        category="net-name",
        authoritative_value="HighVoltage",
        value_kind="str",
        authoritative_source=(
            "core.design_rules.TEMPER_NET_ASSIGNMENTS['DC_BUS_RTN'] == "
            "'HighVoltage' is the existing precedent for the same physical "
            "node one CT-primary-winding away; hb-gnd now carries the "
            "matching explicit entry (this changeset). pcb/temper.kicad_pro"
            "'s net_settings.netclass_assignments is the file kicad-cli's "
            "DRC actually reads and is the propagation target "
            "scripts/sync_kicad_netclass_assignments.py exists for."
        ),
        homes=(
            FactSite(
                file=(
                    "packages/temper-placer/src/temper_placer/core/"
                    "design_rules.py"
                ),
                description="TEMPER_NET_ASSIGNMENTS['hb-gnd']",
                pattern=r'"hb-gnd":\s*"([^"]+)"',
            ),
            FactSite(
                file="pcb/temper.kicad_pro",
                description="net_settings.netclass_assignments['hb-gnd'] (MISSING)",
                pattern=r'"hb-gnd":\s*"([^"]+)"',
            ),
        ),
        notes=(
            "The kicad_pro home is a KNOWN TOOL ERROR (no entry exists "
            "yet), deliberately not fixed here -- see the block comment "
            "above this entry for the measured 28-violation/18-net "
            "propagation impact and why applying it needs an owner "
            "decision plus routing remediation, not a mechanical sync."
        ),
    ),
)

# ---------------------------------------------------------------------------
# Per-netclass via diameter/drill pairs
# ---------------------------------------------------------------------------
# Table-driven rather than 26 hand-written Fact() blocks (13 classes x 2
# fields): packages/temper-placer/src/temper_placer/core/design_rules.py's
# TEMPER_NET_CLASSES is the declared SSOT (netclass_rules.yaml's own
# comments say so explicitly, e.g. HighVoltageSignal's "Matches core/
# design_rules.py's TEMPER_NET_CLASSES[...], which WAS fixed on
# 2026-08-13 -- this file had silently drifted from that SSOT ever
# since"). Every (class, diameter, drill) triple below was independently
# verified against BOTH files by this changeset's author on 2026-08-17
# (both currently agree -- this is a regression guard, not a currently-
# red finding) -- the exact fact family that let a HighVoltageSignal
# 0.8/0.4-vs-1.0/0.4 mismatch put 56 vias below the JLCPCB annular-ring
# fab floor for four days before discovery. Still an explicit,
# hand-reviewed list per this file's own design rationale -- the loop
# below only saves writing 26 near-identical Fact() blocks, it does not
# make the table itself less reviewed.
NETCLASS_VIA_TABLE: tuple[tuple[str, float, float], ...] = (
    # (class name, via_diameter_mm, via_drill_mm)
    ("ACMains", 1.2, 0.6),
    ("HighVoltage", 1.2, 0.6),
    ("HighVoltageTank", 1.2, 0.6),
    ("HighVoltageSignal", 1.0, 0.4),
    ("HighVoltageIsolated", 1.1, 0.5),
    ("FinePitch", 0.8, 0.2),
    ("Power", 1.1, 0.5),
    ("GateDriveHV", 1.0, 0.4),
    ("GateDriveSELV", 1.0, 0.4),
    ("GND", 1.1, 0.5),
    ("HighSpeed", 0.9, 0.3),
    ("Signal", 0.9, 0.3),
    ("HighCurrent", 1.0, 0.4),
)


def _netclass_via_facts() -> tuple[Fact, ...]:
    facts: list[Fact] = []
    for class_name, diameter, drill in NETCLASS_VIA_TABLE:
        for field_name, value, py_field, yaml_field in (
            ("via_diameter_mm", diameter, "via_diameter", "via_diameter"),
            ("via_drill_mm", drill, "via_drill", "via_drill"),
        ):
            facts.append(
                Fact(
                    name=f"netclass_{class_name}_{field_name}",
                    category="via-geometry",
                    authoritative_value=value,
                    value_kind="float",
                    authoritative_source=(
                        f"packages/temper-placer/src/temper_placer/core/"
                        f"design_rules.py TEMPER_NET_CLASSES[{class_name!r}]"
                        f" -- the declared SSOT per netclass_rules.yaml's "
                        f"own convention (see the block comment above this "
                        f"table)."
                    ),
                    homes=(
                        FactSite(
                            file="packages/temper-placer/src/temper_placer/core/design_rules.py",
                            description=f"TEMPER_NET_CLASSES[{class_name!r}].{py_field}",
                            pattern=rf"{py_field}=([\d.]+),",
                            scope_anchor=rf'"{class_name}":\s*NetClassRules\(',
                            scope_lines=20,
                        ),
                        FactSite(
                            file="packages/temper-placer/configs/netclass_rules.yaml",
                            description=f"classes.{class_name}.{yaml_field}",
                            pattern=rf"{yaml_field}:\s*([\d.]+)",
                            scope_anchor=rf"\n  {class_name}:\n",
                            scope_lines=20,
                        ),
                    ),
                )
            )
    return tuple(facts)


REGISTRY = REGISTRY + _netclass_via_facts()


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


@dataclass
class SiteResult:
    fact: str
    site: FactSite
    found_value: float | str | None
    matches: bool
    error: str | None = None


def _extract(repo_root: Path, fact: Fact, site: FactSite) -> SiteResult:
    path = repo_root / site.file
    if not path.is_file():
        return SiteResult(
            fact=fact.name,
            site=site,
            found_value=None,
            matches=False,
            error=f"file not found: {site.file}",
        )
    text = path.read_text(encoding="utf-8")

    search_text = text
    if site.scope_anchor is not None:
        anchor_re = re.compile(site.scope_anchor)
        anchor_match = anchor_re.search(text)
        if anchor_match is None:
            return SiteResult(
                fact=fact.name,
                site=site,
                found_value=None,
                matches=False,
                error=(
                    f"scope anchor {site.scope_anchor!r} not found in "
                    f"{site.file}"
                ),
            )
        # Scope the search to N lines starting at the anchor, so the same
        # field name elsewhere in the file cannot be matched by accident.
        start = anchor_match.start()
        prefix_lines = text[:start].count("\n")
        all_lines = text.splitlines(keepends=True)
        window = "".join(all_lines[prefix_lines : prefix_lines + site.scope_lines])
        search_text = window

    value_re = re.compile(site.pattern)
    value_match = value_re.search(search_text)
    if value_match is None:
        return SiteResult(
            fact=fact.name,
            site=site,
            found_value=None,
            matches=False,
            error=f"pattern {site.pattern!r} did not match in {site.file}",
        )
    raw = value_match.group(1)

    if fact.value_kind == "str":
        # String facts (e.g. board net names): compared by exact equality,
        # no numeric parsing. A missing/renamed site fails closed via the
        # "pattern did not match" branch above -- there is no float-parse
        # failure mode to additionally guard here.
        matches = raw == fact.authoritative_value
        return SiteResult(fact=fact.name, site=site, found_value=raw, matches=matches)

    try:
        found = float(raw)
    except ValueError:
        return SiteResult(
            fact=fact.name,
            site=site,
            found_value=None,
            matches=False,
            error=f"matched value {raw!r} in {site.file} is not numeric",
        )

    assert isinstance(fact.authoritative_value, (int, float))
    matches = abs(found - fact.authoritative_value) < 1e-9
    return SiteResult(fact=fact.name, site=site, found_value=found, matches=matches)


def run(repo_root: Path) -> list[SiteResult]:
    if not REGISTRY:
        raise GateError("REGISTRY is empty -- vacuous run, refusing to report clean")
    results: list[SiteResult] = []
    for fact in REGISTRY:
        if not fact.homes:
            raise GateError(f"fact {fact.name!r} has zero homes -- vacuous entry")
        for site in fact.homes:
            results.append(_extract(repo_root, fact, site))
    return results


def _fmt_value(v: float | str, kind: str) -> str:
    if kind == "str":
        return repr(v)
    return str(int(v)) if kind == "int" else f"{v:g}"


def _print_report(results: list[SiteResult]) -> tuple[bool, bool]:
    by_fact: dict[str, list[SiteResult]] = {}
    for r in results:
        by_fact.setdefault(r.fact, []).append(r)

    facts_by_name = {f.name: f for f in REGISTRY}
    has_violation = False
    has_tool_error = False

    for name, site_results in by_fact.items():
        fact = facts_by_name[name]
        print(f"=== {fact.category}/{fact.name} ===")
        print(f"  Authoritative: {_fmt_value(fact.authoritative_value, fact.value_kind)}")
        print(f"  Source: {fact.authoritative_source}")
        for r in site_results:
            if r.error is not None:
                has_tool_error = True
                print(f"  TOOL ERROR  {r.site.file}: {r.error}")
                continue
            assert r.found_value is not None
            tag = "OK  " if r.matches else "DIFF"
            if not r.matches:
                has_violation = True
            print(
                f"  {tag}  {r.site.file} ({r.site.description}): "
                f"{_fmt_value(r.found_value, fact.value_kind)}"
            )
        if fact.notes:
            print(f"  Notes: {fact.notes}")
        print()

    return has_violation, has_tool_error


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.parse_args()

    repo_root = find_repo_root()

    try:
        results = run(repo_root)
    except GateError as e:
        print(f"TOOL ERROR: {e}")
        sys.exit(EXIT_TOOL_ERROR)

    has_violation, has_tool_error = _print_report(results)

    if has_tool_error:
        state = "tool_error"
    elif has_violation:
        state = "violation"
    else:
        state = "clean"

    if state == "clean":
        print(f"PASS -- {len(REGISTRY)} fact(s), {len(results)} site(s), 0 divergences.")
    elif state == "violation":
        print(
            "FAILED -- a registered fact has homes with disagreeing values. "
            "See the notes above for whether this is a known, deliberately "
            "left-red finding (do not silently 'fix' by editing this "
            "registry's authoritative_value to match the wrong site)."
        )
    else:
        print(
            "TOOL ERROR -- a home file, scope anchor, or value pattern could "
            "not be resolved; the scan cannot be trusted as-is."
        )

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Fact registry drift gate: {state}\n")
            f.write(f"- Facts checked: {len(REGISTRY)}\n")
            f.write(f"- Sites checked: {len(results)}\n")

    if state == "tool_error":
        sys.exit(EXIT_TOOL_ERROR)
    sys.exit(EXIT_VIOLATION if has_violation else EXIT_CLEAN)


if __name__ == "__main__":
    main()
