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
    "ACMains": NetClassRules(
        name="ACMains",
        trace_width=2.5,
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
    "HighVoltage": NetClassRules(
        name="HighVoltage",
        trace_width=3.0,
        clearance=6.0,
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
    "Power": NetClassRules(
        name="Power",
        trace_width=0.5,
        clearance=0.25,
        via_diameter=0.8,
        via_drill=0.4,
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
    "GND": NetClassRules(
        name="GND",
        trace_width=1.0,
        clearance=0.3,
        via_diameter=1.0,
        via_drill=0.5,
        via_template="Via3x3",
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
    "+15V_LS": "HighVoltage",
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
    "a": "HighVoltage",
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
    "zcd": "HighVoltage",  # power_in's internal HV-side ZCD divider tap
    "tank-out": "HighVoltage",  # ResonantTank input == SW_NODE
    "tank.c_tank1-p2": "HighVoltage",  # ResonantTank 400V-rated node
    "power_in.ntc-no": "HighVoltage",  # bypass relay NO -> rectified mains
    "discharge.k_dis1-nc": "HighVoltage",  # k_dis1 contacts group (HV bus)
    "discharge.k_dis2-nc": "HighVoltage",  # k_dis2 contacts group (HV bus)
    "hb.power_loop.q_high-g": "HighVoltage",  # Q_high gate, 1 resistor from GATE_HS
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
    "PWR_RTN": "GND",
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
