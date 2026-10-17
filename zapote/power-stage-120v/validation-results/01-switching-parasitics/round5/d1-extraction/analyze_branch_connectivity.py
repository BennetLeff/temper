#!/usr/bin/env python3
"""Summarize same-layer endpoint connectivity in candidate grid audits.

The result is deliberately incomplete: plated barrels and component terminals
need a separate three-dimensional landing proof before a field solve.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    ports = json.loads((HERE / "port-map.json").read_text())
    reports = []
    for path in sorted(HERE.glob("link-audit-*.json")):
        data = json.loads(path.read_text())
        layers = {(row["net"], row["layer"]): row for row in data["net_layers"]}
        branches = []
        for port in ports["legs"][data["leg"]]:
            matches = []
            for layer in set(port["from_layers"]) & set(port["to_layers"]):
                row = layers.get((port["net"], layer))
                if row is None:
                    continue
                pads = {p["ref"]: set(p["component_ids_20um"]) for p in row["port_pad_coverage"]}
                shared = pads.get(port["from_ref"], set()) & pads.get(port["to_ref"], set())
                matches.append({"layer": layer, "same_component": bool(shared),
                                "from_component_count": len(pads.get(port["from_ref"], set())),
                                "to_component_count": len(pads.get(port["to_ref"], set()))})
            branches.append({"name": port["name"], "from_ref": port["from_ref"],
                             "to_ref": port["to_ref"], "same_layer_checks": matches,
                             "any_same_layer_connection": any(m["same_component"] for m in matches)})
        reports.append({"link_audit": path.name, "leg": data["leg"],
                        "margin_mm": data["margin_mm"], "pitch_mm": data["pitch_mm"],
                        "status": "SAME_LAYER_ONLY_NO_BARRELS", "branches": branches})
    (HERE / "branch-connectivity.json").write_text(json.dumps(reports, indent=2) + "\n")
    for report in reports:
        print(report["link_audit"], ", ".join(b["name"] for b in report["branches"] if not b["any_same_layer_connection"]))


if __name__ == "__main__":
    main()
