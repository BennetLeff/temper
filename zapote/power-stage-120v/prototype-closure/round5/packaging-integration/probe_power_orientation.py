"""Measure proper native19 placements against the inherited reflected assembly.

No source geometry is changed. This is a rejection/proposal experiment, not an
installation release or an assertion that empty collision sets prove assembly.
"""

from __future__ import annotations

import json

from build_integration import OUT, ROOT, bounds, export, hits, read_parts, sha


def main():
    source = ROOT / "output/temper-prototype-closure/pcb/temper-power-native19-candidate.step"
    baseline = (
        ROOT
        / "output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step"
    )
    native = read_parts(source)
    native = {("SUBSTRATE" if k.startswith("=>") else k): v for k, v in native.items()}
    retained = read_parts(baseline)
    old = {
        k.removeprefix("BASE_BASE_native19_"): v
        for k, v in retained.items()
        if k.startswith("BASE_BASE_native19_")
    }
    context = {k: v for k, v in retained.items() if not k.startswith("BASE_BASE_native19_")}
    assert set(native) == set(old)
    candidates = {
        "identity_top_up": {k: v.translate((-110.5, 322, 30.387)) for k, v in native.items()},
        "rz180_top_up": {
            k: v.rotate((0, 0, 0), (0, 0, 1), 180).translate((129.5, 162, 30.387))
            for k, v in native.items()
        },
    }
    result = {
        "status": "REFLECTED_BASELINE_NOT_MANUFACTURING_GEOMETRY",
        "source_step": {"path": str(source.relative_to(ROOT)), "sha256": sha(source)},
        "baseline": {"path": str(baseline.relative_to(ROOT)), "sha256": sha(baseline)},
        "native_bounds": {k: bounds(v) for k, v in native.items()},
        "inherited_bounds": {k: bounds(v) for k, v in old.items()},
        "reflected_transform_determinant": -1,
        "proper_transform_determinant": 1,
        "candidates": {},
    }
    for name, parts in candidates.items():
        print("checking", name, flush=True)
        found = hits(parts, context)
        result["candidates"][name] = {
            "bounds": {k: bounds(v) for k, v in parts.items()},
            "intersections": found,
            "heat_source_bounds": {k: bounds(parts[k]) for k in ["BR1", "Q2", "Q3", "Q5", "Q6"]},
        }
        print(name, len(found), "intersections", flush=True)
        (OUT / "power-orientation-probe.json").write_text(json.dumps(result, indent=2) + "\n")
    # Reviewable true-handed proposal. Every existing support/contact remains so
    # the unresolved interface conflicts are visible, not silently deleted.
    result["rz180_review_step"] = export(
        "r4-rigid-power-orientation-PROBE-NOT-FIT",
        context | {"RIGID_NATIVE19_" + k: v for k, v in candidates["rz180_top_up"].items()},
    )
    (OUT / "power-orientation-probe.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: v["intersections"] for k, v in result["candidates"].items()}, indent=2),
        flush=True,
    )


if __name__ == "__main__":
    main()
