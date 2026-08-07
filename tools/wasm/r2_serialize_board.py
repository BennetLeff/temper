#!/usr/bin/env python3
"""One-time board serialisation for the R2 full-board-pass benchmark.

Parses ``pcb/temper.kicad_pcb`` via the KiCad parser and the Python→Rust
bridge, then calls ``temper_drc_rs.serialize_board_state`` to produce a
JSON snapshot the Rust example ``r2_full_board_pass`` can deserialise.
Also writes a constraints JSON (``ConstraintSet::default()``).

Usage:
    uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json

Output (two files):
    <output>               — BoardState JSON (for r2_full_board_pass)
    <output>.constraints   — ConstraintSet JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def build_board_dict(parsed: Any) -> dict[str, Any]:
    """Build the K1-schema board dict consumed by the Rust bridge.

    Mirrors the logic in ``scripts/ci_closure_test.py`` and
    ``scripts/calibrate_drc_ceiling.py``.
    """
    components: list[dict[str, Any]] = []
    for c in parsed.components:
        x, y = c.initial_position or (0.0, 0.0)
        rotation = (
            float(c.initial_rotation * 90)
            if c.initial_rotation is not None
            else 0.0
        )
        side = (
            "bottom"
            if c.initial_side is not None and c.initial_side == 1
            else "top"
        )
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

        is_mechanical = c.ref.startswith("MH")
        components.append(
            {
                "ref": c.ref,
                "x": x,
                "y": y,
                "rot": rotation,
                "side": side,
                "width": float(c.width),
                "height": float(c.height),
                "net_class": c.net_class,
                "package_type": package_type,
                "power_dissipation_w": None,
                "is_magnetic": False,
                "is_electrolytic": False,
                "is_mechanical": is_mechanical,
                "vent_direction": None,
                "footprint_polygon": None,
            }
        )

    nets: dict[str, list[str]] = {}
    net_classes: dict[str, str] = {}
    for net in parsed.nets:
        comp_refs = list({ref for ref, _ in net.pins})
        nets[net.name] = comp_refs
        net_classes[net.name] = net.net_class

    net_class_rules: dict[str, dict[str, Any]] = {}
    for class_name, rules in parsed.design_rules.net_classes.items():
        net_class_rules[class_name] = {
            "trace_width_mm": rules.trace_width_mm,
            "clearance_mm": rules.clearance_mm,
            "creepage_mm": None,
            "voltage_v": None,
            "max_current_rating": None,
            "safety_category": None,
            "required_layer": None,
            "routing_strategy": None,
        }

    return {
        "board": {
            "width_mm": float(parsed.board.width),
            "height_mm": float(parsed.board.height),
            "margin_mm": 3.0,
        },
        "components": components,
        "nets": nets,
        "net_classes": net_classes,
        "net_class_rules": net_class_rules,
    }


def build_constraints_dict(parsed: Any) -> dict[str, Any]:
    """Build a minimal ConstraintSet dict matching the Rust serde schema."""
    return {
        "clearances": [],
        "zones": [],
        "critical_loops": [],
        "noise_domains": [],
        "isolation_barriers": [],
        "thermal_properties": [],
        "matched_length_groups": [],
        "snubber_requirements": [],
        "bleed_resistor": None,
        "skin_effect_derating": None,
        "hv_clearance_mm": 10.0,
        "board_width": float(parsed.board.width),
        "board_height": float(parsed.board.height),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serialize production board for R2 cost-model benchmark"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the BoardState JSON (constraints written to <output>.constraints)",
    )
    parser.add_argument(
        "--pcb",
        default="pcb/temper.kicad_pcb",
        help="Path to the KiCad PCB file (default: pcb/temper.kicad_pcb)",
    )
    args = parser.parse_args()

    # --- path setup --------------------------------------------------------
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))

    # --- parse PCB ---------------------------------------------------------
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6  # noqa: E402

    pcb_path = repo_root / args.pcb
    print(f"Parsing {pcb_path} ...", file=sys.stderr)
    parsed = parse_kicad_pcb_v6(str(pcb_path))
    print(
        f"  components: {len(parsed.components)}  nets: {len(parsed.nets)}",
        file=sys.stderr,
    )

    # --- build board dict -------------------------------------------------
    board_dict = build_board_dict(parsed)

    # --- serialise via Rust bridge ----------------------------------------
    import temper_drc_rs  # type: ignore[import-untyped]  # noqa: E402

    board_json_str = temper_drc_rs.serialize_board_state(board_dict)
    constraints_dict = build_constraints_dict(parsed)

    # --- write ------------------------------------------------------------
    out = Path(args.output)
    out.write_text(board_json_str, encoding="utf-8")
    print(f"Wrote BoardState JSON → {out}  ({len(board_json_str):,} bytes)", file=sys.stderr)

    constraints_out = out.with_suffix(out.suffix + ".constraints")
    constraints_out.write_text(json.dumps(constraints_dict), encoding="utf-8")
    print(f"Wrote ConstraintSet JSON → {constraints_out}", file=sys.stderr)

    # --- board hash (for evidence doc) ------------------------------------
    import hashlib

    board_bytes = pcb_path.read_bytes()
    board_hash = hashlib.sha256(board_bytes).hexdigest()
    print(f"\nBoard sha256: {board_hash}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
