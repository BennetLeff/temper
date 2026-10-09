"""Verify the native-to-assembly chain and the extended support/harness evidence."""

import json

from check_receipt import OUT, ROOT, digest
from check_receipt import main as check_base


def main():
    (OUT / "installation-verification.json").write_text('{"status":"INCOMPLETE"}\n')
    orientation = json.loads((OUT / "power-orientation-verification.json").read_text())
    assert orientation["status"] == "PASS_ACTUAL_RIGID_POWER_GEOMETRY"
    assert digest(ROOT / orientation["assembly_path"]) == orientation["assembly_sha256"]
    assert orientation["assembly_path"] == str(
        (OUT / "r4-supported-routed-candidate.step").relative_to(ROOT)
    )
    check_base()
    support = json.loads((OUT / "support-receipt.json").read_text())
    assert support["status"] == "NOMINAL_CANDIDATE_NOT_RELEASED"
    for space, expected in support["inputs"].items():
        assert digest(OUT / f"{space}-nine-board-integration-candidate.step") == expected, space
    for item in support["exports"].values():
        assert item["valid"] and item["solids"] > 0
        assert digest(ROOT / item["path"]) == item["sha256"], item["path"]
    sc = json.loads((OUT / "support-checks.json").read_text())
    assert not any(rows for c in sc.values() for rows in c.values()), sc
    distances = json.loads((OUT / "support-critical-distances.json").read_text())["pairs"]
    assert min(p["nominal_distance_mm"] for p in distances) >= 1 - 1e-7
    harness = json.loads((OUT / "harness-receipt.json").read_text())
    assert harness["status"] == "NOMINAL_ROUTE_CANDIDATE_NOT_ELECTRICAL_ACCEPTANCE"
    assert digest(ROOT / harness["input"]) == harness["input_sha256"]
    assert harness["input_sha256"] == support["exports"]["r4"]["sha256"]
    for item in (harness["export"], harness["floor_export"]):
        assert item["valid"] and item["solids"] > 0
        assert digest(ROOT / item["path"]) == item["sha256"]
    assert digest(OUT / "native-pickoffs.json") == harness["native_pickoffs_sha256"]
    pick = json.loads((OUT / "native-pickoffs.json").read_text())
    assert digest(ROOT / pick["source"]) == pick["sha256"]
    hc = json.loads((OUT / "harness-checks.json").read_text())
    assert len(hc) == 10 and not any(hc.values()), hc
    route = json.loads((OUT / "harness-probe.json").read_text())
    for key, row in route["routes"].items():
        assert row["minimum_inside_wire_radius_mm"] >= row["required_manufacturer_10D_mm"], key
        assert all(m > 0 for m in row["tangent_margins_mm"]), key
    margins = json.loads((OUT / "harness-mechanical-margins.json").read_text())["pairs"]
    assert min(p["distance_mm"] for p in margins) >= 0.6 - 1e-6, margins
    floor = json.loads((OUT / "floor-drilling-manifest.json").read_text())
    assert floor["status"] == "PASS_NEW_FLOOR_PATTERN_AND_RETAINED_FEATURES"
    assert floor["floor_sha256"] == digest(OUT / "candidate-drilled-floor.step")
    # Resolve the cooling worker's explicitly delegated interfaces on the FINAL
    # exported assembly, after all support machining. Never waive deferred hits.
    from build_integration import bounds, cylinder, read_parts

    final_parts = read_parts(OUT / "r4-supported-routed-candidate.step")
    cooling = json.loads(
        (
            ROOT / "output/temper-prototype-closure/round5/orientation-cooling/checks-pe-final.json"
        ).read_text()
    )
    power = json.loads((OUT / "rigid-power-installation.json").read_text())
    deferred_results = []
    for row in cooling.get("packaging_deferred_context_hits", []):
        actual_context = power["superseded_mount_map"].get(row["context"], row["context"])
        a, b = final_parts[row["new"]], final_parts[actual_context]
        intersection = a.intersect(b)
        volume = 0.0 if intersection.wrapped.IsNull() else intersection.Volume()
        result = dict(row, final_context=actual_context, final_volume_mm3=volume)
        if row["context"] in ("PAIRED_POST_M3x60_CS_285", "PAIRED_POST_M3x60_CS_295"):
            assert row["new"] == "BASE_BASE_R2_CARRIER_RAIL_-122p5"
            bb = bounds(intersection)
            assert abs(volume - 12.959069696) < 1e-5, result
            assert abs(bb[2] - 10) < 1e-6 and abs(bb[5] - 16) < 1e-6
            result.update(disposition="EXACT_M3_THREAD_ANNULUS_6MM_ENGAGEMENT", bounds_mm=bb)
        else:
            assert row["new"] == "BASE_PROPOSAL_LEFT_WALL"
            assert row["context"] in ("OUT_FLOOR_M3x6_-126.0", "OUT_MACHINED_BRACKET_-128")
            assert abs(volume) < 1e-6, result
            result["disposition"] = "MACHINED_CLEAR_FINAL_GEOMETRY"
        deferred_results.append(result)
    lower = final_parts["PAIRED_WIRE_SADDLE_LOWER"]
    upper = final_parts["PAIRED_WIRE_SADDLE_UPPER"]
    assert len(lower.Solids()) == 1 and len(upper.Solids()) == 1
    assert "PAIRED_SADDLE_BASE" not in final_parts
    saddle_checks = []
    for y in [285, 295]:
        bolt = final_parts[f"PAIRED_POST_M3x60_CS_{y}"]
        post = final_parts[f"PAIRED_SADDLE_PEEK_POST_{y}"]
        tool = cylinder([135.5, y, 70.01], [135.5, y, 83], 2.0)
        for part in [lower, upper]:
            assert abs(part.intersect(tool).Volume()) < 1e-6
        assert lower.distance(bolt) < 1e-6 and lower.distance(post) < 1e-6
        saddle_checks.append(
            {
                "axis_xy": [135.5, y],
                "mount_head_to_integral_base_gap_mm": lower.distance(bolt),
                "post_to_integral_base_gap_mm": lower.distance(post),
                "driver_diameter_mm": 4,
                "access_well_diameter_mm": 6.2,
                "sequence": "Wires absent during mounting or service.",
            }
        )
    for y in [289.5, 294.5]:
        assert upper.distance(final_parts[f"PAIRED_CLOSURE_M2x8_{y}"]) < 1e-6
    (OUT / "installation-verification.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "native_capture_sha256": digest(OUT / "native-capture.json"),
                "collision_groups": 31,
                "integral_catch_guide_loadpath_checks": saddle_checks,
                "cooling_deferred_interfaces_resolved": deferred_results,
                "floor_drilling_manifest_sha256": digest(OUT / "floor-drilling-manifest.json"),
                "native_nine_placement_verification_sha256": digest(
                    OUT / "native-nine-placement-verification.json"
                ),
                "power_orientation_verification_sha256": digest(
                    OUT / "power-orientation-verification.json"
                ),
                "support_receipt_sha256": digest(OUT / "support-receipt.json"),
                "harness_receipt_sha256": digest(OUT / "harness-receipt.json"),
                "note": "Nominal digital candidate; qualification holds remain.",
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "PASS: current nine-board chain, support/connector checks, four native sense routes, bend margins, matching candidate floor and 31 empty collision groups plus explicitly measured thread/termination contacts"
    )


if __name__ == "__main__":
    main()
