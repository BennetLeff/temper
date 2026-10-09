"""Emit review inventories from native board and source tables, without design edits."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pcbnew as pcb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/boards"


def read(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def main():
    tables = {"central": HERE / "central/generated/pins.tsv"}
    tables.update(
        {
            n: HERE / (n + "-pins.tsv")
            for n in ["catch", "bus", "line", "pre", "out", "tank", "iproof", "iline"]
        }
    )
    census = {}
    connectors = {}
    boards = {}
    bom = []
    for name, table in tables.items():
        rows = read(table)
        parts = {r["reference"]: r for r in rows}
        census[name] = dict(sorted(Counter(r["mpn"] for r in parts.values()).items()))
        for ref, r in parts.items():
            bom.append(
                {
                    "board": name,
                    "reference": ref,
                    "source_ref": r.get("source_ref", ""),
                    "mpn": r["mpn"],
                    "footprint": r["footprint"],
                }
            )
        path = HERE / (
            "central/native/supervisor.kicad_pcb"
            if name == "central"
            else f"native/{name}-sensor/{name}-sensor.kicad_pcb"
        )
        b = pcb.LoadBoard(str(path))
        models = []
        missing = []
        for fp in b.GetFootprints():
            if fp.GetReference().startswith("H"):
                continue
            mm = list(fp.Models())
            if not mm:
                missing.append(
                    {
                        "reference": fp.GetReference(),
                        "reason": "No 3D body/lead/harness model supplied",
                    }
                )
            for m in mm:
                resolved = Path(
                    m.m_Filename.replace(
                        "${KICAD10_3DMODEL_DIR}",
                        "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels",
                    )
                )
                models.append(
                    {
                        "reference": fp.GetReference(),
                        "model": m.m_Filename,
                        "resolved_on_host": resolved.is_file(),
                    }
                )
        netlength = defaultdict(float)
        for t in b.GetTracks():
            if not isinstance(t, pcb.PCB_VIA):
                netlength[t.GetNetname()] += pcb.ToMM(t.GetLength())
        boards[name] = {
            "board_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "electrical_parts": len(parts),
            "copper_layers": b.GetCopperLayerCount(),
            "tracks_and_vias": len(b.GetTracks()),
            "net_total_copper_length_mm": dict(sorted(netlength.items())),
            "model_references": models,
            "missing_models": missing,
            "model_collision_review_complete": False,
        }
        pp = []
        for r in rows:
            if not r["reference"].startswith("J"):
                continue
            net = r["net"]
            source = r.get("source_ref", r["reference"])
            domain = (
                "CTRL"
                if net.startswith("CTRL_") or net in ["SUP_RUN_OK", "NATIVE_PERMIT"]
                else "AUX"
                if name == "central" or r["reference"] != "J1" or name in ["iproof", "iline"]
                else "HV_INPUT"
            )
            if net == "NC":
                direction = "no_connect"
            elif net in ["AUX_0V", "CTRL_GND"]:
                direction = "return"
            elif name != "central":
                direction = (
                    "power_in"
                    if net == "POD_3V3"
                    else "analog_reference"
                    if net == "REF_1V25"
                    else "output"
                    if r["reference"] == "J2" or name in ["iproof", "iline"]
                    else "input"
                )
            elif net == "CTRL_3V3" or source == "J_AUX24" or net == "POD_5V":
                direction = "power_in"
            elif net in ["POD_3V3", "AUX_24V", "POD_24V_ACT"]:
                direction = "power_out"
            elif net == "SWDIO":
                direction = "bidirectional"
            elif source == "J_CLK" and net == "ADC_CLKIN":
                direction = "output_monitor_no_external_driver"
            elif net.endswith("_MIRROR_24V"):
                direction = "input_24V_wetted_contact"
            elif (
                net
                in [
                    "ADC_CLKIN",
                    "SWCLK",
                    "WD_RESET_N",
                    "CTRL_PWM_REQUEST",
                    "CTRL_HEARTBEAT",
                    "CTRL_FAULT_HIGH",
                    "CTRL_TX",
                    "CTRL_RAIL_OK",
                    "CTRL_INTERLOCK_OK",
                ]
                or net.endswith(("_RAW", "_DIAG_N", "_TEMP"))
                or source.startswith("J_V")
                or source == "J_CATCH_POD"
            ):
                direction = "input"
            elif net == "REF_1V25":
                direction = "analog_reference_out"
            else:
                direction = "output"
            pp.append(
                {
                    "connector": r["reference"],
                    "source_ref": source,
                    "pin": r["pin"],
                    "net": net,
                    "domain": domain,
                    "direction_from_board": direction,
                    "mpn": r["mpn"],
                }
            )
        connectors[name] = pp
    (HERE / "component-census.json").write_text(json.dumps(census, indent=2) + "\n")
    (HERE / "connector-map.json").write_text(
        json.dumps(
            {
                "version": "R5-boards-1",
                "authority": "Actual source-derived pin tables; board viewpoints, not mating-face drawings",
                "connectors": connectors,
            },
            indent=2,
        )
        + "\n"
    )
    (OUT / "physical-inventory.json").write_text(json.dumps(boards, indent=2) + "\n")
    with (HERE / "board-bom.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(bom[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(bom)
    print("Inventoried", len(boards), "boards,", len(bom), "electrical components")


if __name__ == "__main__":
    main()
