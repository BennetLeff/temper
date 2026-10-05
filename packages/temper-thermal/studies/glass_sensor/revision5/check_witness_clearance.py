"""Check the routed wires against the nominal witness rods and optical flags."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    source = ROOT / "mechanical/build.py"
    spec = importlib.util.spec_from_file_location("r5_cad_witness_check", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import R5 CAD")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    states = [
        ("rest", 0, 0, 0),
        ("loaded", 0.490909, 0.109091, 0),
        ("local_stop", 0, 0.25, 0),
        ("full_stroke", 1.2, 0.25, 0),
        ("upper_capture", 0, -0.1, 0),
        ("cap_capture", 0, 0, 0.2),
    ]
    results = []
    for variant, radius in [("D8", 4), ("D6", 3)]:
        for state, common, local, lift in states:
            parts, _ = module.build(radius, common, local, lift)
            wires = [p for p in parts if p.name.startswith("PFA_route")]
            witnesses = [p for p in parts if "witness_rod" in p.name or "optical_flag" in p.name]
            if len(wires) != 4 or len(witnesses) != 4:
                raise ValueError("Unexpected wire/witness count")
            hits = []
            for wire in wires:
                for target in witnesses:
                    overlap = wire.shape.intersect(target.shape).Volume()
                    if overlap > 1e-6:
                        hits.append(
                            {
                                "wire": wire.name,
                                "target": target.name,
                                "overlap_mm3": overlap,
                            }
                        )
            results.append({"variant": variant, "pose": state, "intersections": hits})
            print(variant, state, len(hits), flush=True)
    (ROOT / "witness-clearance.json").write_text(
        json.dumps(
            {
                "checks": results,
                "scope": "Nominal geometry only; optical line of sight, rod deflection and thermal growth not established.",
            },
            indent=2,
        )
        + "\n"
    )
    if any(row["intersections"] for row in results):
        raise ValueError("Wire/witness interference requires geometry revision")


if __name__ == "__main__":
    main()
