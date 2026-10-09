"""Fail closed on stale inputs, failed STEP readback, overlaps, or a reflected placement."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = json.loads((OUT / "geometry-receipt.json").read_text())
    native = json.loads((OUT / "native-capture.json").read_text())
    assert receipt["native_capture_sha256"] == digest(OUT / "native-capture.json")
    for item in [*receipt["sources"].values(), *receipt["exports"].values()]:
        assert digest(ROOT / item["path"]) == item["sha256"], item["path"]
    for name, item in native.items():
        assert digest(ROOT / item["source"]) == item["sha256"], name
        assert digest(ROOT / item["step"]["path"]) == item["step"]["sha256"], name
    model_paths = {}
    for item in native.values():
        for footprint in item["footprints"]:
            for model in footprint["models"]:
                if model["exists"]:
                    model_paths[model["resolved"]] = model["sha256"]
    for path, expected in model_paths.items():
        assert digest(Path(path)) == expected, path
    assert all(item["valid"] for item in receipt["exports"].values())
    checks = json.loads((OUT / "integration-checks.json").read_text())
    assert not any(rows for space in checks.values() for rows in space.values()), checks
    # Asymmetric probe compares declared native-pad transformation to actual CAD rigid transform.
    import cadquery as cq
    from build_integration import PLACEMENTS, bounds, point, read_parts, tf
    from check_power_orientation import handed_volume

    assemblies = {k: read_parts(ROOT / r["path"]) for k, r in receipt["exports"].items()}
    placement_results = {}
    expected_normals = {
        "front": [0, -1, 0],
        "inward_reverse": [-1, 0, 0],
        "flat": [0, 0, 1],
        "reverse": [0, 0, 1],
    }
    for name, (space, rot, xyz) in PLACEMENTS.items():
        probe = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        actual_basis = [
            list(tf(cq.Vertex.makeVertex(*p), rot, xyz).Center().toTuple()) for p in probe
        ]
        determinant = handed_volume(actual_basis)
        normal = [actual_basis[3][i] - actual_basis[0][i] for i in range(3)]
        assert abs(determinant - 1) < 1e-7, name
        assert max(abs(a - b) for a, b in zip(normal, expected_normals[rot], strict=True)) < 1e-7, (
            name
        )
        p = [10.0, -4.0, 2.0]
        measured = tf(cq.Vertex.makeVertex(*p), rot, xyz).Center().toTuple()
        assert max(abs(a - b) for a, b in zip(measured, point(p, rot, xyz), strict=True)) < 1e-6, (
            name
        )
        # Inspect every actual exported native model, not just the transformation
        # helper. A metadata-only edit cannot make a reflected export pass.
        checked = 0
        for ref, shape in read_parts(OUT / "boards" / (name + ".step")).items():
            key = (
                (name + "_" + ref)
                .replace("=>", "BOARD")
                .replace(":", "_")
                .replace("[", "_")
                .replace("]", "_")
            )
            actual = assemblies[space][key]
            sb = bounds(shape)
            ab = bounds(actual)
            expected = point([(sb[i] + sb[i + 3]) / 2 for i in range(3)], rot, xyz)
            assert max(abs(expected[i] - (ab[i] + ab[i + 3]) / 2) for i in range(3)) < 2e-5, (
                name,
                ref,
            )
            assert abs(actual.Volume() - shape.Volume()) < max(1e-5, abs(shape.Volume()) * 1e-7), (
                name,
                ref,
            )
            checked += 1
        placement_results[name] = {
            "actual_model_count": checked,
            "determinant": determinant,
            "component_normal": normal,
            "source_sha256": native[name]["sha256"],
            "assembly_sha256": receipt["exports"][space]["sha256"],
        }
    (OUT / "native-nine-placement-verification.json").write_text(
        json.dumps(placement_results, indent=2) + "\n"
    )
    from check_power_orientation import check

    source = read_parts(
        ROOT / "output/temper-prototype-closure/pcb/temper-power-native19-candidate.step"
    )
    source = {("SUBSTRATE" if k.startswith("=>") else k): v for k, v in source.items()}
    check(source, read_parts(ROOT / receipt["exports"]["r4"]["path"]), "BASE_BASE_native19_")
    assert receipt["rigid_power_installation_sha256"] == digest(
        OUT / "rigid-power-installation.json"
    )
    for item in json.loads((OUT / "rigid-power-installation.json").read_text())["cooling_sources"]:
        assert digest(ROOT / item["path"]) == item["sha256"], item["path"]
    print(
        "PASS: nine board/source identities, STEP validity, thirteen empty interference sets, nine rigid transforms plus actual native19 solid chirality"
    )


if __name__ == "__main__":
    main()
