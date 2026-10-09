"""Hash the review package without upgrading a stale native checkpoint."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cap = json.loads((OUT / "native-capture.json").read_text())
    stale = [name for name, r in cap.items() if sha(ROOT / r["source"]) != r["sha256"]]
    vp = OUT / "installation-verification.json"
    v = json.loads(vp.read_text()) if vp.exists() else {}
    current = (
        v.get("status") == "PASS"
        and v.get("native_capture_sha256") == sha(OUT / "native-capture.json")
        and not stale
    )
    if current:
        current = v["support_receipt_sha256"] == sha(OUT / "support-receipt.json") and v[
            "harness_receipt_sha256"
        ] == sha(OUT / "harness-receipt.json")
    files = [
        p
        for p in sorted(HERE.iterdir())
        if p.suffix in (".py", ".md", ".json") and p.name != "checkpoint.json"
    ]
    outputs = [
        "r4-supported-routed-candidate.step",
        "pod-supported-integration-candidate.step",
        "candidate-drilled-floor.step",
        "temper-installation-review.pdf",
        "native-capture.json",
        "native-pickoffs.json",
        "geometry-receipt.json",
        "support-receipt.json",
        "harness-receipt.json",
        "integration-checks.json",
        "support-checks.json",
        "harness-checks.json",
        "critical-clearances.json",
        "support-critical-distances.json",
        "harness-mechanical-margins.json",
        "support-patterns.json",
        "harness-probe.json",
        "installation-coordinates.json",
        "support-harness-installation.svg",
        "support-harness-installation.png",
        "installation-verification.json",
        "power-orientation-probe.json",
        "power-orientation-verification.json",
        "floor-drilling-manifest.json",
        "native-nine-placement-verification.json",
        "rigid-power-installation.json",
        "rigid-rz180-coordinates.json",
        "orientation-native-oracle.json",
        "r4-rigid-power-orientation-PROBE-NOT-FIT.step",
    ]
    orientation = json.loads((OUT / "power-orientation-verification.json").read_text())
    d = {
        "status": "MATCHING_NATIVE_DIGITAL_CANDIDATE_QUALIFICATION_HOLDS_REMAIN"
        if current
        else "SUPPORT_ROUTE_CANDIDATE_COMPLETE_FINAL_NATIVE_RECAPTURE_PENDING",
        "power_geometry_status": orientation["status"],
        "native_sources_changed_since_capture": stale,
        "native_capture_sha256": sha(OUT / "native-capture.json"),
        "native": {k: r["sha256"] for k, r in cap.items()},
        "source_files": {str(p.relative_to(ROOT)): sha(p) for p in files},
        "outputs": {
            str((OUT / n).relative_to(ROOT)): sha(OUT / n) for n in outputs if (OUT / n).exists()
        },
        "limits": "No fabrication or powered-build release. Native-pad solder tails/boots/end restraints, tube grip/hot deflection, sensing electrical performance, materials and insulation qualification remain required. Canonical housing and source boards unchanged by this packaging task.",
    }
    if orientation["status"] != "PASS_ACTUAL_RIGID_POWER_GEOMETRY":
        d["status"] = orientation["status"]
    (HERE / "checkpoint.json").write_text(json.dumps(d, indent=2) + "\n")
    print(d["status"])
    print("Stale native captures:", stale)


if __name__ == "__main__":
    main()
