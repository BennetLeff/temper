"""
Design rules for PCB routing.

This module provides net class and design rule specifications for
controlling trace widths, clearances, and via sizes during routing.
"""

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TypeAlias

import numpy as np

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from temper_placer.core.bus_cohort import BusCohortConstraint
from temper_placer.core.differential_pair import DifferentialPairConstraint
from temper_placer.core.net_graph import NetGraph
from temper_placer.core.netclass_rules_gen import NetClassRules


def _hv_word_boundary_match(upper: str, patterns: tuple[str, ...]) -> bool:
    """Word-boundary keyword match, delimited by ``_`` or start/end of
    the (uppercased) name.

    A pattern ending in a non-alphanumeric character (e.g. ``"DC_BUS+"``)
    has no trailing boundary to anchor on and is matched with a leading
    anchor only. Mirrors the identical helper in
    ``router_v6.net_classification._matches_any`` and
    ``router_v6.clearance_check._is_hv_keyword_match`` -- see those
    modules' docstrings for the shared bug history (plain substring
    matching of short net-classification keywords).
    """
    for p in patterns:
        escaped = re.escape(p)
        if p and not p[-1].isalnum():
            if re.search(rf"(?:^|_){escaped}", upper):
                return True
        elif re.search(rf"(?:^|_){escaped}(?:$|[\d_])", upper):
            return True
    return False


@dataclass
class ViaTemplate:
    """Via array template for high-current routing.

    Defines a grid pattern of vias for nets requiring higher current capacity
    than a single via can provide (e.g., power nets, high-current traces).

    Attributes:
        name: Template identifier (e.g., 'Via1x1', 'Via2x2', 'Via3x3')
        rows: Number of vias in vertical direction
        cols: Number of vias in horizontal direction
        via_diameter_mm: Individual via pad diameter in mm
        via_drill_mm: Individual via drill diameter in mm
        pitch_mm: Center-to-center spacing between vias in mm

    Example:
        >>> template = ViaTemplate("Via2x2", 2, 2, 0.6, 0.3, 1.2)
        >>> width, height = template.get_footprint_bbox()
        >>> print(f"2x2 array footprint: {width}x{height}mm")
    """

    name: str
    rows: int
    cols: int
    via_diameter_mm: float
    via_drill_mm: float
    pitch_mm: float

    def get_footprint_bbox(self) -> tuple[float, float]:
        """Calculate bounding box (width, height) of via array.

        Returns:
            Tuple of (width_mm, height_mm) for the entire via array footprint
        """
        width = (self.cols - 1) * self.pitch_mm + self.via_diameter_mm
        height = (self.rows - 1) * self.pitch_mm + self.via_diameter_mm
        return (width, height)

    @property
    def via_count(self) -> int:
        """Total number of vias in array."""
        return self.rows * self.cols

    def get_via_positions(self, center_x: float, center_y: float) -> list[tuple[float, float]]:
        """
        Calculate via positions in array centered at (center_x, center_y).

        Args:
            center_x: Array center X coordinate (mm)
            center_y: Array center Y coordinate (mm)

        Returns:
            List of (x, y) via positions in mm
        """
        positions = []

        # Calculate array dimensions
        array_width = (self.cols - 1) * self.pitch_mm
        array_height = (self.rows - 1) * self.pitch_mm

        # Starting position (top-left of array)
        start_x = center_x - array_width / 2.0
        start_y = center_y - array_height / 2.0

        # Generate grid positions
        for row in range(self.rows):
            for col in range(self.cols):
                x = start_x + col * self.pitch_mm
                y = start_y + row * self.pitch_mm
                positions.append((x, y))

        return positions


@dataclass
class DesignRules:
    print("DEBUG: Loading design_rules.py")
    """PCB Design Rules Module.with net class support.

    Provides default routing parameters and net-class-specific overrides.
    Supports looking up rules by net name or net class.

    Attributes:
        default_trace_width: Default trace width in mm
        default_clearance: Default clearance in mm
        default_via_diameter: Default via diameter in mm
        default_via_drill: Default via drill diameter in mm
        net_classes: Dictionary of net class name -> NetClassRules
        net_overrides: Dictionary of net name -> NetClassRules for per-net overrides
    """

    default_trace_width: float = 0.2
    default_clearance: float = 0.2
    default_via_diameter: float = 0.6
    default_via_drill: float = 0.3
    net_classes: dict[str, NetClassRules] = field(default_factory=dict)
    net_overrides: dict[str, NetClassRules] = field(default_factory=dict)
    net_class_assignments: dict[str, str] = field(default_factory=dict)
    differential_pairs: list[DifferentialPairConstraint] = field(default_factory=list)
    bus_cohorts: list[BusCohortConstraint] = field(default_factory=list)
    net_topologies: dict[str, NetGraph] = field(default_factory=dict)
    via_templates: dict[str, ViaTemplate] = field(
        default_factory=lambda: {
            "Via1x1": ViaTemplate("Via1x1", 1, 1, 0.6, 0.3, 1.0),
            "Via2x2": ViaTemplate("Via2x2", 2, 2, 0.6, 0.3, 1.2),
            "Via3x3": ViaTemplate("Via3x3", 3, 3, 0.6, 0.3, 1.2),
            "Via4x4": ViaTemplate("Via4x4", 4, 4, 0.6, 0.3, 1.2),
        }
    )

    def get_via_template(self, net_name: str) -> ViaTemplate:
        """Get via template for a specific net.

        Args:
            net_name: Net name

        Returns:
            ViaTemplate to use for this net
        """
        rules = self.get_rules_for_net(net_name)
        template_name = rules.via_template

        if template_name in self.via_templates:
            return self.via_templates[template_name]

        # Fallback to 1x1 if template not found
        return self.via_templates["Via1x1"]

    def get_rules_for_net(self, net_name: str, net_class: str | None = None) -> NetClassRules:
        """Get routing rules for a specific net.

        Lookup priority:
        1. Per-net override (net_overrides[net_name])
        2. Net class rules (net_classes[net_class])
        3. Default rules

        Args:
            net_name: Net name (e.g., 'VCC', 'NET1')
            net_class: Optional net class name (e.g., 'Power', 'Signal')

        Returns:
            NetClassRules for this net
        """
        # Check net-specific override first
        if net_name in self.net_overrides:
            return self.net_overrides[net_name]

        # Check explicit net class assignment
        if not net_class and net_name in self.net_class_assignments:
            net_class = self.net_class_assignments[net_name]

        # Then check net class
        if net_class and net_class in self.net_classes:
            return self.net_classes[net_class]

        # Check if net name matches a known ground net pattern (before power)
        if self._is_ground_net(net_name) and "GND" in self.net_classes:
            return self.net_classes["GND"]

        # Check if net name matches a known power net pattern
        if self._is_power_net(net_name) and "Power" in self.net_classes:
            return self.net_classes["Power"]

        # Check if net name implies Gate Drive, HV (switching) side (GATE_*)
        if self._is_gate_net_hv(net_name) and "GateDriveHV" in self.net_classes:
            return self.net_classes["GateDriveHV"]

        # Check if net name implies Gate Drive, SELV (controller) side (PWM_*)
        if self._is_gate_net_selv(net_name) and "GateDriveSELV" in self.net_classes:
            return self.net_classes["GateDriveSELV"]

        # Check if net name implies High Current (SW, AC, BUS)
        if self._is_high_current_net(net_name) and "HighCurrent" in self.net_classes:
            # If not explicitly matched as Power, or if we want to upgrade Power to HighCurrent
            # Actually, Power handled most VCCs. HighCurrent handles SW_NODE etc.
            return self.net_classes["HighCurrent"]

        # Return default rules
        return NetClassRules(
            name="Default",
            trace_width=self.default_trace_width,
            clearance=self.default_clearance,
            via_diameter=self.default_via_diameter,
            via_drill=self.default_via_drill,
            dru_priority=999,
        )

    def get_class_for_net(self, net_name: str) -> str:
        """Get the net class name for a specific net."""
        return self.get_rules_for_net(net_name).name

    def _is_ground_net(self, net_name: str) -> bool:
        """Check if net name matches common ground net patterns."""
        from temper_placer.router_v6.net_classification import is_ground_net

        return is_ground_net(net_name)

    def _is_power_net(self, net_name: str) -> bool:
        """Check if net name matches common power net patterns (excluding ground)."""
        from temper_placer.router_v6.net_classification import is_power_net

        if self._is_ground_net(net_name):
            return False
        return is_power_net(net_name)

    def _is_gate_net_hv(self, net_name: str) -> bool:
        """Check if net belongs to the HV (switching) side of gate-drive
        circuitry -- the secondary/output side of U7's reinforced barrier.

        Split 2026-07-28 (R4) from the single ``_is_gate_net`` alongside the
        ``GateDrive`` -> ``GateDriveHV``/``GateDriveSELV`` class split: GATE_*
        and SW_NODE (the node gate drive is referenced to) are HV-side:
        keeping them in one keyword match with PWM_* would leave this
        fallback unable to say which class a matched net belongs to. Word-
        boundary keyword match (delimited by ``_`` or start/end of the
        uppercased name) -- see :func:`_is_high_current_net`'s docstring for
        the bug history this shares.
        """
        upper = net_name.upper()
        # GATE_H, GATE_L, GATE_HS, GATE_LS, SW_NODE (ref for gate)
        patterns = ("GATE", "SW_NODE")
        return _hv_word_boundary_match(upper, patterns)

    def _is_gate_net_selv(self, net_name: str) -> bool:
        """Check if net belongs to the SELV (controller) side of gate-drive
        circuitry -- the primary/input side of U7's reinforced barrier.

        See :meth:`_is_gate_net_hv`'s docstring for why this is split out.
        """
        upper = net_name.upper()
        # PWM_H, PWM_L, PWM_HS, PWM_LS
        patterns = ("PWM",)
        return _hv_word_boundary_match(upper, patterns)

    def _is_high_current_net(self, net_name: str) -> bool:
        """Check if net carries high switching current.

        Bug history (2026-07-27): this previously matched ``"COIL"`` as a
        plain substring (``p in upper``), which matched
        ``discharge.k_dis1-coil1``/``...-coil2`` and
        ``power_in.bypass_relay-coil1``/``...-coil2`` -- four relay-coil
        nets declared SELV ("coil drive") in
        ``elec/domain_manifest.yaml`` -- misclassifying them as
        high-current/HV-adjacent. Same defect class as
        ``creepage_check.py`` (merge 5076e715) and ``clearance_check.py``
        (merge 466c7724); see
        ``docs/evidence/2026-07-27-net-classification-gate.md``.
        """
        upper = net_name.upper()
        # DC_BUS+, AC_L, AC_N, COIL
        patterns = ("DC_BUS", "AC_L", "AC_N", "COIL")
        return _hv_word_boundary_match(upper, patterns)

    def get_diff_pair_for_net(self, net_name: str) -> DifferentialPairConstraint | None:
        """Get differential pair constraint if net is part of a pair.

        Args:
            net_name: Net name to check

        Returns:
            DifferentialPairConstraint if net is part of a differential pair, None otherwise
        """
        for pair in self.differential_pairs:
            if pair.net_pos == net_name or pair.net_neg == net_name:
                return pair
        return None

    def get_bus_cohort_for_net(self, net_name: str) -> BusCohortConstraint | None:
        """Get bus cohort constraint if net is part of a bus.

        Args:
            net_name: Net name to check

        Returns:
            BusCohortConstraint if net is part of a bus, None otherwise
        """
        for bus in self.bus_cohorts:
            if net_name in bus.nets:
                return bus
        return None


# =============================================================================
# Standard Net Classes for Temper Project
# =============================================================================

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
