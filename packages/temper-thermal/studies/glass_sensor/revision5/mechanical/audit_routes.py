"""Independent route/solid collision census; reports violations without suppressing them."""

import json
from pathlib import Path

import build

out = Path(__file__).resolve().parent
result = {}
for name, radius in [("D8", 4), ("D6", 3)]:
    states = {}
    for pose, common, local, lift in [
        ("rest", 0, 0, 0),
        ("loaded", 0.490909, 0.109091, 0),
        ("local_stop", 0, 0.25, 0),
        ("full_stroke", 1.2, 0.25, 0),
        ("upper_capture", 0, -0.1, 0),
        ("cap_capture", 0, 0, 0.2),
    ]:
        parts, routes = build.build(radius, common, local, lift)
        wires = [p for p in parts if p.name.startswith("PFA_route")]
        rigid = [p for p in parts if not p.envelope]
        hits = []
        for wire in wires:
            for part in rigid:
                volume = wire.shape.intersect(part.shape).Volume()
                if volume > 1e-6:
                    hits.append({"wire": wire.name, "part": part.name, "volume_mm3": volume})
        for i, wire in enumerate(wires):
            for other in wires[i + 1 :]:
                volume = wire.shape.intersect(other.shape).Volume()
                if volume > 1e-6:
                    hits.append({"wire": wire.name, "part": other.name, "volume_mm3": volume})
        states[pose] = {
            "intersections": hits,
            "route_envelope_volumes_mm3": [p.shape.Volume() for p in wires],
            "ideal_outer_volume_mm3": 3.141592653589793 * (0.116**2 * 59.5 + 0.04**2 * 0.5),
            "routes": routes,
        }
        print(name, pose, len(hits), flush=True)
    result[name] = states
(out / "route_audit.json").write_text(json.dumps(result, indent=2) + "\n")

failures = [
    f"{name}/{pose}"
    for name, states in result.items()
    for pose, data in states.items()
    if data["intersections"]
    or any(
        abs(volume - data["ideal_outer_volume_mm3"]) > 1e-5
        for volume in data["route_envelope_volumes_mm3"]
    )
]
if failures:
    raise RuntimeError("Route audit failed: " + ", ".join(failures))

_, _, _, terminals = build.components()
connectivity = []
for index in range(4):
    bead = build.weld_bead(index)
    wire = build.route(index, 0)[0]
    row = {
        "wire": index,
        "terminal": index // 2,
        "bead_wire_overlap_mm3": bead.intersect(wire).Volume(),
        "bead_terminal_overlap_mm3": bead.intersect(terminals[index // 2]).Volume(),
        "wrong_terminal_overlap_mm3": bead.intersect(terminals[1 - index // 2]).Volume(),
    }
    if (
        row["bead_wire_overlap_mm3"] <= 0
        or row["bead_terminal_overlap_mm3"] <= 0
        or row["wrong_terminal_overlap_mm3"] > 1e-8
    ):
        raise RuntimeError(f"Weld topology failure: {row}")
    connectivity.append(row)
(out / "weld_connectivity.json").write_text(json.dumps(connectivity, indent=2) + "\n")
