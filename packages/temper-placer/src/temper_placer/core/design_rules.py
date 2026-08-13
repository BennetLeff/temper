"""
Design rules for PCB routing.

This module provides net class and design rule specifications for
controlling trace widths, clearances, and via sizes during routing.

The data model (``ViaTemplate``, ``DesignRules``) is implemented in Rust as
pyo3 pyclasses in the ``temper-design-bundle`` crate (the
``temper_design_bundle_python`` extension) — the Wave 4 Phase 2
"contracts-as-pyo3-pyclasses" pivot
(``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This module keeps the pre-migration public API unchanged and
re-exports the Rust pyclasses (the pure-delegation pattern, mirroring
``core/net_types.py`` and ``core/loop.py``).

What stays Python: the module-level constant tables (``TEMPER_NET_CLASSES``,
``TEMPER_NET_ASSIGNMENTS``) construct Pydantic ``NetClassRules`` objects,
which remain Python; ``SAFETY_CONSTANT_AUTHORITY`` derives from them; and
``create_temper_design_rules()`` assembles a ``DesignRules`` pyclass from
those tables. The pyclasses hold such cross-module objects opaquely
(``Py<PyDict>``/``Py<PyAny>``), exactly the pattern ``core/net_types.py``
uses for ``LayerIndex``.

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/core/test_design_rules_rust_differential.py`` (oracle:
``tests/core/_design_rules_py_oracle.py``); the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.

API notes (deliberate, documented deviations from the pre-migration
dataclass):
- ``DesignRules`` is a pyo3 pyclass. Its container fields ARE the Python
  ``dict``/``list`` objects: in-place mutation (``dr.net_classes[x] = ...``,
  ``dr.differential_pairs.append(...)``) persists, and every field — the four
  scalars plus the containers — is assignable, exactly like the mutable
  dataclass. The dynamically-attached ``class_pairs`` attribute is a real
  property (defaults to an empty dict), so consumers that set/read it
  (``io/netclass_loader.py``, ``placer/cp_sat/feedback.py``) behave
  identically.
- The stray ``print("DEBUG: Loading design_rules.py")`` class-body statement
  from the pre-migration module is gone (it was a debug artifact with no API
  surface); the oracle retains it verbatim.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TypeAlias

import numpy as np
import temper_design_bundle_python as _tdb

from temper_placer.core.netclass_rules_gen import NetClassRules

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

ViaTemplate = _tdb.ViaTemplate
DesignRules = _tdb.DesignRules

TEMPER_NET_CLASSES = {
    # WIDTH RECONCILED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-
    # scoping.md): trace_width was 2.5mm here (and in pcb/temper.kicad_pro),
    # disagreeing with packages/temper-placer/configs/netclass_rules.yaml's
    # 3.0mm -- a third-SSOT-drift finding from PR #1119's independent
    # investigation. 2.5mm carries only 14.08A at the IPC-2221B 40C pour
    # budget ac_l/ac_n actually route under (measured: both reach copper via
    # zone pours, never A*-routed traces) -- short of the declared 15A
    # design current by ~6%. 3.0mm carries 16.07A, the smallest standard
    # step that clears 15A with margin (required minimum: 2.73mm). Bumped to
    # match netclass_rules.yaml -- the file the router actually consumes --
    # rather than the other direction, since 3.0mm is the value that is
    # actually sufficient.
    "ACMains": NetClassRules(
        name="ACMains",
        trace_width=3.0,
        clearance=6.0,
        via_diameter=1.2,
        via_drill=0.6,
        via_template="Via2x2",
        voltage_v=240.0,
        creepage_mm=6.0,
        routing_strategy="plane_required",
        dru_priority=10,
        required_layer=None,
        safety_category="AC",
    ),
    # FIXED 2026-08-12 (docs/evidence/2026-08-12-netclass-param-reconciliation.md):
    # clearance was 6.0, disagreeing with pcb/temper.kicad_pro's HighVoltage
    # clearance (2.0, unchanged since the file's introduction). 6.0's own
    # citation ("IEC 60335-1 Table 16 working isolation at 400V", still
    # attached to netclass_rules.yaml's matching entry before this fix) is
    # independently debunked: Table 16 has no 400V row and no 6.0mm value.
    # 2.0 is what kicad-cli actually enforces for same-class HighVoltage
    # pairs and traces to a real, cited derivation (HV_INTERNAL_CLEARANCE_MM,
    # scripts/generate_kicad_dru.py:63). elec/src/constraints.ato -- the
    # project's original SSOT -- carries two separate HighVoltage fields,
    # `clearance = 2.0mm` and `air_clearance = 6.0mm`; kicad_pro matches the
    # former exactly and this table matched the latter exactly, consistent
    # with a field-name conflation during the Python port. Measured: this
    # value is not consumed by scripts/generate_kicad_dru.py's per-class
    # trace-width loop (only .trace_width is), so the change has zero
    # kicad-cli DRC effect; U6 isolator placement feasibility is also
    # unaffected (infeasible at both 2.0 and 6.0 -- the isolation barrier's
    # own corridor geometry is the bottleneck, not this clearance). Whether
    # 2.0 is itself IEC-adequate for the same-domain, no-creepage-backstop
    # HighVoltage-to-HighVoltage case is NOT resolved by this fix -- see the
    # evidence doc's open-question section.
    # WIDTH RE-SCOPED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-
    # scoping.md, following PR #1119's investigation): this class used to
    # bundle a 1000x current range under one 3.0mm width -- the tank/DC-bus
    # nets at 22.5A RMS thermal design current (elec/src/modules.ato:585-593)
    # down to the discharge bleed string at ~20mA
    # (discharge.k_dis1-nc/k_dis2-nc, ~170V/(3.9k+4.7k)) and mA-scale
    # voltage-domain-only taps (a, zcd, hb.power_loop.q_high-g, +15V_LS).
    # 3.0mm was short of the bus/tank current's own 40C-pour-budget
    # requirement (4.77mm at 22.5A) by ~37%, while being wildly over-built
    # for the mA-scale members. RE-SCOPED, not re-valued: the mA-scale
    # members moved OUT to the new HighVoltageSignal class below (same
    # clearance/creepage/voltage/safety_category -- same voltage domain --
    # different current tier), and this class's remaining members (the
    # 22.5A RMS pour nets AND the 15A w1_1/w1_2/power_in.ntc-no trace nets,
    # which measure as real routed copper on the real board, not pours --
    # see PR #1119 S2.2) share ONE width: 5.0mm. 5.0mm clears the pour tier's
    # own 4.77mm requirement (22.5A RMS, 40C pour) with margin and, with more
    # margin (~20%), the trace tier's 4.16mm requirement (15A, 20C trace) --
    # a deliberate reuse of one width across two current sub-bands rather
    # than a third class, matching this task's "reuse existing classes"
    # instruction; feasibility of exactly this 3.0->5.0mm HighVoltage/
    # HighVoltageTank change was already measured in PR #1119 (TRUE
    # clearance 1814->1282, TRUE track_width 841->802, creepage 164->149,
    # pad connectivity 49/139->48/139 -- noise, not a regression).
    "HighVoltage": NetClassRules(
        name="HighVoltage",
        trace_width=5.0,
        clearance=2.0,
        via_diameter=1.2,
        via_drill=0.6,
        via_template="Via3x3",
        voltage_v=400.0,
        creepage_mm=6.0,
        routing_strategy="plane_required",
        dru_priority=20,
        required_layer="B.Cu",
        safety_category="HV",
    ),
    "FinePitch": NetClassRules(
        name="FinePitch",
        trace_width=0.127,
        clearance=0.1,
        via_diameter=0.4,
        via_drill=0.2,
        via_template="Via1x1",
        dru_priority=30,
        required_layer=None,
        safety_category="LV",
    ),
    # FIXED 2026-08-12 (docs/evidence/2026-08-12-netclass-param-reconciliation.md):
    # all four scalar fields disagreed with pcb/temper.kicad_pro's Power
    # class (clearance 0.25 vs 0.5, trace_width 0.5 vs 1.0, via_diameter 0.8
    # vs 1.0, via_drill 0.4 vs 0.5). The old values here matched
    # HighCurrent's row in this same table byte-for-byte (0.25/0.5/0.8/0.4)
    # -- the established field/class-mixup failure mode, not an independent
    # Power derivation. kicad_pro's values (0.5/1.0/1.0/0.5) instead match
    # BOTH elec/src/constraints.ato's `module Power` (trace_width=1.0mm,
    # clearance=0.5mm -- the project's original SSOT; .ato has no
    # via_diameter/via_drill fields) and docs/specs/NET_CLASS_SPECIFICATION.md
    # SS2/SS3.2's formal "Power (Low Voltage Rails)" row (1.0mm trace /
    # 0.5mm clearance / 1.0mm via pad / 0.5mm via drill / 3A), independently
    # of each other. kicad_pro was correct; this table was wrong.
    "Power": NetClassRules(
        name="Power",
        trace_width=1.0,
        clearance=0.5,
        via_diameter=1.0,
        via_drill=0.5,
        via_template="Via2x2",
        dru_priority=40,
        required_layer=None,
        safety_category="LV",
    ),
    # Split 2026-07-28 (R4,
    # docs/plans/2026-07-28-003-refactor-ato-net-classification-ssot-plan.md
    # U7) from the single "GateDrive" class, which spanned both sides of
    # U7's (the UCC21550 gate driver's) reinforced isolation barrier:
    # GATE_HS/GATE_LS/GATE_H/GATE_L are the secondary-side (HV, floating on
    # SW_NODE) gate outputs; PWM_HS/PWM_LS/PWM_H/PWM_L are the primary-side
    # (SELV) MCU PWM inputs. Every clearance/width/via value below is
    # unchanged from the pre-split class -- only the class model and
    # safety_category differ.
    "GateDriveHV": NetClassRules(
        name="GateDriveHV",
        trace_width=0.4,
        clearance=0.25,
        via_diameter=0.8,
        via_drill=0.4,
        via_template="Via1x1",
        dru_priority=50,
        required_layer="F.Cu",
        # NOT "LV": GATE_HS/GATE_LS float on SW_NODE, same HV domain as
        # HighVoltage (elec/domain_manifest.yaml). Leaving this "LV" would
        # reproduce the exact failure this split exists to fix.
        safety_category="HV",
    ),
    "GateDriveSELV": NetClassRules(
        name="GateDriveSELV",
        trace_width=0.4,
        clearance=0.25,
        via_diameter=0.8,
        via_drill=0.4,
        via_template="Via1x1",
        dru_priority=51,
        required_layer="F.Cu",
        safety_category="LV",
    ),
    # routing_strategy="plane_preferred" added per R3 of
    # docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md: this field
    # was previously left at its Python default (None), silently
    # disagreeing with packages/temper-placer/configs/temper_constraints.yaml
    # (GND, lines ~315-323: "routing_strategy: plane_preferred") and with
    # docs/evidence/2026-07-28-pour-strategy-audit.md's Task 1 verdict for
    # PWR_RTN specifically (KEEP the copper -- never DELETE). GND lost its
    # pour by accident, not by decision, when _zone_layers_for_net() was
    # fixed to read this field instead of a hardcoded 5-class list -- this
    # field never declared what the config file already said. See R3-R5 of
    # the plan above; _zone_layers_for_net (_zone_pour_stitch.py) is the
    # paired fix that makes the eligibility check recognize this tier.
    "GND": NetClassRules(
        name="GND",
        trace_width=1.0,
        clearance=0.3,
        via_diameter=1.0,
        via_drill=0.5,
        via_template="Via3x3",
        routing_strategy="plane_preferred",
        dru_priority=60,
        required_layer=None,
        safety_category="LV",
    ),
    "HighSpeed": NetClassRules(
        name="HighSpeed",
        trace_width=0.15,
        clearance=0.2,
        via_diameter=0.6,
        via_drill=0.3,
        target_impedance=50.0,
        via_template="Via1x1",
        dru_priority=70,
        required_layer=None,
        safety_category="LV",
    ),
    "Signal": NetClassRules(
        name="Signal",
        trace_width=0.2,
        clearance=0.15,
        via_diameter=0.6,
        via_drill=0.3,
        via_template="Via1x1",
        dru_priority=80,
        required_layer=None,
        safety_category="LV",
    ),
    "HighCurrent": NetClassRules(
        name="HighCurrent",
        trace_width=0.5,
        clearance=0.25,
        via_diameter=0.8,
        via_drill=0.4,
        via_template="Via4x4",
        dru_priority=90,
        required_layer=None,
        safety_category="HV",
    ),
    # HighVoltageIsolated - gate-drive floating bootstrap supply (+5V_ISO,
    # VBOOT_H, VBOOT_L, and the UCC21550 gate driver's own secondary bias
    # nets hb.gate_hs.driver-p1-1 (VDDA) / hb.gate_hs.driver-p2 (VSSA)).
    #
    # FIXED 2026-07-28 (docs/evidence/2026-07-28-netclass-defect-reconciliation.md):
    # this class was added to pcb/temper.kicad_pro and
    # packages/temper-placer/configs/netclass_rules.yaml on 2026-07-28
    # (docs/evidence/2026-07-28-hv-isolated-rules-and-creepage-triage.md,
    # commit 71dba365) but never added HERE -- this table (the Python
    # placer/router's own net-class model) had zero entries for it, so
    # every net in this class fell through to Default for any Python-side
    # (CP-SAT placer, router_v6) clearance/routing decision even though the
    # real KiCad DRC truth-gate already enforced it correctly. Same drift
    # shape as the +340V_BUS defect (commit 688c15bb) this evidence doc's
    # own precedent cites -- a fix landing in some assignment tables and not
    # others. Parameters mirror netclass_rules.yaml's own HighVoltageIsolated
    # entry exactly (clearance/creepage 6.0mm, trace_width 2.0mm, voltage
    # 20V, safety_category HV -- elec/domain_manifest.yaml puts every net in
    # this class in the SAME HV domain as ac_l/+170V_BUS/SW_NODE).
    # ADDED 2026-08-12 (docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md).
    #
    # WHY A SEPARATE CLASS AND NOT A RAISE OF `HighVoltage`: the `HighVoltage`
    # class above conflates a 340-400 V DC bus with the series-resonant tank's
    # cap<->coil junction, which is not rail-clamped and measures 923.7 V peak /
    # 570.5 Vrms at the worst OCP-01-passing corner (ngspice against
    # simulation/harness/nets/zvs_margin_sweep.cir; per-net table in
    # docs/evidence/2026-08-12-hv-clearance-adequacy.md sec 2.3/3.2). Those two
    # working voltages land in DIFFERENT rows of IEC 60335-1's creepage tables
    # -- row iv (>250-400 V) for the bus, row vi (>500-800 V) for the tank node
    # -- so one class cannot carry one correct creepage figure for both. The
    # same evidence measured the alternative: raising `HighVoltage` wholesale
    # costs +5 clearance violations at the smallest step (3.0mm) and breaches
    # power_pcb_dataset/drc_ceiling.json, because it is the bus/relay/rectifier
    # nets -- at most 400 V -- that are packed tight, not the tank node.
    #
    # WHY 6.3mm: IEC 60335-1 Table 18 ("Minimum Creepage Distances for
    # FUNCTIONAL Insulation", clauses 29.2.4 and L-2), band >500 and <=800 V,
    # material group IIIa/IIIb, pollution degree 2 = 6.3mm. Table 18 is the
    # correct table for this pair (functional, not basic, insulation) and above
    # 500 V it is numerically IDENTICAL to Table 17 -- the functional-insulation
    # concession that exists in rows i-v is gone by row vi. Full transcription
    # and the clause-29.2.4 exemption analysis:
    # docs/evidence/2026-08-12-hv-hv-creepage-determination.md sec 3.1-3.3.
    # PD2 is the repo's selected pollution degree
    # (docs/evidence/2026-08-11-pd2-decision-record.md D1; PD3 would be 10.0mm,
    # and that record's own sec 2 notes PD3 governs the as-built construction
    # until the sealed compartment lands -- so 6.3mm is a FLOOR, not a ceiling).
    #
    # `clearance` is deliberately IDENTICAL to `HighVoltage`'s 2.0mm:
    # docs/evidence/2026-08-12-hv-clearance-adequacy.md settled that 2.0mm is
    # adequate for every HighVoltage pair on this board including this one, and
    # docs/evidence/2026-08-12-netclass-param-reconciliation.md settled the
    # value. This class changes the CREEPAGE requirement only.
    # WIDTH RE-SCOPED 2026-08-13, same task/evidence doc as HighVoltage above.
    # tank.c_tank1-p2 carries the same 22.5A RMS tank current as the
    # HighVoltage bus nets (it IS the cap<->coil junction the current flows
    # through) -- only creepage differs from HighVoltage (6.3mm vs 6.0mm,
    # Table 18 row vi vs row iv, per the class's own header comment). Width
    # tracks HighVoltage's bump 3.0->5.0mm for the identical current-band
    # reason; this net is unrouted on the real board today (PR #1119 S2.2),
    # a pre-existing routability gap this width change does not create or
    # resolve.
    "HighVoltageTank": NetClassRules(
        name="HighVoltageTank",
        trace_width=5.0,
        clearance=2.0,
        via_diameter=1.2,
        via_drill=0.6,
        via_template="Via3x3",
        voltage_v=923.7,
        creepage_mm=6.3,
        routing_strategy="plane_required",
        dru_priority=21,
        required_layer="B.Cu",
        safety_category="HV",
    ),
    # ADDED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-scoping.md):
    # the mA-scale current tier carved OUT of HighVoltage above -- same
    # voltage domain (elec/domain_manifest.yaml's `HV` domain: these nets
    # float with or tap directly off SW_NODE/the bus, same as HighVoltage's
    # own members), so clearance/creepage_mm/voltage_v/safety_category are
    # IDENTICAL to HighVoltage's -- this class changes the CURRENT/WIDTH
    # requirement only, exactly mirroring how HighVoltageTank (2026-08-12)
    # changed the CREEPAGE requirement only while keeping clearance
    # identical. Members: discharge.k_dis1-nc/k_dis2-nc (bleed string,
    # ~20mA, 170V/(3.9k+4.7k), modules.ato:1171-1173), hb.power_loop.q_high-g
    # (Q_high gate tap, one resistor from GATE_HS), a/zcd (U3's ZCD divider
    # tap and primary/LED-anode net), +15V_LS (low-side gate-driver bias
    # rail, floats on DC_BUS_RTN -- current per TRACE_WIDTH_CALCULATIONS.md
    # S3.8's own "Gate Driver Supply (15V)" case: 100mA quiescent + gate-
    # charge bursts, peak 500mA).
    #
    # WIDTH 0.5mm: IPC-2221B math for any of these currents (<=500mA, 20C
    # trace) computes to a fraction of a mil -- "too thin for manufacturing"
    # in the same shape TRACE_WIDTH_CALCULATIONS.md S3.8 already hits for its
    # own 0.5A case, whose recommendation ("Minimum: 0.5mm (20 mils) for
    # manufacturability") this class's width is taken from directly, rather
    # than an unrelated class's figure (GateDriveHV's 0.4mm is sized for a
    # fast-transient switching-current signal, different physics, not a
    # supply-rail/bleed-current manufacturability floor).
    "HighVoltageSignal": NetClassRules(
        name="HighVoltageSignal",
        trace_width=0.5,
        clearance=2.0,
        via_diameter=0.8,
        via_drill=0.4,
        via_template="Via1x1",
        voltage_v=400.0,
        creepage_mm=6.0,
        dru_priority=22,
        required_layer=None,
        safety_category="HV",
    ),
    "HighVoltageIsolated": NetClassRules(
        name="HighVoltageIsolated",
        trace_width=2.0,
        clearance=6.0,
        via_diameter=1.0,
        via_drill=0.5,
        via_template="Via1x1",
        voltage_v=20.0,
        creepage_mm=6.0,
        dru_priority=25,
        required_layer="F.Cu",
        safety_category="HV",
    ),
}

# Net class assignments matching KiCad project (temper.kicad_pro)
TEMPER_NET_ASSIGNMENTS = {
    # ACMains - Mains voltage (240V AC)
    "AC_L": "ACMains",
    "AC_N": "ACMains",
    "ac_l": "ACMains",
    "ac_n": "ACMains",
    "PE": "ACMains",
    # HighVoltage - DC bus (300-400V DC)
    # RENAMED: the board and netlist call this rail "+170V_BUS" (12
    # occurrences in pcb/temper.kicad_pcb; "+340V_BUS" appears zero
    # times). The stale key left the live DC bus with no netclass at
    # all, so it fell through to DesignRules' LV default clearance and
    # creepage -- see scripts/check_hv_netclass_coverage.py.
    "+170V_BUS": "HighVoltage",
    "DC_BUS_RTN": "HighVoltage",
    "DC_BUS+": "HighVoltage",
    "DC_BUS-": "HighVoltage",
    "SW_NODE": "HighVoltage",
    # FIXED 2026-07-28 (docs/evidence/2026-07-28-netclass-defect-reconciliation.md):
    # "+15V_LS" was misclassified below under "Power" despite
    # elec/domain_manifest.yaml declaring it an HV-domain net ("low-side
    # gate-driver rail; referenced to DC_BUS_RTN, not gnd -- floats within
    # the HV domain, not SELV") -- an HV-domain net was being held to LV
    # separation rules, and inflated the creepage violation count with 3
    # false positives (HV-to-LV/HighVoltageIsolated-to-LV rules tripping on
    # a same-domain pair). Moved here to match the manifest, not the name.
    #
    # RE-SCOPED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-
    # scoping.md): moved on again, from "HighVoltage" to the new
    # "HighVoltageSignal" class -- same voltage domain (clearance/creepage/
    # voltage_v/safety_category unchanged), but +15V_LS is a gate-driver
    # bias-supply rail (<=500mA peak per TRACE_WIDTH_CALCULATIONS.md S3.8),
    # not a 15-22.5A bus/tank current-carrying net, and HighVoltage's own
    # width just moved to 5.0mm for the current-carrying tier. This is a
    # current-band re-scope, not a domain change.
    "+15V_LS": "HighVoltageSignal",
    # ADDED 2026-07-28, same evidence doc. "a" (U3's own primary/LED-anode
    # net, between the ZCD divider tap and the H11L1 opto's series
    # resistor -- elec/build/default.net net 24, U3 pin 1 <-> R9 pin 2) was
    # entirely absent from this table, so it fell through to the
    # unclassified "Default" class and no HV-to-LV creepage rule ever saw
    # U3's real primary/secondary isolator crossing (the same 14.058mm slot
    # this project fitted for it). elec/domain_manifest.yaml declares it
    # HV-domain ("still entirely HV-side"). This closes that coverage gap;
    # it does not touch the isolator declaration itself
    # (elec/domain_manifest.yaml's own `power_in.zcd_opto` entry already
    # correctly separates this pin from the SELV-side VO/GND/VCC group).
    #
    # RE-SCOPED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-
    # scoping.md): moved from "HighVoltage" to "HighVoltageSignal" -- U3's
    # divider-tap/opto-anode current is uA-mA scale, not the bus/tank
    # current-carrying tier HighVoltage's 5.0mm width now targets. Same
    # clearance/creepage (this net is one pin of U3, one of the isolators
    # the PD2/8.0mm barrier is measured against -- see the evidence doc's
    # DRU-threading section for why HighVoltageSignal carries the identical
    # HV-to-LV creepage rule HighVoltage did for this exact pair).
    "a": "HighVoltageSignal",
    # ADDED 2026-07-28, sweep for siblings during the same evidence doc's
    # investigation (docs/evidence/2026-07-28-netclass-defect-reconciliation.md
    # sec "Sweep"). All 9 nets below are declared under
    # elec/domain_manifest.yaml's domains.HV.nets (traced to real wiring in
    # that file's own comments, not inferred from spelling) but were absent
    # from this table entirely -- the same false-negative shape as "a"
    # above, just not one of the two nets this task's own falsifier named.
    # 7 of the 9 were already independently classed "HighVoltage" in
    # configs/temper_production_config.yaml (an orphaned config not loaded
    # by any code path today, but corroborating evidence the manifest's
    # call is uncontroversial); the other 2 (hb.power_loop.q_high-g, zcd)
    # have their own detailed wire-tracing directly in the manifest.
    "w1_1": "HighVoltage",  # CMC winding 1 taps (line side)
    "w1_2": "HighVoltage",
    # RE-SCOPED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-
    # scoping.md): "zcd" moved "HighVoltage" -> "HighVoltageSignal" (uA-mA
    # divider tap current, not the bus/tank current tier). Per the task
    # that re-scoping was done under, "zcd" is dead circuitry from an
    # unresynced deletion (5842767c2) and is excluded from that task's
    # feasibility conclusions -- the class move is still correct/harmless
    # regardless, since it is voltage-domain-preserving.
    "zcd": "HighVoltageSignal",  # power_in's internal HV-side ZCD divider tap
    "tank-out": "HighVoltage",  # coil far end -> CT primary -> PWR_RTN
    # RECLASSIFIED 2026-08-12 (docs/evidence/2026-08-12-hv-hv-creepage-
    # enforcement.md). The old "400V-rated node" comment traced to
    # elec/src/modules.ato:534's `v_tank_peak: voltage = 400V`, which
    # docs/evidence/2026-08-12-hv-clearance-adequacy.md sec 2.3 measured to be
    # true only at the declared 47 kHz nominal: at the 44 kHz PLL floor the
    # cap voltage is 497.8 V pk and the node-to-rail differential is 837.7 V pk,
    # rising to 923.7 V pk / 570.5 Vrms at the worst OCP-01-passing corner.
    # This is the ONLY net on the board measured above 500 Vrms against any
    # other net, which is what puts it alone in IEC 60335-1 Table 18 row vi
    # (6.3mm at PD2) while every other HighVoltage net sits in row iv or below.
    # `tank-out` and `SW_NODE` deliberately stay `HighVoltage`: SW_NODE is
    # rail-clamped (measured +-173 V at every operating point) and tank-out sits
    # a CT primary away from PWR_RTN. Neither is the unclamped node.
    "tank.c_tank1-p2": "HighVoltageTank",  # cap<->coil junction, 570.5 Vrms
    "power_in.ntc-no": "HighVoltage",  # bypass relay NO -> rectified mains
    # RE-SCOPED 2026-08-13 (docs/evidence/2026-08-13-netclass-current-
    # scoping.md): the discharge bleed string is ~20mA
    # (170V/(3.9k+4.7k), modules.ato:1171-1173) -- three orders of magnitude
    # below the bus/tank current HighVoltage's 5.0mm width now targets.
    # Moved "HighVoltage" -> "HighVoltageSignal" (same voltage domain: these
    # are HV-bus-referenced contacts, open when the relay is de-energized).
    "discharge.k_dis1-nc": "HighVoltageSignal",  # k_dis1 contacts group (HV bus)
    "discharge.k_dis2-nc": "HighVoltageSignal",  # k_dis2 contacts group (HV bus)
    # RE-SCOPED 2026-08-13, same evidence doc: Q_high's gate current is
    # mA-scale gate-drive current, not bus/tank current -- moved to
    # "HighVoltageSignal".
    "hb.power_loop.q_high-g": "HighVoltageSignal",  # Q_high gate, 1 resistor from GATE_HS
    # ADDED 2026-07-28, same sweep. hb.gate_hs.driver-p1-1 (VDDA) /
    # hb.gate_hs.driver-p2 (VSSA) are the two REAL, currently-compiled nets
    # of the HighVoltageIsolated class defined above (elec/build/default.net
    # net codes 57/55) -- already correctly classed HighVoltageIsolated in
    # pcb/temper.kicad_pro since the sibling Task A fix (commit 71dba365),
    # but never added here (see the HighVoltageIsolated class comment
    # above for the full drift explanation). +5V_ISO/VBOOT_H/VBOOT_L have
    # no live counterpart in the current compiled netlist (0 occurrences,
    # verified) -- added anyway, harmless if absent, matching this table's
    # own existing +340V_BUS/AC_L-style historical-alias convention.
    "+5V_ISO": "HighVoltageIsolated",
    "VBOOT_H": "HighVoltageIsolated",
    "VBOOT_L": "HighVoltageIsolated",
    "hb.gate_hs.driver-p1-1": "HighVoltageIsolated",
    "hb.gate_hs.driver-p2": "HighVoltageIsolated",
    # FinePitch - U8 SSOP-20 (0.635mm) + RTD SPI peripherals
    "sclk": "FinePitch",
    "sdi": "FinePitch",
    "sdo": "FinePitch",
    "cs_n": "FinePitch",
    "bias": "FinePitch",
    "refin_n": "FinePitch",
    "vbias": "FinePitch",
    "RTD_SCK": "FinePitch",
    "RTD_SDI": "FinePitch",
    "RTD_CS_N": "FinePitch",
    "RTD_SDO": "FinePitch",
    "RTD_DRDY": "FinePitch",
    "RTD_HW_FAULT": "FinePitch",
    # GateDriveHV/GateDriveSELV - MOSFET gate drive signals, split 2026-07-28
    # (R4) across U7's reinforced isolation barrier. GATE_* are the
    # secondary-side (HV) gate outputs; PWM_* are the primary-side (SELV)
    # MCU PWM inputs. See the class comment in TEMPER_NET_CLASSES above.
    "GATE_HS": "GateDriveHV",
    "GATE_LS": "GateDriveHV",
    "GATE_H": "GateDriveHV",
    "GATE_L": "GateDriveHV",
    "PWM_HS": "GateDriveSELV",
    "PWM_LS": "GateDriveSELV",
    "PWM_H": "GateDriveSELV",
    "PWM_L": "GateDriveSELV",
    # Power - DC supply rails
    "+15V": "Power",
    "+3V3": "Power",
    "vcc": "Power",
    "V_BUS_SENSE": "Power",
    # GND - power return
    #
    # 2026-08-11: `gnd` was ABSENT from this table entirely, which went
    # unnoticed for as long as it did because nothing consumed the table at
    # parse time -- every net classified as "Signal" regardless (the Rust
    # parser's `Net::new` default, netlist_contracts.rs). #1041 wired
    # TEMPER_NET_ASSIGNMENTS into `parse_kicad_pcb`, and the first thing real
    # classification exposed was that the board's LARGEST net -- `gnd`, 86
    # pads, the ground return of a mains-powered board -- had no entry and so
    # still fell through to Signal (trace 0.2mm / clearance 0.15mm) rather
    # than the "GND" entry above (trace 1.0mm / clearance 0.3mm /
    # routing_strategy "plane_preferred").
    #
    # FIXED 2026-08-12 (this task; see docs/evidence/2026-08-12-nonexistent-
    # gnd-class-mapping.md): the "GND" class named above is a real,
    # genuinely-defined NetClassRules entry in THIS table (has been since
    # this module's creation, 4f315fd0d, 2025-12-25) -- but pcb/temper.
    # kicad_pro's declared classes (10 as of this session, 9 when this
    # defect was reported) never included "GND"
    # (confirmed: `json.load(open("pcb/temper.kicad_pro"))["net_settings"]
    # ["classes"]`). Assigning a net to a class name kicad_pro never declared
    # is inert on the fabrication path -- see the evidence doc for a
    # measured proof (byte-identical kicad-cli clearance whether "gnd" is
    # mapped to "GND" or left unassigned entirely). PR #1087 (fix/unassigned-
    # selv-nets) independently reached the same conclusion for kicad_pro's
    # OWN net_settings.netclass_assignments and picked "Power", grounded in
    # docs/specs/NET_CLASS_SPECIFICATION.md 3.2 ("GND (control ground)"
    # listed under Power); PR #1083 (fix/unassigned-hv-domain-nets) assigned
    # PWR_RTN to "HighVoltage" there, since it is the doubler midpoint,
    # HV-domain per elec/domain_manifest.yaml:95. Mirrored here so this
    # table names the same class kicad_pro actually declares for both nets.
    #
    # NOTE (not fixed by this change -- flagged, not silently absorbed):
    # "GND" was the only entry in this table declaring
    # `routing_strategy="plane_preferred"`; router_v6/_zone_pour_stitch.py's
    # `_zone_layers_for_net` reads this table directly (not the get_rules_for_net
    # fallback cascade) to decide zone-pour eligibility, and `Power` declares
    # no routing_strategy at all. Reassigning `gnd` here measurably drops it
    # out of F.Cu/B.Cu zone-pour eligibility and (via `_should_route`) into
    # A*-routed instead of zone-covered -- see the evidence doc's "Zone-pour
    # and routing-strategy side effect" section for the measurement. `gnd`'s
    # own dedicated In1.Cu ground-plane pour (router_v6/_ground_plane.py) is
    # unaffected -- it targets the literal net name "gnd", never consults
    # this table.
    "gnd": "Power",
    "PWR_RTN": "HighVoltage",
    # NOTE `CGND` names no net on this board (0 references in
    # pcb/temper.kicad_pcb, checked 2026-08-11). It is kept rather than
    # deleted because the GND-family reclassification -- CGND/PGND both
    # would-be aliases of PWR_RTN -- is an open, deliberately-reserved
    # decision (see scripts/check_hv_netclass_coverage.py's docstring, which
    # flags it as human-decision-required with an order-of-magnitude larger
    # blast radius). An assignment for a net that does not exist is inert, so
    # this is dead weight rather than a hazard; removing it is that decision's
    # job, not this line's. It still names the same nonexistent "GND" class
    # this fix retires from `gnd`/`PWR_RTN` -- the extended
    # check_netclass_class_param_correspondence.py gate (this task) reports
    # it as a known, pre-existing, deliberately out-of-scope violation of
    # the identical shape; not silently exempted, just not this line's fix.
    "CGND": "GND",
}

# -----------------------------------------------------------------------------
# Safety constant single source of truth (SSOT).
# Every consumer needing a safety clearance MUST reference TEMPER_NET_CLASSES
# (or SAFETY_CONSTANT_AUTHORITY derived from it) instead of repeating the float.
# Duplicating a bare float that appears here outside this module is blocked by
# the AST linter at packages/temper-drc/tests/test_safety_constant_lint.py.
# -----------------------------------------------------------------------------
SAFETY_CONSTANT_AUTHORITY_NET_CLASSES: frozenset[str] = frozenset({"ACMains", "HighVoltage"})
SAFETY_CONSTANT_AUTHORITY_FIELDS: frozenset[str] = frozenset({"clearance", "creepage_mm"})

SAFETY_CONSTANT_AUTHORITY: tuple[tuple[str, str, float], ...] = tuple(
    (nc_name, field_name, float(getattr(nc, field_name)))
    for nc_name, nc in TEMPER_NET_CLASSES.items()
    if nc_name in SAFETY_CONSTANT_AUTHORITY_NET_CLASSES
    for field_name in SAFETY_CONSTANT_AUTHORITY_FIELDS
)

def create_temper_design_rules() -> DesignRules:
    """Create design rules with Temper-specific net classes.

    Returns:
        DesignRules configured for Temper project requirements
    """
    return DesignRules(
        default_trace_width=0.2,
        default_clearance=0.15,  # Relaxed from 0.2mm to allow signal density (Targeted Reduction)
        default_via_diameter=0.6,
        default_via_drill=0.3,
        net_classes=deepcopy(TEMPER_NET_CLASSES),
        net_class_assignments=deepcopy(TEMPER_NET_ASSIGNMENTS),
    )

__all__ = [
    "Array",
    "DesignRules",
    "NetClassRules",
    "SAFETY_CONSTANT_AUTHORITY",
    "SAFETY_CONSTANT_AUTHORITY_FIELDS",
    "SAFETY_CONSTANT_AUTHORITY_NET_CLASSES",
    "TEMPER_NET_ASSIGNMENTS",
    "TEMPER_NET_CLASSES",
    "ViaTemplate",
    "create_temper_design_rules",
]
