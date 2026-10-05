"""Check pinned cold-study evidence and derive conditional interface calculations."""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round2/cooling"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    data = json.loads((HERE / "interface.json").read_text())
    report = json.loads((OUT / "checks.json").read_text())
    assert report["source_sha256"] == digest(HERE / "build_revision.py")
    assert report["interface_sha256"] == digest(HERE / "interface.json")
    assert report["step"]["sha256"] == digest(OUT / "native19-r4-round2-cold.step")
    for row in data["sources"].values():
        assert digest(ROOT / row["path"]) == row["sha256"]
    assert report["native_parts"] == 142
    assert report["sink_connected_solids"] == 1
    for key in (
        "native_collisions",
        "r4_collisions",
        "native_vs_r4_collisions",
        "airway_obstacles",
    ):
        assert not report[key], (key, report[key])
    allowed = {}
    for side in ("LEFT", "RIGHT"):
        for z in (22, 62):
            allowed[frozenset(("CUSTOM_SINK", f"SINK_M3_{side}_{z}"))] = (
                math.pi * (1.5**2 - 1.25**2) * 6
            )
    for i in range(4):
        rail = "CARRIER_RAIL_-122p5" if i < 2 else "CARRIER_RAIL_128p5"
        allowed[frozenset((rail, f"CARRIER_M3x25_{i}"))] = math.pi * (1.5**2 - 1.25**2) * 5.4
        allowed[frozenset((rail, f"FLOOR_MOUNT_SCREW_{i}"))] = math.pi * (1.5**2 - 1.25**2) * 6
    for i in range(4, 8):
        allowed[frozenset((f"FLOOR_MOUNT_SCREW_{i}", f"CRADLE_M4_NUT_{i}"))] = (
            math.pi * (2**2 - 1.65**2) * 3
        )
    seen = set()
    for hit in report["new_pair_intersections"]:
        pair = frozenset((hit["a"], hit["b"]))
        assert pair in allowed, ("Unreviewed assembly intersection", hit)
        assert abs(hit["volume_mm3"] - allowed[pair]) < 1e-5, hit
        seen.add(pair)
    assert seen == set(allowed), "Thread/contact topology changed"
    prior = json.loads((ROOT / data["sources"]["corrected_package_bounds"]["path"]).read_text())
    front = Decimal(str(data["contact"]["ceramic_front_local_y"]))
    intervals = {}
    for part in ("mos", "bridge"):
        inputs = prior["dimensional_inputs"][part]
        center = Decimal(str(inputs["lead_center_board_y"]))
        edge = [Decimal(str(v)) for v in inputs["rear_to_near_lead_edge"]]
        lead = [Decimal(str(v)) for v in inputs["lead_thickness"]]
        correct = sorted(center - e - c / 2 for e in edge for c in lead)
        wrong = sorted(center - e + c / 2 for e in edge for c in lead)
        assert correct != wrong, "Near-edge sign regression oracle lost discrimination"
        actual = [float(correct[0] - front), float(correct[-1] - front)]
        assert actual == data["contact"]["shim_geometric_ranges_before_films_mm"][part]
        intervals[part] = actual
    flow = data["thermal_allocation"]["delivered_CFM_min"] * 0.00047194745
    sections = report["airway_slice_area_mm2"]
    throats = {side: min(values.values()) for side, values in sections.items()}
    air = {
        side: {
            "sampled_min_area_mm2": area,
            "velocity_at_requested_flow_m_per_s": flow / (area * 1e-6),
            "dynamic_pressure_Pa_at_assumed_density_1p092": 0.5
            * 1.092
            * (flow / (area * 1e-6)) ** 2,
        }
        for side, area in throats.items()
    }
    route = data["pe"]["bond_path_world_xyz"]
    length = sum(math.dist(a, b) for a, b in zip(route, route[1:], strict=False))
    result = {
        "status": "PINNED_NOMINAL_COLD_GEOMETRY_CHECKS_PASS_NOT_PHYSICAL_QUALIFICATION",
        "native_parts": report["native_parts"],
        "step": report["step"],
        "accepted_thread_intersections": len(seen),
        "unexpected_intersections": 0,
        "shim_plus_film_geometric_intervals_mm": intervals,
        "pe_route_centerline_mm": length,
        "airway_screen": air,
        "airway_screen_limits": "Sampled0.1mmsection areas;20CFM is a requested flow, not a measured operating point;1.092kg/m3 air density is an engineering50C assumption. Pressure losses, fan P-Q and sink thermal performance unverified.",
        "service_open_projection_hits": report["fuse_open_projection_vs_installed_context"],
        "pins": {
            name: digest(HERE / name)
            for name in (
                "interface.json",
                "build_revision.py",
                "check_revision.py",
                "README.md",
                "sources.json",
                "plot_revision.py",
            )
        },
        "checks_sha256": digest(OUT / "checks.json"),
    }
    (OUT / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
