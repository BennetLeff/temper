"""Independently reimport the STEP and classify every new-part intersection."""

from __future__ import annotations

import hashlib
import json

from build_carrier import HERE, OUT, ROOT, hits, read_parts


def classify(a: str, b: str) -> str:
    pair = {a, b}
    if a.split("_")[0] == b.split("_")[0] and a.split("_")[0] in {f"R{i}" for i in range(1, 9)}:
        return "resistor body/coating/lead representation"
    if "BLEED_PCB" in pair and any("_LEAD_" in v for v in pair):
        return "soldered resistor lead; board laminate model omits tiny drilled holes"
    for x in ("4", "74.5"):
        if pair == {f"BLEED_PEEK_M3_{x}", f"BLEED_PEEK_NUT_{x}"}:
            return "nominal thread-major/minor overlap; thread/creep unqualified"
    for screw in pair:
        if screw.startswith("GUARD_M3_") and screw.replace("GUARD_M3_", "GUARD_PEEK_BOSS_") in pair:
            return "nominal thread-major/minor overlap; thread/creep unqualified"
    if pair == {"CATHODE_FORMED_COPPER_LINK", "DC1_PIN_2"}:
        return "proposed cathode solder contact; not pulse-qualified"
    if pair in (
        {"CC1_M4_TERMINAL_80", "HV_RET_INSULATED_WIRE_MAX"},
        {"DC1_PIN_3", "FUSED_P_TO_ANODE_INSULATED_WIRE_MAX"},
    ):
        return "unreleased terminal landing: insulation sweep retained through termination"
    for net, stud in (("BUS_P", "J8"), ("HV_RET", "J10")):
        if pair in (
            {f"{net}_INSULATED_WIRE_MAX", f"{stud}_LUG_ENVELOPE"},
            {f"{net}_INSULATED_WIRE_MAX", f"{stud}_BOOT_DESIGN"},
        ):
            return "unreleased lug/boot landing: full insulated sweep retained; exact terminal shape pending"
    return "UNCLASSIFIED"


def main() -> None:
    target = OUT / "internal-checks.json"
    target.write_text('{"status":"INCOMPLETE"}\n')
    data = json.loads((HERE / "interface.json").read_text())
    source = OUT / "r4-catch-carrier-routed-design.step"
    baseline_names = set(read_parts(ROOT / data["baseline_step"]))
    parts = {k: v for k, v in read_parts(source).items() if k not in baseline_names}
    names = sorted(parts)
    found = []
    for i, a in enumerate(names):
        for row in hits({a: parts[a]}, {b: parts[b] for b in names[i + 1 :]}):
            row["classification"] = classify(row["new"], row["context"])
            found.append(row)
    unknown = [r for r in found if r["classification"] == "UNCLASSIFIED"]
    report = {
        "status": "PASS_CLASSIFIED_CONTACTS_NOT_RELEASE"
        if not unknown
        else "UNCLASSIFIED_INTERSECTIONS",
        "step_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "new_parts_checked": len(parts),
        "pair_tests": len(parts) * (len(parts) - 1) // 2,
        "method": "All unique new-part pairs after STEP reimport; AABB broad phase then OCC solid intersection; >1e-5 mm3 threshold.",
        "contacts": found,
        "unclassified": unknown,
        "limits": "Insulation sweeps through terminal landings remain explicit holds. Nominal CAD does not prove tolerance, insulation, pulse, loads or supplier fit.",
    }
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "unclassified": unknown}, indent=2))
    if unknown:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
