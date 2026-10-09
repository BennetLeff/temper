"""Integrate immutable cooling replacements and proper native/catch geometry."""

from __future__ import annotations

import json

from build_integration import ROOT, bounds, cylinder, hits, read_parts, sha
from correct_power_installation import correct


def merge(parts):
    directory = ROOT / "output/temper-prototype-closure/round5/orientation-cooling"
    checks = json.loads((directory / "checks-pe-final.json").read_text())
    assert not checks["native_hits"] and not checks["context_hits"]
    removed = json.loads((directory / "removed_names-pe-final.json").read_text())
    interface = json.loads((directory / "interface-pe-final.json").read_text())
    replacement_path = directory / "cooling-replacements-pe-final.step"
    assert sha(replacement_path) == checks["cooling-replacements"]["sha256"]
    replacement = read_parts(replacement_path)
    result = {k: v for k, v in parts.items() if k not in removed}
    result.update(replacement)
    floor = "BASE_BASE_R4_two_bend_bottom_and_sides"
    # Candidate is a NEW fabricated floor. Restore obsolete source holes before
    # drilling the replacement pattern, otherwise 1mm rail shifts create slots.
    obsolete = [
        (-116.5, 210, 3.4),
        (-116.5, 290, 3.4),
        (134.5, 210, 3.4),
        (134.5, 290, 3.4),
        (-120, 87, 4.4),
        (-120, 158, 4.4),
        (120, 87, 4.4),
        (120, 160, 4.4),
    ]
    for x, y, d in obsolete:
        result[floor] = result[floor].fuse(cylinder([x, y, 8], [x, y, 10], d / 2))
    for row in interface["floor_drilling"]:
        x, y = row["center_xy"]
        result[floor] = result[floor].cut(cylinder([x, y, 7], [x, y, 11], row["diameter"] / 2))
    result, power = correct(result)
    source_files = [
        directory / n
        for n in [
            "checks-pe-final.json",
            "interface-pe-final.json",
            "removed_names-pe-final.json",
            "cooling-replacements-pe-final.step",
        ]
    ]
    power.update(
        cooling_sources=[
            {"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in source_files
        ],
        obsolete_floor_holes_restored_xy_d_mm=obsolete,
        new_cooling_floor_holes=interface["floor_drilling"],
    )
    return result, power


def screen(parts):
    native = {k: v for k, v in parts.items() if k.startswith("BASE_BASE_native19_")}
    catch = {
        k: v
        for k, v in parts.items()
        if k.startswith(("J8_", "J10_", "PAIRED_", "BUS_P_", "HV_RET_", "CC1_HV_RET_"))
    }
    rest = {k: v for k, v in parts.items() if k not in native and k not in catch}
    checks = {
        "power_native_vs_context": hits(
            native, {k: v for k, v in parts.items() if k not in native}
        ),
        "corrected_catch_vs_context": hits(catch, rest),
        "corrected_catch_pair": [],
    }
    pairs = []
    names = list(catch)
    for i, a in enumerate(names):
        pairs += hits({a: catch[a]}, {b: catch[b] for b in names[i + 1 :]})
    allowed = {
        frozenset(
            ["HV_RET_INSULATED_WIRE_MAX", "CC1_HV_RET_STRIPPED_TERMINATION_ENVELOPE"]
        ): "Wire maximum envelope contains its continuing stripped conductor at jacket exit",
        frozenset(
            ["CC1_HV_RET_M4_RING_LUG_CANDIDATE", "CC1_HV_RET_STRIPPED_TERMINATION_ENVELOPE"]
        ): "Explicit electrical termination landing; exact crimp/solder process remains unqualified",
    }
    contacts = []
    remaining = []
    for row in checks["corrected_catch_vs_context"]:
        if row["new"].startswith("PAIRED_POST_M3x60_CS_") and "CARRIER_RAIL_" in row["context"]:
            y = float(row["new"].rsplit("_", 1)[1])
            b = bounds(catch[row["new"]].intersect(rest[row["context"]]))
            assert abs(row["volume_mm3"] - 12.959069696) < 1e-5, row
            assert b[1] >= y - 1.5 - 1e-6 and b[4] <= y + 1.5 + 1e-6
            assert abs(b[2] - 10) < 1e-6 and abs(b[5] - 16) < 1e-6, row
            contacts.append(
                dict(
                    row,
                    reason="M3 major-cylinder overlap in Ø2.5 tapped rail, exactly 6mm engagement",
                    bounds_mm=b,
                )
            )
        else:
            remaining.append(row)
    checks["corrected_catch_vs_context"] = remaining
    for row in pairs:
        key = frozenset([row["new"], row["context"]])
        if row["new"] == "PAIRED_WIRE_SADDLE_LOWER" and row["context"].startswith(
            "PAIRED_CLOSURE_M2x8_"
        ):
            assert abs(row["volume_mm3"] - 2.827433388) < 1e-5, row
            contacts.append(
                dict(
                    row,
                    reason="M2 major-cylinder overlap in Ø1.6 lower-half pilot, 2.5mm engagement",
                )
            )
        elif key in allowed:
            intersection = catch[row["new"]].intersect(catch[row["context"]])
            b = bounds(intersection)
            # Limit accepted conductor continuation to its declared local terminal.
            assert all(
                b[i] >= lo - 1e-6 and b[i + 3] <= hi + 1e-6
                for i, (lo, hi) in enumerate([(53, 61), (343, 351), (58, 66)])
            ), row
            contacts.append(dict(row, bounds_mm=b, reason=allowed[key]))
        else:
            checks["corrected_catch_pair"].append(row)
    return checks, contacts
