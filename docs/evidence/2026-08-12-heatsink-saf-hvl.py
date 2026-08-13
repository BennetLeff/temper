#!/usr/bin/env python3
"""SAF_HVL_001 count via the Rust safety kernel, for one or more boards.

Reuses the EXACT board_dict/constraints_dict construction that
temper_placer.regression.drc_ratchet.DrcRatchet._run_rust_drc uses in
production (not DrcBoardSnapshot.from_netlist), then calls
temper_drc_rs.run_drc(..., categories=["safety"]).
"""
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import temper_drc_rs
from temper_placer.core.design_rules import TEMPER_NET_CLASSES
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6


def build(pcb_path: Path):
    parsed = parse_kicad_pcb_v6(pcb_path)
    components = []
    for c in parsed.components:
        x, y = c.initial_position or (0.0, 0.0)
        rotation = float(c.initial_rotation * 90) if c.initial_rotation is not None else 0.0
        side = "bottom" if c.initial_side is not None and c.initial_side == 1 else "top"
        fp_lower = c.footprint.lower() if c.footprint else ""
        if any(p in fp_lower for p in ("tht", "through", "pin", "dip")):
            package_type = "tht"
        elif "to-247" in fp_lower or "to247" in fp_lower:
            package_type = "to247"
        elif "to-220" in fp_lower or "to220" in fp_lower:
            package_type = "to220"
        elif "bga" in fp_lower:
            package_type = "bga"
        elif "qfn" in fp_lower:
            package_type = "qfn"
        elif "qfp" in fp_lower or "tqfp" in fp_lower:
            package_type = "qfp"
        elif "dpak" in fp_lower or "d2pak" in fp_lower:
            package_type = "dpak"
        else:
            package_type = "smd"
        components.append({
            "ref": c.ref, "x": x, "y": y, "rot": rotation, "side": side,
            "width": float(c.width), "height": float(c.height),
            "net_class": c.net_class, "package_type": package_type,
            "power_dissipation_w": None, "is_magnetic": False,
            "is_electrolytic": False, "vent_direction": None,
            "footprint_polygon": None, "is_mechanical": c.ref.startswith("MH"),
        })
    nets, net_classes = {}, {}
    for net in parsed.nets:
        nets[net.name] = list({ref for ref, _ in net.pins})
        net_classes[net.name] = net.net_class
    net_class_rules = {
        n: {"trace_width_mm": r.trace_width, "clearance_mm": r.clearance,
            "creepage_mm": r.creepage_mm, "voltage_v": r.voltage_v,
            "max_current_rating": r.max_current_rating,
            "safety_category": r.safety_category,
            "required_layer": r.required_layer,
            "routing_strategy": r.routing_strategy}
        for n, r in TEMPER_NET_CLASSES.items()
    }
    board_dict = {
        "board": {"width_mm": float(parsed.board.width),
                  "height_mm": float(parsed.board.height), "margin_mm": 3.0},
        "components": components, "nets": nets,
        "net_classes": net_classes, "net_class_rules": net_class_rules,
    }
    constraints_dict: dict[str, Any] = {
        "clearances": [], "zones": [], "critical_loops": [], "noise_domains": [],
        "isolation_barriers": [], "thermal_properties": [],
        "matched_length_groups": [], "snubber_requirements": [],
        "bleed_resistor": None, "skin_effect_derating": None,
        "hv_clearance_mm": 10.0,
        "board_width": float(parsed.board.width),
        "board_height": float(parsed.board.height),
    }
    return parsed, board_dict, constraints_dict


for arg in sys.argv[1:]:
    p = Path(arg)
    parsed, bd, cd = build(p)
    nc = Counter(c["net_class"] for c in bd["components"])
    viols = temper_drc_rs.run_drc(bd, cd, categories=["safety"])
    codes = Counter(v.get("code") for v in viols)
    gaps = sorted(v["actual_gap_mm"] for v in viols if "actual_gap_mm" in v)
    print(f"\n=== {p.name} ===")
    print(f"  components={len(bd['components'])}  net_class={dict(nc)}")
    print(f"  safety violations total={len(viols)}  by code={dict(codes)}")
    if gaps:
        import statistics
        print(f"  gap_mm: min={gaps[0]:.2f} median={statistics.median(gaps):.2f} "
              f"max={gaps[-1]:.2f}  zero-gap pairs={sum(1 for g in gaps if g == 0.0)}")
    for v in viols[:2]:
        print(f"    e.g. {v.get('message')}")
