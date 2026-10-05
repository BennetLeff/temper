"""Evaluate the wider catch-carrier alternative against the proposed R4 assembly."""

from __future__ import annotations

import json
from pathlib import Path

from build_proposal import HERE, OUT, ROOT, box, digest, export, hits, read_parts


def main() -> None:
    receipts = json.loads((OUT / "checks.json").read_text())
    baseline = next(
        row for row in receipts["exports"] if row["path"].endswith("/r4-barrier-design-only.step")
    )
    source = ROOT / baseline["path"]
    if digest(source) != baseline["sha256"]:
        raise ValueError("Barrier proposal source hash changed")
    data = json.loads((HERE / "catch-alternative.json").read_text())
    context = read_parts(source)
    components = {p["id"]: box(p["min"], p["size"]) for p in data["parts"]}
    e = data["enclosure"]
    outer = box(e["lower_min"], e["lower_size"])
    lower = outer.cut(box([17, 330, 11.5], [108, 96, 40]))
    # Keep the lid but open only the two hat interfaces; all faces are proposal shells.
    lower = lower.fuse(box([15.5, 328.5, 40], [111, 99, 1.5]))
    hats = {}
    for name, prefix in [
        ("CAP_HAT", "cap_hat"),
        ("DIODE_HAT", "diode_hat"),
        ("SENSE_HAT", "sense_hat"),
    ]:
        origin, size = e[prefix + "_min"], e[prefix + "_size"]
        inner_origin = [origin[0] + 1.5, origin[1] + 1.5, origin[2] - 2]
        inner_size = [size[0] - 3, size[1] - 3, size[2] + 0.5]
        hats[name] = box(origin, size).cut(box(inner_origin, inner_size))
        lower = lower.cut(
            box([origin[0] + 1.5, origin[1] + 1.5, 39], [size[0] - 3, size[1] - 3, 5])
        )
    front_cut = box([15, 328, 9], [112, 2, 34])
    front = lower.intersect(front_cut)
    lower = lower.cut(front_cut)
    shells = {"LOW_CARRIER_SHELL": lower, "REMOVABLE_FRONT": front, **hats}
    d = data["service_door"]
    door = {"FUSE_OPEN_PROJECTION": box(d["min"], d["size"])}
    wire = data["unfiltered_channel_replacement"]
    channel = {"RELOCATED_UNFILTERED_CHANNEL": box(wire["min"], wire["size"])}
    report = {
        "status": data["status"],
        "script_sha256": digest(Path(__file__)),
        "interface_sha256": digest(HERE / "catch-alternative.json"),
        "baseline": baseline,
        "body_vs_context": hits(components, context),
        "shell_vs_context": hits(shells, context),
        "body_vs_shell": hits(components, shells),
        "open_projection_vs_context": hits(door, context),
        "channel_vs_catch": hits(channel, components | shells),
        "channel_vs_context": hits(channel, context),
        "export": export(
            "r4-catch-alternative-design-only",
            [("BASE_", context), ("CATCH_", components), ("SHELL_", shells)],
        ),
        "limits": data["limits"]
        + [
            "Open projection checked against installed context only; remove the catch front cover first.",
            "Channel is a reservation, not a swept wire bundle.",
        ],
    }
    (OUT / "catch-alternative-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
