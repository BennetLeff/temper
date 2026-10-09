"""Check actual exported native19 solids against independent native/model anchors.

The negative control is the historical mirrored assembly, not a second formula.
"""

from __future__ import annotations

import argparse
import json

from build_integration import OUT, ROOT, bounds, read_parts, sha

REFS = ("J8", "J10", "C21", "C5")


def center(s):
    b = bounds(s)
    return [(b[i] + b[i + 3]) / 2 for i in range(3)]


def handed_volume(points):
    a, b, c, d = points
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    w = [d[i] - a[i] for i in range(3)]
    return (
        u[0] * (v[1] * w[2] - v[2] * w[1])
        - u[1] * (v[0] * w[2] - v[2] * w[0])
        + u[2] * (v[0] * w[1] - v[1] * w[0])
    )


def check(source, assembly, prefix):
    points = [center(source[k]) for k in REFS]
    actual = [center(assembly[prefix + k]) for k in REFS]
    determinant = handed_volume(actual) / handed_volume(points)
    if abs(determinant - 1) > 1e-7:
        raise AssertionError(f"actual STEP chirality determinant {determinant}, expected +1")
    for key, p, q in zip(REFS, points, actual, strict=True):
        expected = [129.5 - p[0], 162 - p[1], 30.387 + p[2]]
        assert max(abs(a - b) for a, b in zip(q, expected, strict=True)) < 1e-6, key
    # Independent pcbnew footprint centers, not centers calculated using the assembly adapter.
    for key, x in [("J8", 116.5), ("J10", 82.5)]:
        c = center(assembly[prefix + key])
        assert abs(c[0] - x) < 1e-6 and abs(c[1] - 192.5) < 1e-6, key
    assert abs(bounds(assembly[prefix + "BR1"])[2] - 32) < 1e-6
    assert bounds(assembly[prefix + "SUBSTRATE"])[5] < bounds(assembly[prefix + "BR1"])[2]
    return {
        "determinant_measured_from_four_asymmetric_model_centers": determinant,
        "references": list(REFS),
        "world_centers": actual,
        "top_side_world_normal": [0, 0, 1],
        "step_rotation_matrix": [[-1, 0, 0], [0, -1, 0], [0, 0, 1]],
        "step_translation_mm": [129.5, 162, 30.387],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default=str(OUT / "r4-supported-routed-candidate.step"))
    ap.add_argument("--prefix", default="BASE_BASE_native19_")
    a = ap.parse_args()
    p = ROOT / "output/temper-prototype-closure/pcb/temper-power-native19-candidate.step"
    native = read_parts(p)
    native = {("SUBSTRATE" if k.startswith("=>") else k): v for k, v in native.items()}
    historical = (
        ROOT
        / "output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step"
    )
    try:
        check(native, read_parts(historical), "BASE_BASE_native19_")
    except AssertionError as exc:
        negative = str(exc)
    else:
        raise AssertionError("Historical reflected negative control unexpectedly passed")
    step = __import__("pathlib").Path(a.step)
    result = check(native, read_parts(step), a.prefix)
    result.update(
        status="PASS_ACTUAL_RIGID_POWER_GEOMETRY",
        source_step_sha256=sha(p),
        assembly_path=str(step.relative_to(ROOT)),
        assembly_sha256=sha(step),
        historical_negative_control=negative,
    )
    (OUT / "power-orientation-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
