# VERBATIM pre-migration oracle: _parse_nets.py (Wave 4 Phase 3 candidate 3, parse engine).
# Copied from packages/temper-placer/src/temper_placer/io/_parse_nets.py at commit 79ab9bd0e.
# Only edits vs the source: intra-oracle imports rewritten (temper_placer.io.X -> .X)
# so the oracle package is self-contained. Extraction bodies, dataclasses and
# kiutils usage are byte-identical to the pre-migration source. This is the pinned
# Python arm of the Rust parse-engine differential (R1a).
#
# DELIBERATE DIVERGENCE 2026-08-15: `_extract_nets_from_pcb` no longer drops
# single-pad nets (the pre-migration `len(n.pins) >= 2` filter). This oracle
# pins the MIGRATION contract -- Rust engine output == oracle output -- not the
# pre-migration behavior; a deliberate behavior correction has to be made on
# both sides or the differential starts asserting the defect (same precedent as
# the 0.25 -> 0.20 default_trace_width correction below). See that function's
# comment and extract_nets_pure in parse_engine.rs for the full rationale.
#
# DELIBERATE DIVERGENCE 2026-08-17 (docs/evidence/2026-08-17-blind-via-
# annular-floor-fix.md): `default_via_diameter`/`default_via_drill` 0.8/0.4 ->
# 0.9/0.3, in lockstep with the shim (`io/_parse_nets.py`). Same precedent as
# the 0.25 -> 0.20 default_trace_width correction: this oracle pins the
# migration contract, not the value, so the real bug fix (0.8/0.4 gave a
# 0.2mm annular ring, below JLCPCB's 2oz PTH floor of 0.254mm -- root-caused
# to exactly 56 vias on the committed board) has to land on both sides
# together or the differential starts asserting the defect instead of
# catching a regression.

"""Internal: net, net class, safety classification, and design rules extraction."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING, Any

# DesignRules is CONSTRUCTED at runtime (see _extract_design_rules' return), so
# it cannot live under TYPE_CHECKING. `from __future__ import annotations` makes
# the annotations resolve lazily either way, which is why mypy and the Type Check
# gate stayed green while the runtime path raised
# `name 'DesignRules' is not defined` -- surfaced as
# "written board failed parse_kicad_pcb_v6" in the regression suite.
# Safe as a module-level import: core.design_rules pulls in numpy, the design
# bundle and core.netclass_rules_gen, none of which import temper_placer.io.
from temper_placer.core.design_rules import DesignRules
from temper_placer.core.netlist import Component, Net, Netlist

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard


def _extract_nets_from_pcb(
    _ki_board: KiBoard,
    components: list[Component],
    _warnings: list[str],
) -> list[Net]:
    """
    Extract connectivity from Kiutils board object.

    Args:
        ki_board: Parsed board.
        components: Extracted components list.
        warnings: List for warning messages.

    Returns:
        List of Net instances.
    """
    nets_dict: dict[str, Net] = {}

    for comp in components:
        for pin in comp.pins:
            if not pin.net:
                continue

            if pin.net not in nets_dict:
                nets_dict[pin.net] = Net(name=pin.net, pins=[])

            nets_dict[pin.net].pins.append((comp.ref, pin.name))

    # DIVERGENCE (2026-08-15, deliberate, in lockstep with the Rust engine --
    # see extract_nets_pure in parse_engine.rs): the pre-migration code
    # filtered `len(n.pins) >= 2`, dropping single-pad nets. Single-pad nets
    # are real electrical entities that still need net-class assignment
    # (DRC, DRU emission, safety classification) and must stay in the
    # netlist registry so apply_net_class_mapping_strict can resolve every
    # key of temper_constraints.yaml's net_classes: (the ZCD orphan-footprint
    # removal leaves ac_l as a single-pad net). Routing already excludes
    # them (routing_space._routable_net_names requires >= 2 pins). Kept in
    # lockstep so the R1a differential stays a parity check rather than
    # asserting the pre-migration drop.
    return list(nets_dict.values())


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


def extract_net_classes(content: str) -> dict:
    """
    Extract net class definitions from raw KiCad PCB content.

    Returns:
        Dict mapping class name to dict of rules:
        {
            "Name": {
                "clearance": 0.2,
                "trace_width": 0.25,
                "via_dia": 0.8,
                "via_drill": 0.4,
                "nets": ["GND", "VCC"]
            }
        }
    """
    classes = {}

    start_indices = [m.start() for m in re.finditer(r"\(net_class\b", content)]

    for start in start_indices:
        balance = 0
        end = start
        found_start = False

        for i in range(start, len(content)):
            char = content[i]
            if char == "(":
                balance += 1
                found_start = True
            elif char == ")":
                balance -= 1

            if found_start and balance == 0:
                end = i + 1
                break

        block = content[start:end]

        name_match = re.search(r'^\(net_class\s+"([^"]+)"', block)
        if not name_match:
            continue

        name = name_match.group(1)

        rules: dict[str, Any] = {"nets": []}

        def get_float(pattern, _block=block):
            m = re.search(pattern, _block)
            return float(m.group(1)) if m else None

        rules["clearance"] = get_float(r"\(clearance\s+([\d.]+)\)")
        rules["trace_width"] = get_float(r"\(track_width\s+([\d.]+)\)") or get_float(
            r"\(trace_width\s+([\d.]+)\)"
        )
        rules["via_dia"] = get_float(r"\(via_dia\s+([\d.]+)\)")
        rules["via_drill"] = get_float(r"\(via_drill\s+([\d.]+)\)")
        rules["diff_pair_gap"] = get_float(r"\(diff_pair_gap\s+([\d.]+)\)")
        rules["diff_pair_width"] = get_float(r"\(diff_pair_width\s+([\d.]+)\)")

        rules["nets"] = re.findall(r'\(add_net\s+"([^"]+)"\)', block)

        classes[name] = rules

    return classes


def _extract_design_rules(
    ki_board: KiBoard, _warnings: list[str], pcb_content: str | None = None
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

    Args:
        ki_board: Parsed KiCad board.
        warnings: List to append warnings.
        pcb_content: Raw PCB file content (optional, for manual net class parsing).

    Returns:
        DesignRules with net classes and assignments.
    """
    from temper_placer.router_v6.stage0_data import NetClassRules

    net_classes = {}
    net_class_assignments = {}

    default_clearance = 0.2
    # 0.25 -> 0.20 on 2026-08-12, in lockstep with the shim
    # (``io/_parse_nets.py``). This oracle pins the MIGRATION contract --
    # shim output == pre-migration output -- not the VALUE, so a deliberate
    # value correction has to be made on both sides or the differential
    # starts asserting the defect. See that file's comment and
    # docs/evidence/2026-08-12-clearance-congestion-band.md for why 0.2 is
    # the correct figure (kicad_pro's Default track_width, the same file's
    # min_track_width, and core/design_rules.py all say 0.2).
    default_trace_width = 0.2
    # 0.8/0.4 -> 0.9/0.3 on 2026-08-17, in lockstep with the shim -- see the
    # "DELIBERATE DIVERGENCE 2026-08-17" module header note above. The inner
    # `getattr(..., 0.8)`/`getattr(..., 0.4)` fallbacks below are left
    # untouched: they sit behind `setup.defaults`, which kiutils 1.4.8 never
    # exposes, so that branch never fired in the oracle either (see this
    # function's own docstring in the shim) -- verbatim dead pre-migration
    # code, not a second copy of the live value.
    default_via_diameter = 0.9
    default_via_drill = 0.3

    if hasattr(ki_board, "setup") and ki_board.setup:
        setup = ki_board.setup
        if hasattr(setup, "defaults"):
            defaults = setup.defaults
            if hasattr(defaults, "clearance"):
                default_clearance = float(defaults.clearance)
            if hasattr(defaults, "trackWidth") or hasattr(defaults, "trace_width"):
                default_trace_width = float(
                    getattr(defaults, "trackWidth", getattr(defaults, "trace_width", 0.25))
                )
            if hasattr(defaults, "viaDiameter") or hasattr(defaults, "via_dia"):
                default_via_diameter = float(
                    getattr(defaults, "viaDiameter", getattr(defaults, "via_dia", 0.8))
                )
            if hasattr(defaults, "viaDrill") or hasattr(defaults, "via_drill"):
                default_via_drill = float(
                    getattr(defaults, "viaDrill", getattr(defaults, "via_drill", 0.4))
                )

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

            current_rating = None
            if (
                "_" in class_name
                and class_name.split("_")[-1].replace("A", "").replace(".", "").isdigit()
            ):
                with contextlib.suppress(ValueError):
                    current_rating = float(class_name.split("_")[-1].replace("A", ""))

            net_classes[class_name] = NetClassRules(
                name=class_name,
                clearance_mm=clearance,
                trace_width_mm=trace_width,
                via_diameter_mm=via_diameter,
                via_drill_mm=via_drill,
                diff_pair_gap_mm=rules.get("diff_pair_gap"),
                diff_pair_width_mm=rules.get("diff_pair_width"),
                current_rating_amps=current_rating,
            )

            for net_name in rules.get("nets", []):
                net_class_assignments[net_name] = class_name

    elif hasattr(ki_board, "netClasses") and ki_board.netClasses:
        for nc in ki_board.netClasses:
            class_name = nc.name if hasattr(nc, "name") else "Signal"

            clearance = float(getattr(nc, "clearance", default_clearance))
            trace_width = float(
                getattr(nc, "trackWidth", getattr(nc, "trace_width", default_trace_width))
            )
            via_diameter = float(
                getattr(nc, "viaDiameter", getattr(nc, "via_dia", default_via_diameter))
            )
            via_drill = float(getattr(nc, "viaDrill", getattr(nc, "via_drill", default_via_drill)))
            diff_pair_gap = (
                float(getattr(nc, "diffPairGap", 0)) if hasattr(nc, "diffPairGap") else None
            )
            diff_pair_width = (
                float(getattr(nc, "diffPairWidth", 0)) if hasattr(nc, "diffPairWidth") else None
            )

            current_rating = None
            if (
                "_" in class_name
                and class_name.split("_")[-1].replace("A", "").replace(".", "").isdigit()
            ):
                with contextlib.suppress(ValueError):
                    current_rating = float(class_name.split("_")[-1].replace("A", ""))

            net_classes[class_name] = NetClassRules(
                name=class_name,
                clearance_mm=clearance,
                trace_width_mm=trace_width,
                via_diameter_mm=via_diameter,
                via_drill_mm=via_drill,
                diff_pair_gap_mm=diff_pair_gap,
                diff_pair_width_mm=diff_pair_width,
                current_rating_amps=current_rating,
            )

            if hasattr(nc, "nets") and nc.nets:
                for net_name in nc.nets:
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
