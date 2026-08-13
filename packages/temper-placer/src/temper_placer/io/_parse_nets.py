"""Internal: net, net class, safety classification, and design rules extraction.

Migrated to the Rust parse engine (``temper_design_bundle_python.parse_engine``,
Wave 4 Phase 3 candidate 3). What moved to Rust:

- ``extract_net_classes`` — the pure-text net-class regex kernel
  (``parse_engine.extract_net_classes``), bit-identical against the oracle.
- the net extraction itself — ``_extract_nets_from_pcb`` runs inside
  ``parse_kicad_pcb`` on the Rust side.

What deliberately stays Python (R3-style boundary, argued in VERIFICATION.md):

- ``_apply_safety_classifications`` — a pure function over the contract
  pyclasses (``Netlist``/``Component``/``Pin``/``DesignRules``) with no kiutils
  dependency; both differential arms apply the identical code to identical
  inputs.
- ``_extract_design_rules`` — the assembly that targets the Python dataclass
  ``NetClassRules`` (``router_v6.stage0_data``) and the v6-only wrapper; it
  consumes the Rust ``extract_net_classes`` kernel plus the same hardcoded
  defaults the oracle uses (kiutils 1.4.8 exposes neither ``setup.defaults``
  nor ``board.netClasses``, so those branches never fired in the oracle).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

from temper_placer.core.design_rules import DesignRules
from temper_placer.core.netlist import Netlist

_rs = _tdb.parse_engine

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard

# Pure-text net-class extraction kernel (Rust; kiutils-free).
extract_net_classes = _rs.extract_net_classes


def _apply_safety_classifications(netlist: Netlist, design_rules: DesignRules) -> None:
    """
    Apply safety classifications from design rules to each component's net_class.

    For each component, determines the most severe safety category among its
    connected nets and sets ``comp.net_class`` accordingly:

    - Any net with ``safety_category`` ``"HV"`` or ``"AC"`` → ``"HighVoltage"``
    - All nets ``"LV"`` or unclassified → keeps existing default (``"Signal"``)

    Severity order: ``HV > AC > LV``. A component with one HV net and one LV net
    is classified as ``"HighVoltage"`` — the worst-case classification.

    Args:
        netlist: The parsed netlist (mutated in-place).
        design_rules: Design rules with ``net_class_assignments`` and ``net_classes``
            containing ``NetClassRules`` with ``safety_category`` values.
    """
    severity_order = {"HV": 3, "AC": 2, "LV": 1}
    severity_to_class = {3: "HighVoltage", 2: "HighVoltage"}

    for comp in netlist.components:
        max_severity = 0

        for pin in comp.pins:
            if not pin.net:
                continue

            class_name = design_rules.net_class_assignments.get(pin.net)
            if class_name and class_name in design_rules.net_classes:
                nc_rules = design_rules.net_classes[class_name]
                safety = nc_rules.safety_category
                if safety in severity_order:
                    sev = severity_order[safety]
                    if sev > max_severity:
                        max_severity = sev

        if max_severity in severity_to_class:
            comp.net_class = severity_to_class[max_severity]


def _class_current_rating(class_name: str):
    """The oracle's current-rating heuristic: ``Power_5A`` -> ``5.0``.

    Only fires when the underscore-suffixed tail of the class name, with all
    ``A`` and ``.`` characters removed, is all digits.
    """
    if "_" not in class_name:
        return None
    tail = class_name.split("_")[-1]
    stripped = tail.replace("A", "").replace(".", "")
    if not stripped or not stripped.isdigit():
        return None
    try:
        return float(tail.replace("A", ""))
    except ValueError:
        return None


def _extract_design_rules(
    _ki_board: KiBoard, _warnings: list[str], pcb_content: str | None = None
) -> DesignRules:
    """
    Extract KiCad design rules from board setup.

    .. note::

        Native netclass extraction from KiCad PCB files is **vestigial**. The
        authoritative source is ``configs/netclass_rules.yaml``, loaded via
        ``load_netclass_rules()`` and injected into the pipeline by
        ``route_pcb()`` as ``net_classes`` (see plan 2026-07-23-008 R7).

        This function exists for **backward compatibility** and for boards
        that embed netclass data directly in ``.kicad_pcb`` files. It should
        **NOT** be extended with new fields (e.g., ``safety_category``) --
        those belong in the YAML SSOT and its one-way adapter
        ``_to_stage0_netclass_rules()``.

    Migrated (candidate 3): the text kernel (``extract_net_classes``) runs in
    Rust; the assembly below targets the Python ``NetClassRules`` dataclass and
    stays here (the v6-only path). ``_ki_board`` is accepted for call
    compatibility but unused: kiutils 1.4.8 exposes neither ``setup.defaults``
    nor ``board.netClasses``, so the oracle's two kiutils-driven branches never
    fired.
    """
    from temper_placer.router_v6.stage0_data import NetClassRules

    net_classes = {}
    net_class_assignments = {}

    default_clearance = 0.2
    # 0.20mm, not the 0.25 this carried until 2026-08-12. Three declared
    # sources say 0.2 and none said 0.25: `pcb/temper.kicad_pro`'s `Default`
    # net class (`track_width: 0.2`), the same file's
    # `design_settings.rules.min_track_width` (0.2), and
    # `core/design_rules.py`'s `default_trace_width=0.2`. The generated DRU's
    # `Signal trace width` rule is likewise `min 0.2mm`.
    #
    # It is load-bearing for `clearance`, not cosmetic. Stage 4's A* reserves
    # `trace_width + clearance` around routed copper and the routing lattice
    # is 0.1mm, so this number sets the achievable inter-net pitch:
    #   0.25 + 0.20 = 0.45 -> quantises up to a 0.50mm pitch (25% coarser,
    #                         measured cost: 4497 -> 3410 segments,
    #                         86/102 -> 73/102 nets)
    #   0.20 + 0.20 = 0.40 -> lands exactly on the lattice, keeping the
    #                         original 0.40mm pitch, and the resulting
    #                         edge gap is 0.40 - 0.20 = 0.20mm, exactly the
    #                         `Default routing` rule rather than 0.05mm under
    #                         it.
    # See docs/evidence/2026-08-12-clearance-congestion-band.md.
    default_trace_width = 0.2
    default_via_diameter = 0.8
    default_via_drill = 0.4

    manual_classes = {}
    if pcb_content:
        manual_classes = extract_net_classes(pcb_content)

    if manual_classes:
        for class_name, rules in manual_classes.items():
            clearance = rules.get("clearance")
            if clearance is None:
                clearance = default_clearance

            trace_width = rules.get("trace_width")
            if trace_width is None:
                trace_width = default_trace_width

            via_diameter = rules.get("via_dia")
            if via_diameter is None:
                via_diameter = default_via_diameter

            via_drill = rules.get("via_drill")
            if via_drill is None:
                via_drill = default_via_drill

            net_classes[class_name] = NetClassRules(
                name=class_name,
                clearance_mm=clearance,
                trace_width_mm=trace_width,
                via_diameter_mm=via_diameter,
                via_drill_mm=via_drill,
                diff_pair_gap_mm=rules.get("diff_pair_gap"),
                diff_pair_width_mm=rules.get("diff_pair_width"),
                current_rating_amps=_class_current_rating(class_name),
            )

            for net_name in rules.get("nets", []):
                net_class_assignments[net_name] = class_name

    if "Signal" not in net_classes:
        net_classes["Signal"] = NetClassRules(
            name="Signal",
            clearance_mm=default_clearance,
            trace_width_mm=default_trace_width,
            via_diameter_mm=default_via_diameter,
            via_drill_mm=default_via_drill,
        )

    return DesignRules(
        net_classes=net_classes,
        net_class_assignments=net_class_assignments,
        default_clearance=default_clearance,
        default_trace_width=default_trace_width,
        default_via_diameter=default_via_diameter,
        default_via_drill=default_via_drill,
    )
