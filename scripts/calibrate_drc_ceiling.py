#!/usr/bin/env python3
"""Calibrate DRC violation ceiling for Rust DRC engine.

Parses each specified .kicad_pcb file, runs temper_drc_rs.run_drc() on it,
and outputs an updated drc_ceiling.json with actual violation counts.

Usage:
    python3 scripts/calibrate_drc_ceiling.py pcb/*.kicad_pcb --output power_pcb_dataset/drc_ceiling.json
    python3 scripts/calibrate_drc_ceiling.py --boards pcb/temper.kicad_pcb pcb/temper_physics_routed.kicad_pcb
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def _setup_path(repo_root: Path) -> None:
    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _infer_package_type(footprint: str | None) -> str:
    """Infer SMD/THT/package type from footprint name."""
    fp_lower = footprint.lower() if footprint else ""
    if any(p in fp_lower for p in ("tht", "through", "pin", "dip")):
        return "tht"
    if "to-247" in fp_lower or "to247" in fp_lower:
        return "to247"
    if "to-220" in fp_lower or "to220" in fp_lower:
        return "to220"
    if "bga" in fp_lower:
        return "bga"
    if "qfn" in fp_lower:
        return "qfn"
    if "qfp" in fp_lower or "tqfp" in fp_lower:
        return "qfp"
    if "dpak" in fp_lower or "d2pak" in fp_lower:
        return "dpak"
    return "smd"


def build_board_dict(parsed) -> dict:
    """Build K1-schema board_dict from a ParsedPCB object."""
    components = []
    for c in parsed.components:
        x, y = c.initial_position or (0.0, 0.0)
        rotation = float(c.initial_rotation * 90) if c.initial_rotation is not None else 0.0
        side = "bottom" if c.initial_side is not None and c.initial_side == 1 else "top"
        components.append({
            "ref": c.ref,
            "x": x,
            "y": y,
            "rot": rotation,
            "side": side,
            "width": float(c.width),
            "height": float(c.height),
            "net_class": c.net_class,
            "package_type": _infer_package_type(c.footprint),
            "power_dissipation_w": None,
            "is_magnetic": False,
            "is_electrolytic": False,
            "vent_direction": None,
            "footprint_polygon": None,
        })

    nets: dict[str, list[str]] = {}
    net_classes: dict[str, str] = {}
    for net in parsed.nets:
        comp_refs = list({ref for ref, _ in net.pins})
        nets[net.name] = comp_refs
        net_classes[net.name] = net.net_class

    net_class_rules: dict[str, dict] = {}
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


def build_constraints_dict(parsed) -> dict:
    """Build a minimal constraints dict for the Rust DRC engine."""
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


def board_id_from_path(pcb_path: Path) -> str:
    """Derive a board_id from a PCB file path.

    Eg. 'pcb/temper.kicad_pcb' -> 'temper', '/absolute/path/foo.kicad_pcb' -> 'foo'.
    """
    stem = pcb_path.stem  # removes .kicad_pcb
    return stem


def run_rust_drc(pcb_path: Path) -> tuple[int, int, int, list[dict]]:
    """Run the Rust DRC engine on a PCB file.

    Returns:
        (error_count, warning_count, info_count, all_violations)
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    import temper_drc_rs

    parsed = parse_kicad_pcb_v6(str(pcb_path))
    board_dict = build_board_dict(parsed)
    constraints_dict = build_constraints_dict(parsed)

    violations = temper_drc_rs.run_drc(board_dict, constraints_dict)

    errors = sum(1 for v in violations if v.get("severity", "").upper() in ("ERROR", "CRITICAL"))
    warnings = sum(1 for v in violations if v.get("severity", "").upper() == "WARNING")
    infos = sum(1 for v in violations if v.get("severity", "").upper() == "INFO")

    return errors, warnings, infos, violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate DRC violation ceiling for Rust DRC engine")
    parser.add_argument("pcb_files", nargs="+", type=str, help="Paths to .kicad_pcb files")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path for drc_ceiling.json (default: print to stdout)")
    args = parser.parse_args()

    repo_root = _find_repo_root()
    _setup_path(repo_root)

    boards = []
    all_ok = True

    for pcb_rel in args.pcb_files:
        pcb_path = Path(pcb_rel)
        if not pcb_path.is_absolute():
            pcb_path = repo_root / pcb_path

        if not pcb_path.exists():
            print(f"ERROR: PCB file not found: {pcb_path}", file=sys.stderr)
            all_ok = False
            continue

        board_id = board_id_from_path(pcb_path)
        print(f"Running Rust DRC on {board_id} ({pcb_path})...", end=" ", flush=True)

        try:
            errors, warnings, infos, violations = run_rust_drc(pcb_path)

            # Count violations by check_name
            check_counts = Counter(v.get("check_name", "unknown") for v in violations)

            print(f"{errors} errors, {warnings} warnings, {infos} infos")
            for check, count in sorted(check_counts.items()):
                print(f"  {check}: {count}")

            # Build violations_by_type from check_name counts
            violations_by_type: dict[str, int] = {}
            for v in violations:
                name = v.get("check_name", "unknown")
                sev = v.get("severity", "ERROR").upper()
                key = f"{name}:{sev}"
                violations_by_type[key] = violations_by_type.get(key, 0) + 1

            # Relative path from repo root for ceiling file
            try:
                rel_path = pcb_path.relative_to(repo_root)
            except ValueError:
                rel_path = pcb_path

            boards.append({
                "board_id": board_id,
                "path": str(rel_path),
                "error_ceiling": errors,
                "warning_ceiling": warnings,
                "violations_by_type": violations_by_type,
            })

        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            all_ok = False

    ceiling = {"boards": boards}

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(ceiling, f, indent=2)
        print(f"\nWrote drc_ceiling.json to {output_path}")
    else:
        print("\n" + json.dumps(ceiling, indent=2))

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
