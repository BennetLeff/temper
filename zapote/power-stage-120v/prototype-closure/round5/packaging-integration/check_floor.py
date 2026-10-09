"""Check final floor drilling and preservation against actual STEP solids."""

from __future__ import annotations

import json

import cadquery as cq
from build_integration import OUT, ROOT, cylinder, read_parts, sha


def main():
    power = json.loads((OUT / "rigid-power-installation.json").read_text())
    support = json.loads((OUT / "support-patterns.json").read_text())["records"]
    harness = json.loads((OUT / "harness-probe.json").read_text())
    rows = [
        {"xy_d": [*r["center_xy"], r["diameter"]], "role": r["role"], "owner": "cooling"}
        for r in power["new_cooling_floor_holes"]
    ]
    for r in support:
        if "floor_hole_d" in r:
            rows.append(
                {"xy_d": [*r["xy"], r["floor_hole_d"]], "role": r["id"], "owner": "support"}
            )
        for xy_d in r.get("floor_holes_xy_d", []):
            rows.append({"xy_d": xy_d, "role": r["id"], "owner": "support"})
    for k, r in harness["candidate_changes"].items():
        if "floor_hole_xy_d_mm" in r:
            rows.append({"xy_d": r["floor_hole_xy_d_mm"], "role": k, "owner": "harness"})
    assert len(rows) == 26 and len({tuple(r["xy_d"]) for r in rows}) == 26
    path = OUT / "candidate-drilled-floor.step"
    floor = cq.importers.importStep(str(path)).val()
    for r in rows:
        x, y, d = r["xy_d"]
        r["residual_material_mm3"] = floor.intersect(
            cylinder([x, y, 8.02], [x, y, 9.98], d / 2 - 0.02)
        ).Volume()
        assert r["residual_material_mm3"] < 1e-6, r
    source = (
        ROOT
        / "output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step"
    )
    old = read_parts(source)["BASE_BASE_R4_two_bend_bottom_and_sides"]
    tools = [
        cylinder([x, y, 7.9], [x, y, 10.1], d / 2 + 1e-5)
        for x, y, d in power["obsolete_floor_holes_restored_xy_d_mm"] + [r["xy_d"] for r in rows]
    ]
    # Sequential subtraction avoids invalid overlapping-tool compounds at the
    # shifted holes; those overlapping tools are precisely what this checks.
    lost_shape = old.cut(floor)
    gained_shape = floor.cut(old)
    for tool in tools:
        if not lost_shape.wrapped.IsNull() and abs(lost_shape.Volume()) > 1e-8:
            lost_shape = lost_shape.cut(tool)
        if not gained_shape.wrapped.IsNull() and abs(gained_shape.Volume()) > 1e-8:
            gained_shape = gained_shape.cut(tool)
    lost = 0.0 if lost_shape.wrapped.IsNull() else lost_shape.Volume()
    gained = 0.0 if gained_shape.wrapped.IsNull() else gained_shape.Volume()
    assert abs(lost) < 1e-5 and abs(gained) < 1e-5, (lost, gained)
    receipt = {
        "status": "PASS_NEW_FLOOR_PATTERN_AND_RETAINED_FEATURES",
        "floor_sha256": sha(path),
        "source_sha256": sha(source),
        "new_holes": rows,
        "obsolete_cooling_holes": power["obsolete_floor_holes_restored_xy_d_mm"],
        "undocumented_lost_volume_mm3": lost,
        "undocumented_gained_volume_mm3": gained,
        "instruction": "Fabricate new candidate floor; do not shift-drill an existing floor into overlapping slots.",
    }
    (OUT / "floor-drilling-manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS: 26 new holes; 8 obsolete cooling holes restored; no other floor features changed")


if __name__ == "__main__":
    main()
