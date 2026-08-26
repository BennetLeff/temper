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
    # UNSOURCED (flagged 2026-08-15, safety-assertion audit): clearance=6.0
    # and creepage_mm=6.0 below are NOT IEC 60335-1 Table 16 values (Table
    # 16 is keyed to rated impulse voltage; its value set is {0.5, 1.5, 3.0,
    # 5.5, 8.0, 11.0}) and the legacy "IEC 60335-1 Table 16 working isolation
    # at 400V" citation is debunked twice over: 400V is not a Table 16 row
    # and 6.0mm is not a Table 16 value (docs/evidence/2026-07-28-creepage-
    # determination-brainstorm.md). 6.0mm is also not a Table 17/18 creepage
    # cell at any row applicable to 120-240V mains. This table is the
    # placer-feasibility model; the fab-authoritative enforcement is
    # scripts/generate_kicad_dru.py's cited figures. Values NOT changed
    # (re-sourcing is a separate attributed decision); the debunked
    # citation was removed from netclass_rules.yaml's matching entry in
    # the same pass.
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
        # creepage_mm 6.0: UNSOURCED legacy figure (flagged 2026-08-15) --
        # not a recovered Table 17 value at row iv (>250-400V: 4.0mm PD2 /
        # 6.3mm PD3 basic, IIIa/IIIb; reinforced doubles 8.0/12.6mm). The
        # fab-authoritative figure is scripts/generate_kicad_dru.py's
        # HV_CREEPAGE_ENFORCED_MM (12.6mm, PD3-pinned, cited). See the
        # matching note in netclass_rules.yaml.
        creepage_mm=6.0,
        routing_strategy="plane_required",
        dru_priority=20,
        required_layer="B.Cu",
        safety_category="HV",
    ),
    # via_diameter RAISED 0.4 -> 0.8mm 2026-08-13
    # (docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md sec.6.1,
    # docs/hardware/FAB_CAPABILITY.md #2a): the old 0.4mm/0.2mm pad/drill pair
    # gave a 0.1mm annular ring, below JLCPCB's 2oz PTH annular-ring floor
    # (0.254mm) -- this is the smaller of the two via families measured on
    # the real board, and it fails even JLCPCB's 1oz ABSOLUTE MINIMUM
    # (0.15mm), not just the 2oz figure. New pad = drill (0.2mm, unchanged --
    # this is a manufacturability fix to pad geometry, not a drill/current-
    # capacity change) + 2 x 0.3mm target ring (0.3mm chosen for margin over
    # the 0.254mm floor, not the bare minimum 0.708mm pad -- ACMains/
    # HighVoltage/HighVoltageTank above already use a 1.2mm/0.6mm pad/drill
    # pair, a 0.3mm ring that already clears the floor; every other class in
    # this table is raised to the SAME 0.3mm ring target below, so via
    # geometry across the whole netclass table is now uniform on ring width,
    # varying only by drill diameter).
    "FinePitch": NetClassRules(
        name="FinePitch",
        # trace_width FIXED 2026-08-15 (full-route agent finding +
        # docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md):
        # 0.127mm was below the board's setup min_track_width (0.2mm,
        # pcb/temper.kicad_pro) AND JLCPCB's 2oz-multilayer floor (0.15mm),
        # producing track_width DRC errors on 6 routed nets. Raised to
        # 0.2mm to match both. Matches netclass_rules.yaml + kicad_pro.
        trace_width=0.2,
        clearance=0.1,
        via_diameter=0.8,
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
    # via_diameter RAISED 1.0 -> 1.1mm 2026-08-13 (same JLCPCB-2oz-annular-
    # ring-floor fix as FinePitch above): 1.0mm/0.5mm gave a 0.25mm ring,
    # 0.004mm short of the 0.254mm floor. New pad = 0.5mm drill (unchanged)
    # + 2 x 0.3mm ring target, matching the board-wide 0.3mm-ring convention.
    "Power": NetClassRules(
        name="Power",
        trace_width=1.0,
        clearance=0.5,
        via_diameter=1.1,
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
    # via_diameter RAISED 0.8 -> 1.0mm 2026-08-13 (same JLCPCB-2oz-annular-
    # ring-floor fix, board-wide 0.3mm-ring convention -- see FinePitch
    # above): 0.8mm/0.4mm gave a 0.2mm ring, below the 0.254mm floor. This is
    # also the exact family (0.8mm/0.4mm) measured on all 40 of the board's
    # larger-family real vias
    # (docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md sec.6.1).
    "GateDriveHV": NetClassRules(
        name="GateDriveHV",
        trace_width=0.4,
        clearance=0.25,
        via_diameter=1.0,
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
        via_diameter=1.0,
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
    # via_diameter RAISED 1.0 -> 1.1mm 2026-08-13 (same fix as Power above:
    # 1.0mm/0.5mm gave a 0.25mm ring, 0.004mm short of the 0.254mm floor).
    "GND": NetClassRules(
        name="GND",
        trace_width=1.0,
        clearance=0.3,
        via_diameter=1.1,
        via_drill=0.5,
        via_template="Via3x3",
        routing_strategy="plane_preferred",
        dru_priority=60,
        required_layer=None,
        safety_category="LV",
    ),
    # via_diameter RAISED 0.6 -> 0.9mm 2026-08-13 (board-wide 0.3mm-ring fix,
    # see FinePitch above): 0.6mm/0.3mm gave a 0.15mm ring, below the
    # 0.254mm floor.
    "HighSpeed": NetClassRules(
        name="HighSpeed",
        trace_width=0.15,
        clearance=0.2,
        via_diameter=0.9,
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
        via_diameter=0.9,
        via_drill=0.3,
        via_template="Via1x1",
        dru_priority=80,
        required_layer=None,
        safety_category="LV",
    ),
    # via_diameter RAISED 0.8 -> 1.0mm 2026-08-13 (same fix as GateDriveHV/
    # GateDriveSELV above; this is the other class sharing the 0.8mm/0.4mm
    # family measured on the board's 40 larger-family real vias).
    "HighCurrent": NetClassRules(
        name="HighCurrent",
        trace_width=0.5,
        clearance=0.25,
        via_diameter=1.0,
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
        via_diameter=1.0,
        via_drill=0.4,
        via_template="Via1x1",
        voltage_v=400.0,
        # creepage_mm 6.0 inherited from HighVoltage: UNSOURCED legacy
        # figure (flagged 2026-08-15) -- see HighVoltage's note above.
        creepage_mm=6.0,
        dru_priority=22,
        required_layer=None,
        safety_category="HV",
    ),
    # UNSOURCED (flagged 2026-08-15): HighVoltageIsolated's clearance=6.0
    # and creepage_mm=6.0 are legacy figures -- 6.0mm is in NO recovered
    # table (Table 16 value set {0.5, 1.5, 3.0, 5.5, 8.0, 11.0}; Table 17
    # row iv gives 4.0/8.0mm PD2 and 6.3/12.6mm PD3 for this class's
    # voltage band), and the original "Table 16 working isolation at 400V"
    # citation is debunked. Fab-authoritative enforcement is
    # scripts/generate_kicad_dru.py's cited figures. Values unchanged --
    # re-sourcing is a separate attributed decision.

    # via_diameter RAISED 1.0 -> 1.1mm 2026-08-13 (same fix as Power/GND
    # above: 1.0mm/0.5mm gave a 0.25mm ring, 0.004mm short of the 0.254mm
    # floor).
    "HighVoltageIsolated": NetClassRules(
        name="HighVoltageIsolated",
        trace_width=2.0,
        clearance=6.0,
        via_diameter=1.1,
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
    # ADDED 2026-08-17 (hb-gnd TEMPER_NET_ASSIGNMENTS blast-radius
    # investigation; see docs/evidence/2026-08-17-hb-gnd-design-rules-
    # classification-blast-radius.md). `hb-gnd` is declared HV under
    # elec/domain_manifest.yaml (PR #1145, netlist-traced: the half-bridge
    # low-side switch's return conductor -- power_loop.q_low.E in
    # elec/src/modules.ato:379 -- one CT-primary-winding, a few milliohms,
    # not a galvanic isolator, from the already-declared HV net
    # `DC_BUS_RTN`, ~-170V relative to power_return/PWR_RTN -- which
    # elec/src/main.ato's own comment calls "signal ground" -- confirmed
    # independently from the .ato topology, not merely trusted from the
    # manifest's own trace), and `router_v6.clearance_check.
    # _classify_net_class` already returns "HV" for it on both the Python
    # and Rust backends (PR #1300). This table had NO entry for it at
    # all -- confirmed live, `scripts/check_hv_netclass_coverage.py`
    # PROPERTY 1/3 both flagged `hb-gnd` as a currently-red, CI-blocking
    # violation: unclassified here AND absent from pcb/temper.kicad_pro's
    # real netclass_assignments (falls to KiCad's "Default" 0.2mm class on
    # the actual kicad-cli DRC path -- weaker than even a generic LV
    # class). This entry fixes PROPERTY 1 only; PROPERTY 3 (the kicad_pro
    # sync) is deliberately left red -- see the evidence doc.
    #
    # Measured DRC impact of JUST this table entry, isolated (before vs.
    # after, real committed board, kicad-cli 10.0.5, --severity-all
    # --all-track-errors, both with and without --refill-zones -- see the
    # evidence doc for the full methodology): a scratch pcb/temper.
    # kicad_pro copy with ONLY "hb-gnd": "HighVoltage" synced in (isolated
    # from every other pre-existing sync-script gap) clears 8 FALSE
    # clearance+creepage violations against hb-gnd's own HV domain-mates
    # (DC_BUS_RTN, PWR_RTN, +170V_BUS, SW_NODE, w1_1, the gate-driver
    # isolated rails -- hb-gnd was being misread as the LV side of a
    # same-domain pair) but surfaces 28 NEW, genuine violations against 18
    # distinct LV/SELV nets physically close to hb-gnd's routed copper
    # (WDT_KICK x8, +3V3, I_SENSE, RTD_SDI/RTD_HW_FAULT, i2c_sda_ui,
    # thermal.j_fan-p1, discharge.r_dis2a-p2, safety.ovp.r_adc_top1-p2,
    # etc. -- actual distances as tight as 0.65-0.88mm against a 2.0mm/
    # 12.6mm PD3 requirement). Net: +25 total DRC violations (1086->1111
    # no-refill, 1024->1050 refill), 100% in the clearance/creepage
    # categories, ALL previously-invisible real exposure, not new
    # false-positives. Direction is strictly stricter and the classifier
    # source-of-truth correction is genuinely safety-improving; syncing it
    # into pcb/temper.kicad_pro for real (so kicad-cli's DRC actually
    # enforces it) is a SEPARATE, NOT-taken step here -- it requires
    # routing/placement remediation (moving copper) this task's hard rules
    # forbid an agent from doing unilaterally, so it is reported, not
    # applied. Not the PWR_RTN/CGND reservation (handoff §9 item 6): this
    # is a small net (6 pads) gaining a missing explicit assignment, not a
    # reclassification of an existing large-copper/zone-poured net, and
    # scripts/sync_kicad_netclass_assignments.py's own PROTECTED_NETS
    # (PWR_RTN, CGND) is untouched by this change.
    #
    # KNOWN CONSEQUENCE, LEFT RED, NOT FIXED (forbidden to re-pin a pinned
    # oracle per this task's hard rules): this entry makes
    # tests/core/_design_rules_py_oracle.py's frozen TEMPER_NET_ASSIGNMENTS
    # snapshot (content-hash pinned in scripts/oracle_hashes.json) diverge
    # from this live table, so test_design_rules_rust_differential.py::
    # test_module_constants_identical / test_create_temper_design_rules_
    # identical now fail. The oracle FILE itself is untouched (`scripts/
    # check_oracle_hashes.py` still reports 167/167 byte-identical to its
    # pin) -- only the differential-parity comparison is red. Reconciling
    # requires the standing oracle re-pin ceremony (exhaustive-divergence
    # evidence, a deliberate committed act) as separate follow-up work.
    "hb-gnd": "HighVoltage",
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
    # ADDED 2026-08-18. `input` is GateDriveLS's module-local signal
    # (elec/src/modules.ato:214, :234) wired to UCC21550 pin 10 = OUTB at
    # modules.ato:423 -- the driver's SECONDARY-side output. components.ato:71-74
    # places pins 9 (VSSB), 10 (OUTB), 11 (VDDB) under the part's own
    # "# Secondary side" comment, and the board's pad->net map confirms it
    # independently: U6 pad 9 = hb-gnd, pad 10 = input, pad 11 = +15V_LS. It is
    # physically sandwiched between two already-declared HV nets on adjacent
    # pins of one package.
    #
    # Its reference is VSSB = hb-gnd = dc_bus.hv_minus: 0-15V relative to
    # hb-gnd (the gate swing, bounded by VDDB, asserted <= 25V at
    # modules.ato:438), but ~-170V to -155V relative to PWR_RTN. Not SELV.
    #
    # It is AFFIRMATIVELY declared HV at elec/domain_manifest.yaml:251 (PR
    # #1134, 96db2ccde, 2026-08-15) -- not an absence case. But it had no entry
    # here AND none in pcb/temper.kicad_pro, so it resolved to Default
    # (0.15/0.2mm) on both enforced surfaces while
    # router_v6.clearance_check._classify_net_class already returned "HV" for
    # it. scripts/check_hv_netclass_coverage.py was already failing closed on
    # this under PROPERTY 1 and BLOCKING PROPERTY 3.
    #
    # HighVoltageSignal, not HighVoltage or GateDriveHV. Matches +15V_LS above
    # -- its own supply rail on the adjacent pin, same domain, same
    # safety_category, same 2.0/6.0 -- and hb.power_loop.q_high-g, the high
    # side's structural mirror, already HighVoltageSignal on both surfaces.
    # trace_width 0.5mm suits the mA gate-drive tier; HighVoltage's 5.0mm
    # targets the 15-22.5A bus/tank tier.
    #
    # GateDriveHV was measured and REJECTED: it clears all 10 of this net's
    # current violations and surfaces NOTHING, because GateDriveHV is excluded
    # from the B-side of every reinforced rule in the .kicad_dru and declares
    # no creepage as an A-side -- `input` would owe zero creepage to any net on
    # the board, including +3V3, gnd, SHUTDOWN and the fan connector. On a
    # -170V-referenced conductor that is making a check pass by weakening it.
    #
    # Measured delta (each variant run 3x and intersected; kicad-cli is
    # nondeterministic run-to-run): 10 same-domain false positives clear --
    # two of them at the package-fixed 0.670mm SOIC-16W pad gap, unsatisfiable
    # at any placement -- and 9 GENUINE reinforced-barrier exposures against
    # LV/SELV surface at 8.1-12.5mm. Those 9 are not novel: pads 9/11/14/16
    # already produce the byte-identical shape against the same primary-side
    # pins today. `input` was the only secondary-side U6 pin not producing
    # them, because it was the only one classed Default.
    #
    # See docs/evidence/2026-08-18-input-netclass-misclassification.md.
    "input": "HighVoltageSignal",
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
    # ADDED 2026-08-18: the remaining six `discharge.*` nets, each
    # AFFIRMATIVELY DECLARED HV in elec/domain_manifest.yaml
    # (lines 285/306/313/335/345/359)
    # yet absent from BOTH enforced surfaces -- this table AND
    # pcb/temper.kicad_pro's netclass_assignments -- so every one resolved to
    # `Default` (0.2mm clearance, ZERO creepage) for both the Python placer
    # and kicad-cli. Same defect shape as `input` (PR #1360) and `hb-gnd`
    # (PR #1145). Topology re-traced from elec/src/modules.ato directly, NOT
    # from the manifest's own summary, and cross-checked against the board's
    # pad->net map; all six are HV-domain throughout, with BOTH ends of every
    # string already-declared HV nets:
    #
    #   r_dis1a-p2 (R6.2+R7.1): mid-node of half-bus-1's bleed string
    #     `hv_plus -> r_dis1a -> r_dis1b -> k_dis1.NC -> mid`
    #     (modules.ato:1378-1381). hv_plus = +170V_BUS, mid = PWR_RTN --
    #     both already-declared HV. Sits ~+85V wrt PWR_RTN.
    #   r_dis2a-p2 (R8.2+R9.1): mid-node of half-bus-2's string
    #     `mid -> r_dis2a -> r_dis2b -> k_dis2.NC -> hv_minus`
    #     (modules.ato:1384-1387). mid = PWR_RTN, hv_minus = DC_BUS_RTN --
    #     both already-declared HV. Sits ~-85V wrt PWR_RTN.
    #   r_snub1-p2 (C7.1+R14.2) / r_snub2-p2 (C8.1+R15.2): the RC-snubber
    #     mid-nodes bridging each relay's own NC-COM contact gap
    #     (modules.ato:1392-1397). DC-blocked by c_snub*, so these carry only
    #     transient AC current across a gap whose BOTH ends are HV
    #     (k_dis*.NC already HV-declared; k_dis*.COM = PWR_RTN / DC_BUS_RTN).
    #   k_dis1-no (K2.3) / k_dis2-no (K3.3): the relays' NO contacts. The
    #     manifest's "same physical contact bank as COM/NC" argument holds,
    #     but UNDERSTATES the case: modules.ato:1388-1389 records that the
    #     coils are held energized in normal operation, which holds each pole
    #     ON its NO contact -- so NO is GALVANICALLY BONDED to COM (= PWR_RTN
    #     for K2, DC_BUS_RTN for K3) for the entire time the unit is running.
    #     These are live HV pads whenever the product is powered, not merely
    #     mechanically-adjacent unconnected ones.
    #
    # Class choice is HighVoltageSignal, not HighVoltage, for the same
    # ~20mA current-tier reason the 2026-08-13 re-scope above gives for their
    # own directly-connected siblings k_dis1-nc/k_dis2-nc: same voltage
    # domain, same safety_category ("HV"), same 6.0mm creepage parameter and
    # the same real 2.0mm/12.6mm reinforced enforcement via the ".. to LV"
    # rule -- it is the current/width requirement alone that differs.
    # HighVoltage's 5.0mm width would be a bus/tank figure on a mA-scale net.
    #
    # VERIFIED this class actually ENFORCES something before proposing it
    # (the GateDriveHV trap that PR #1360 measured and rejected: that class
    # is excluded from the B-side of every reinforced rule AND declares no
    # creepage as an A-side, so a net assigned it owes zero creepage to
    # anything). HighVoltageSignal is the A-side of a real generated rule --
    # "HighVoltageSignal to LV", RULE 4d -- carrying clearance 2.0mm and
    # creepage 12.6mm against every LV/SELV/Default net.
    #
    # MEASURED (3 kicad-cli runs per variant, sets intersected, scratch copy
    # with an fp-lib-table sibling; kicad-cli is nondeterministic run-to-run):
    # 379 -> 395 errors. 18 creepage violations CLEAR, and every single one is
    # a same-domain HV<->HV pair that was only ever a false positive of these
    # nets reading as `Default`/LV (K2.3<->K2.4 and K3.3<->K3.4 -- adjacent
    # pads of ONE relay contact block; R14.1<->R14.2 and R15.1<->R15.2 -- the
    # two pads of ONE 2512 resistor, unsatisfiable at any placement; plus
    # pairs against PWR_RTN, DC_BUS_RTN, SW_NODE, hb-gnd, ac_n, tank-out and
    # the isolated gate-driver rails). 17 NEW creepage violations surface
    # against genuinely LV/SELV nets (+3V3, gnd, safety-line/-1/-2,
    # RTD_SDI/RTD_SDO, V_BUS_SENSE, OCP2_VREF_2V5, rtd_force_n,
    # rtd_pan.r_high_top-inp, safety.coil_thermal-line/.comp-inp) -- real,
    # previously-invisible reinforced-barrier exposure, the same shape the
    # `input` and `hb-gnd` fixes surfaced. Direction is strictly stricter.
    #
    # ALSO SURFACED, GENUINE, NOT FIXED HERE: 15 track_width violations, all
    # on `discharge.r_snub1-p2` -- the ONLY one of these six with any routed
    # copper, carried at 0.2mm on In3.Cu against HighVoltageSignal's 0.5mm
    # manufacturability floor. That is a real undersized-trace finding on a
    # net that swings to the full half-bus, not an artifact of this change;
    # remediating it means moving copper in pcb/temper.kicad_pcb, which this
    # task is forbidden to touch. Reported, not applied. Choosing a weaker
    # class to make it disappear would be the reclassification-to-escape
    # failure mode this table's own comments warn against.
    "discharge.k_dis1-no": "HighVoltageSignal",  # K2.3 NO contact; bonded to COM (PWR_RTN) when energized
    "discharge.k_dis2-no": "HighVoltageSignal",  # K3.3 NO contact; bonded to COM (DC_BUS_RTN) when energized
    "discharge.r_dis1a-p2": "HighVoltageSignal",  # half-bus-1 bleed mid-node, ~+85V wrt PWR_RTN
    "discharge.r_dis2a-p2": "HighVoltageSignal",  # half-bus-2 bleed mid-node, ~-85V wrt PWR_RTN
    "discharge.r_snub1-p2": "HighVoltageSignal",  # K2 NC-COM snubber mid-node
    "discharge.r_snub2-p2": "HighVoltageSignal",  # K3 NC-COM snubber mid-node
    # RE-SCOPED 2026-08-13, same evidence doc: Q_high's gate current is
    # mA-scale gate-drive current, not bus/tank current -- moved to
    # "HighVoltageSignal".
    "hb.power_loop.q_high-g": "HighVoltageSignal",  # Q_high gate, 1 resistor from GATE_HS
    # ADDED 2026-08-19 (netclass two-table reconciliation). These 7 nets
    # are declared under elec/domain_manifest.yaml's domains.HV.nets and
    # landed there on 2026-08-15 via PR #1164 (commits a458f8e2a /
    # 3c7f7484d, "classify every Default-netclass net's true domain;
    # declare 7 newly-found HV nets"). That PR's own commit message names
    # this table and pcb/temper.kicad_pro as a deliberate, NOT-taken
    # follow-up ("TEMPER_NET_ASSIGNMENTS / kicad_pro are left as a named
    # follow-up, same as PR #1145 left them for hb-gnd/s1"). Nothing has
    # taken it since, so all 7 have been HV-declared but netclass-
    # unassigned in BOTH tables -- scripts/check_hv_netclass_coverage.py
    # PROPERTY 1 (this table) and PROPERTY 3 (kicad_pro) have both been
    # red on origin/main for those 7 names, and on the fab-authoritative
    # path (kicad-cli DRC, via kicad_pro's netclass_assignments) every one
    # of them resolves to KiCad's "Default" class: 0.2mm clearance and NO
    # creepage constraint of any kind. `input` and the six discharge nets
    # have been physically present on pcb/temper.kicad_pcb since
    # 2026-07-15 (a1e93e8b5) and 2026-07-16 (b5674c3e0 / f6ec8abbb)
    # respectively.
    #
    # Domain re-verified independently for this change from the evidence
    # hierarchy (manifest -> elec/src/*.ato -> connected pins), NOT from
    # net spelling -- every verdict below agrees with PR #1164's:
    #
    # - `input`: UCC21550 (U6) pin 10 = OUTB, inside components.ato's own
    #   "# Secondary side" pin group, plus R22.1 (hb.gate_ls.rg_on.p1).
    #   Wired at HalfBridge level by `gate_hs.driver.OUTB ~ gate_ls.input`
    #   (modules.ato:423); `rg_on.p2 ~ drive.out` makes it ONE 2.2ohm gate
    #   resistor upstream of the already-declared HV net GATE_LS. Floats
    #   on DC_BUS_RTN via driver.VSSB (pin 9, modules.ato:424) -- roughly
    #   -170V with respect to signal ground. It is the low-side structural
    #   analogue of `hb.power_loop.q_high-g` directly above.
    #
    #   CLASS CHOICE, and why it is NOT "GateDriveHV" even though `input`
    #   is literally a gate-driver output: this table's two existing
    #   precedents for a node one gate-resistor away from a driver output
    #   DISAGREE -- GATE_HS/GATE_LS are "GateDriveHV", while
    #   `hb.power_loop.q_high-g` (GATE_HS's own post-resistor sibling) is
    #   "HighVoltageSignal". Under an unresolved precedent conflict the
    #   more restrictive class is required, and here the gap is not
    #   marginal: measured against the generated pcb/temper.kicad_dru,
    #   the GateDriveHV class has NO rule granting it any clearance or
    #   creepage against any LV/SELV class -- its only A-side rules are
    #   "GateDriveHV near HV" (0.5mm), "GateDriveHV to ACMains" (0.5mm)
    #   and "GateDriveHV to HighVoltageIsolated" (0.5mm), and it is
    #   explicitly excluded from the B-side of every "... to LV" rule.
    #   HighVoltageSignal, by contrast, carries "HighVoltageSignal to LV"
    #   (2.0mm clearance + 12.6mm reinforced creepage). Same voltage
    #   domain, same safety_category, but only one of the two actually
    #   enforces the barrier -- see this change's report for the separate
    #   GateDriveHV finding, which is NOT fixed here.
    "input": "HighVoltageSignal",
    # - `discharge.k_dis1-no` / `discharge.k_dis2-no`: pin 3 (NO) of each
    #   discharge relay, the SAME physical contact block as pin 1 (COM,
    #   `k_dis1.COM ~ mid` = power_return = already-declared HV PWR_RTN)
    #   and pin 4 (NC, already declared HV and already classed
    #   HighVoltageSignal directly above). modules.ato leaves the NO
    #   contacts deliberately unconnected ("NO contacts intentionally
    #   unconnected: energized = pole held on NO = discharge path open"),
    #   so these pads carry zero current -- HighVoltageSignal's 0.5mm
    #   width is ample and its clearance/creepage (2.0/6.0) are identical
    #   to HighVoltage's. Matched to their own -nc siblings.
    "discharge.k_dis1-no": "HighVoltageSignal",
    "discharge.k_dis2-no": "HighVoltageSignal",
    # - `discharge.r_dis1a-p2` / `discharge.r_dis2a-p2`: interior mid-node
    #   of each half-bus bleed string (`hv_plus -> r_dis1a(3.9k) ->
    #   r_dis1b(3.9k) -> k_dis1.NC -> mid`, modules.ato:1378-1385). BOTH
    #   ends are already-declared HV nets (+170V_BUS and PWR_RTN), so
    #   every interior node is unambiguously HV -- unlike the OVP-01
    #   protective-impedance dividers below, this string never reaches
    #   SELV at any point. Current is ~20mA (170V/7.8k), three orders of
    #   magnitude below the bus/tank tier HighVoltage's 5.0mm width
    #   targets -- the identical derivation already cited for
    #   discharge.k_dis1-nc/k_dis2-nc above.
    "discharge.r_dis1a-p2": "HighVoltageSignal",
    "discharge.r_dis2a-p2": "HighVoltageSignal",
    # - `discharge.r_snub1-p2` / `discharge.r_snub2-p2`: interior node of
    #   the RC snubber bridging each relay's own NC-COM contact gap
    #   (`k_dis1.NC ~ r_snub1.p1`, `r_snub1.p2 ~ c_snub1.p1`, `c_snub1.p2
    #   ~ k_dis1.COM`, modules.ato:1392-1394). Both ends of that string
    #   are HV (k_dis1.NC via discharge.k_dis1-nc; k_dis1.COM = mid =
    #   PWR_RTN), so the interior node is HV throughout -- a DC-blocked
    #   AC-only path across the SAME HV contact gap, not a crossing into
    #   another domain. Continuous current is zero (series capacitor);
    #   the only current is the 1.7A-peak / 47us closure transient
    #   modules.ato:1164 sizes the snubber for, far inside a 0.5mm
    #   conductor's transient capability and nowhere near the continuous
    #   bus/tank tier. HighVoltageSignal.
    "discharge.r_snub1-p2": "HighVoltageSignal",
    "discharge.r_snub2-p2": "HighVoltageSignal",
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
    # ADDED 2026-08-13 (docs/evidence/2026-08-13-ovp01-midchain-single-fault-
    # creepage.md). OVP-01 protective-impedance-divider MID-CHAIN interior
    # nodes -- PR #1164 traced their normal voltage (~58-114V, re-derived
    # independently, matching exactly) and left them "deliberately
    # unclassified" (elec/domain_manifest.yaml, matching the 2026-07-27
    # precedent at commit 70503e6dc), which resolves to Default:
    # creepage_mm=0.0, zero enforcement. Two findings this evidence doc adds:
    # (1) under Clause 8.1.4's OWN required single-fault condition (the
    # top-side resistor nearest the bus shorts -- the same fault class the
    # manifest's own touch-current arithmetic already evaluates, just never
    # carried through to the interior node's own voltage), r_div_top1-p2 /
    # r_adc_top1-p2 reach the FULL +170V_BUS potential (170.0V exactly) and
    # r_div_top2-p2 / r_adc_top2-p2 reach 86.6-87.4V -- both above the SELV
    # ceiling even though the "-top2-p2" pair's NORMAL voltage (58.1-58.9V)
    # sits just under it. (2) declaring any of the four in
    # elec/domain_manifest.yaml's domains: HV/SELV dict was tried and
    # empirically breaks scripts/check_domain_partition.py: its chain model
    # (synthesize_chain_head_isolators) treats only the FIRST chain member as
    # a graph isolator, by deliberate design (declaring every member "caused
    # false isolator-barrier violations in practice") -- so every node
    # downstream, these four included, sits in the SAME connected component
    # as the already-declared-SELV far end (comp.INP / V_BUS_SENSE), and
    # domain-labeling them HV there asserts two domains for one connected
    # component, which check_domain_disjointness correctly rejects. This
    # table is the decoupled alternative: an entry here is read by
    # check_hv_netclass_coverage.py's PROPERTIES 1/3/4 only in the
    # domain_manifest.yaml -> here direction, never the reverse, so it adds
    # real netclass coverage without asserting a topology claim the gate
    # would (correctly) reject. Mapped to the EXISTING "HighVoltage" class,
    # not a new value -- see the evidence doc Sec 4 for why 6.0mm is a safe
    # over-provision here rather than the precisely-derived figure (IEC
    # 60335-1 Table 17/18 would put these specific voltage bands at
    # 1.4-4.0mm depending on table/row; a purpose-built netclass at the
    # correct row is named there as a follow-up, mirroring this project's
    # own HighVoltageTank precedent, not invented here). pcb/temper.kicad_pro's
    # netclass_assignments -- what the real kicad-cli DRC reads -- is a
    # separate, still-open follow-up (matches PR #1145/#1164's own precedent
    # of leaving that wiring for later); this entry alone does not yet change
    # the physical board's DRC creepage enforcement.
    # REMOVED 2026-08-25. The four OVP-01 mid-chain divider nodes were
    # mapped to "HighVoltage" above as a deliberate interim over-provision,
    # and that comment closed by saying pcb/temper.kicad_pro's
    # netclass_assignments -- "what the real kicad-cli DRC reads" -- was "a
    # separate, still-open follow-up" and that "this entry alone does not yet
    # change the physical board's DRC creepage enforcement".
    #
    # #1391 wired kicad_pro. That turned the interim entry into live DRC
    # enforcement, and the figure it enforces is NOT the 6.0mm the
    # over-provision was reasoned about: "HighVoltage" participates in the
    # `HV to LV` rule, so kicad-cli applies REINFORCED creepage 12.6mm --
    # the mains<->SELV barrier -- to nodes the evidence doc measures at
    # 58.1-87.4V and 114.4V.
    #
    # docs/evidence/2026-08-13-ovp01-midchain-single-fault-creepage.md Sec 4
    # gives the correct bands from IEC 60335-1 Table 18 (functional
    # insulation, material group IIIa/IIIb): >50 and <=125V is 1.4mm PD2 /
    # 2.2mm PD3, with Table 17 basic insulation at 1.5/2.4 and 2.5/4.0mm as
    # the open alternative. So the enforced 12.6mm is 3-9x the applicable
    # figure by that document's own derivation.
    #
    # MEASURED cost of the over-constraint, 5 samples, spread 0:
    #   with these four assigned    errors 473  clearance 227  creepage 149
    #   with them removed           errors 413  clearance 209  creepage 107
    # 60 errors, and creepage returns exactly to its pre-#1391 value of 107 --
    # i.e. every one of #1391's creepage findings came from these four nets.
    #
    # domain_manifest.yaml declines these nets deliberately and says so:
    # "genuinely mid-chain, neither HV nor SELV by voltage ... not silently
    # dropped: flagged". Removing them here restores agreement between all
    # three tables rather than leaving two of them asserting a barrier the
    # third rejects.
    #
    # The real fix is the purpose-built netclass at the correct Table 17/18
    # row that the evidence doc names in its Sec 6 follow-ups. That needs the
    # table-choice question answered and is not invented here.
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
    # ADDED 2026-08-19 (netclass two-table reconciliation). The two
    # remaining elec/domain_manifest.yaml SELV-domain nets with no
    # assignment in pcb/temper.kicad_pro (scripts/
    # check_hv_netclass_coverage.py PROPERTY 4, red on origin/main).
    # Declared here first so kicad_pro can be DERIVED from this table by
    # scripts/sync_kicad_netclass_assignments.py rather than hand-copied.
    #
    # Both were traced to SELV in the manifest itself, from the compiled
    # netlist, and re-verified for this change:
    #
    # - `s1`: OCP-02's CT (T2 / safety.ocp2.ct) SECONDARY node. Netlist
    #   net code 117 = T2.3 (ct.S1), U19.3 (TLV3201 INP), C37.1
    #   (c_filter), R65.1 (r_burden). modules.ato SecondaryOCPComparator
    #   wires `ct.S2 ~ power.gnd` and `r_burden.p2 ~ power.gnd`, and
    #   main.ato:859 chains `safety.power_3v3.gnd ~ gnd` -- the secondary
    #   has NO galvanic connection to the primary (which sits on
    #   hb-gnd/DC_BUS_RTN), so it is referenced to signal ground
    #   regardless of the primary's common-mode voltage. This is the
    #   exact isolation construction of `I_SENSE` (T1's secondary), and
    #   `I_SENSE` is classed FinePitch -- matched to its twin.
    "s1": "FinePitch",
    # - `safety.ocp2-line`: OCP-02's fault line on TP3 (U25.2 comparator
    #   output, U19.1 fault-OR input, TP3.1). Entirely SELV: the TLV3201
    #   is powered from power_3v3 and no HV node is read, driven or
    #   referenced on this net; the sensing happens through CT2's
    #   isolated secondary (above). Matched to `RTD_HW_FAULT` directly
    #   above -- the board's other SELV comparator/fault status line.
    #
    # NOTE on class choice for these two: it is deliberately NOT a
    # safety-bearing decision, and this is provable rather than assumed.
    # Every "... to LV" rule in the generated pcb/temper.kicad_dru
    # conditions its B side on `B.NetClass != <each HV-family class>`, so
    # a net gets the full 2.0mm/12.6mm reinforced barrier against every
    # HV net if and only if its class is not one of the HV-family
    # classes. FinePitch, Power, GND and KiCad's own Default are
    # therefore INDISTINGUISHABLE to every HV<->SELV rule; they differ
    # only in their own baseline netclass clearance and trace width,
    # which for these two low-current sense/logic nets is a functional
    # and routability matter, not a shock-hazard one. The maximally
    # restrictive alternative would be "Power" (0.5mm baseline vs
    # FinePitch's 0.1mm); it is not taken because the evidence here is
    # not absent or ambiguous -- each net has a directly-traced twin
    # already carrying FinePitch -- and because Power's 1.0mm track width
    # is wrong for a CT burden node and a comparator output.
    "safety.ocp2-line": "FinePitch",
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
    # ADDED 2026-08-13 (URGENT hyphen-boundary net-classification defect;
    # see docs/evidence/2026-08-13-hyphen-boundary-netclass-defect.md).
    # These 5 nets are real, compiled nets on the production board
    # (elec/build/default.net) and are explicitly declared SELV in
    # elec/domain_manifest.yaml ("discharge.k_dis1's own declared 'coil'
    # group"/"power_in.bypass_relay's own declared 'coil' group" --
    # pin_labels there already call both pins of each pair "SELV coil
    # drive"). Today they fall through DesignRules.get_rules_for_net's
    # entire pattern cascade to Default (they contain no GND/Power/gate
    # keyword). The fix in this same change makes the HighCurrent tier's
    # "-" boundary widening apply to "COIL" too (consistent with the rest
    # of the cascade) -- which, left alone, would newly match these five
    # names ("...-coil1"/"...-coil2") and reclassify them HighCurrent
    # (safety_category "HV"), the exact false-positive shape
    # creepage_check.py's 2026-07-27 fix already fought to remove for the
    # same five nets under a different mechanism (see
    # router_v6/creepage_check.py's `_is_high_voltage_net` docstring).
    # Declared explicitly here (Tier 2, wins over the Tier 4+ pattern
    # cascade) rather than narrowing the boundary fix back down for just
    # "COIL" -- narrowing would silently reintroduce the hyphen-boundary
    # defect for the next hyphenated COIL-adjacent net.
    #
    # CHANGED 2026-08-16 (full-route agent, fix/route-to-100-percent):
    # "Signal" -> "Power". The original Signal declaration (2026-08-13,
    # #1134) was a stability fix whose PRIMARY purpose -- blocking the
    # hyphen-boundary-widened "COIL" keyword from reclassifying these
    # five nets HighCurrent (safety_category "HV") -- survives unchanged
    # under an explicit Power entry (an explicit Tier-2 declaration still
    # wins over the Tier 4+ cascade, and Power != HighCurrent). But the
    # Signal VALUE drifted from every other home of this fact: pcb/
    # temper.kicad_pro's net_settings.netclass_assignments (the file
    # kicad-cli's DRC actually reads) has assigned all five nets "Power"
    # since PR #1087 (2026-08-12, "12V/75mA relay coil-drive nets, per
    # elec/src/modules.ato; explicitly classed 'Power' already in
    # configs/temper_production_config.yaml"), and configs/
    # temper_production_config.yaml itself says "Power nets pull the
    # 15V/3V3 conversion + relay coil drivers into Power". The mismatch
    # measured as 531 real kicad-cli track_width DRC violations on the
    # 2026-08-16 capstone route: every coil-net track emitted at the
    # Signal width (0.2mm) while the DRC's "Power trace width" rule
    # requires 1.0mm. Aligning the router's emitted width with the
    # DRC-enforced class (Power 1.0mm -- strictly WIDER copper, the
    # conservative direction, matching the router's own C-space halos
    # which already read Power 0.5mm clearance from kicad_pro) is the
    # same shape as the #1255 FinePitch fix: make the emitted width
    # satisfy the enforced rule. Safety_category stays "LV" (Power's own
    # category); no clearance/creepage threshold changes anywhere.
    "discharge.k_dis1-coil1": "Power",
    "discharge.k_dis1-coil2": "Power",
    "discharge.k_dis2-coil1": "Power",
    "power_in.bypass_relay-coil1": "Power",
    "power_in.bypass_relay-coil2": "Power",
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
        # default_via_diameter RAISED 0.6 -> 0.9mm 2026-08-13 (same JLCPCB
        # 2oz-annular-ring-floor fix, board-wide 0.3mm-ring convention, as
        # every TEMPER_NET_CLASSES entry above -- see FinePitch's comment):
        # 0.6mm/0.3mm gave a 0.15mm ring, below the 0.254mm floor. This is
        # the fallback used for any net that resolves to no declared class.
        default_via_diameter=0.9,
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
