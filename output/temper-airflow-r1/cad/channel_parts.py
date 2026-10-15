#!/usr/bin/env python3
"""What sits under the jet box on the board of record (s42, codex/power-stage-integration c8665ceb0).

    python3 channel_parts.py      -> channel-parts.json

R43's native-21 envelope is the stage-13 STEP, older than s42, so fit_check.py's 1.2 mm / 6.0 mm gaps are checked here
against s42's own placement (native-21/placement.json, model frame) and footprints (native-21/frozen/default.csv), read
from git objects. The jet box floor is 6.0 mm above the board over model x 1-88, y 10.5-22.5; the gate is that every
part centred in x -2..92, y 6..25 is an SMD package (body height <= 2.5 mm by package class) apart from the TO-247s and
the film caps that bound the channel.
"""
import csv
import io
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[2] / "worktrees/ps-integrate"
COMMIT = "c8665ceb09c756582797fb3279d7a3db468ad0bc"
SMD = ("R_0402", "R_0603", "R_0805", "R_1206", "R_2512", "C_0402", "C_0603", "C_0805", "C_1206", "C_1210", "SOD-128",
       "D_SOD", "R_Shunt_Bourns_CSS2H-2512")
BOUNDING = ("TO-247", "B32652")


def show(path):
    return subprocess.run(["git", "-C", str(PS), "show", f"{COMMIT}:{path}"], capture_output=True, text=True, check=True).stdout


def main():
    place = json.loads(show("zapote/power-stage-120v/native-21/placement.json"))
    fps = {}
    for row in csv.DictReader(io.StringIO(show("zapote/power-stage-120v/native-21/frozen/default.csv"))):
        for d in row["Designator"].split(","):
            fps[d.strip()] = (row["Comment"], row["Footprint"])
    src = show("zapote/power-stage-120v/elec/src/power_stage_120v.ato")
    desig = {}
    for line in src.splitlines():
        line = line.strip()
        if ".designator = " in line:
            k, v = line.split(".designator = ")
            desig[k.strip()] = v.strip().strip('"')
    rows = []
    for name, at in place.items():
        x, y = at[:2]
        if -2 <= x <= 92 and 6 <= y <= 25:
            ref = desig.get(name, "?")
            mpn, fp = fps.get(ref, ("?", "?"))
            cls = "SMD" if any(s in fp for s in SMD) else ("bounding" if any(s in fp or s in mpn for s in BOUNDING) else "CHECK")
            rows.append({"name": name, "ref": ref, "at_model": at, "mpn": mpn, "footprint": fp, "class": cls})
    out = {"scope": __doc__.strip(), "commit": COMMIT, "parts": rows,
           "status": "PASS" if all(r["class"] != "CHECK" for r in rows) else "CHECK"}
    (HERE / "channel-parts.json").write_text(json.dumps(out, indent=1) + "\n")
    print(out["status"], [(r["ref"], r["footprint"].split(":")[-1], r["class"]) for r in rows])


if __name__ == "__main__":
    main()
