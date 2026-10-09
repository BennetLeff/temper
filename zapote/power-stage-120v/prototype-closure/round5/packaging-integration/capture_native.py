"""Read-only pcbnew capture of actual nine-board placement and model identity."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pcbnew as pcb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BOARDS = HERE.parent / "boards"
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
MODEL_ROOT = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(p):
    return [pcb.ToMM(p.x), pcb.ToMM(p.y)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "boards").mkdir(exist_ok=True)
    items = {"central": BOARDS / "central/native/supervisor.kicad_pcb"}
    items.update(
        {
            k: BOARDS / f"native/{k}-sensor/{k}-sensor.kicad_pcb"
            for k in ["catch", "bus", "line", "pre", "out", "tank", "iproof", "iline"]
        }
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=list(items), action="append")
    selected = parser.parse_args().only
    previous = OUT / "native-capture.json"
    result = json.loads(previous.read_text()) if selected and previous.exists() else {}
    for key, source in items.items():
        if selected and key not in selected:
            continue
        before = sha(source)
        b = pcb.LoadBoard(str(source))
        e = b.GetBoardEdgesBoundingBox()
        entry = {
            "source": str(source.relative_to(ROOT)),
            "sha256": before,
            "outline_bbox": [*point(e.GetPosition()), *point(e.GetEnd())],
            "thickness_mm": pcb.ToMM(b.GetDesignSettings().GetBoardThickness()),
            "footprints": [],
            "mounts": [],
        }
        for fp in b.GetFootprints():
            row = {
                "ref": fp.GetReference(),
                "value": fp.GetValue(),
                "footprint": str(fp.GetFPID().GetLibItemName()),
                "position": point(fp.GetPosition()),
                "angle_deg": fp.GetOrientationDegrees(),
                "side": "B" if fp.IsFlipped() else "F",
                "pads": [],
                "models": [],
            }
            for p in fp.Pads():
                pad = {
                    "pin": p.GetNumber(),
                    "xy": point(p.GetPosition()),
                    "drill": point(p.GetDrillSize()),
                    "size": point(p.GetSize()),
                    "net": p.GetNetname(),
                }
                row["pads"].append(pad)
                if p.GetAttribute() == pcb.PAD_ATTRIB_NPTH and max(pad["drill"]) >= 2.5:
                    entry["mounts"].append({"ref": fp.GetReference(), **pad})
            for model in fp.Models():
                raw = model.m_Filename
                resolved = Path(
                    raw.replace("${KICAD10_3DMODEL_DIR}", MODEL_ROOT).replace(
                        "${KIPRJMOD}", str(source.parent)
                    )
                )
                row["models"].append(
                    {
                        "path": raw,
                        "resolved": str(resolved),
                        "exists": resolved.exists(),
                        "sha256": sha(resolved) if resolved.is_file() else None,
                    }
                )
            entry["footprints"].append(row)
        target = OUT / "boards" / f"{key}.step"
        command = [
            CLI,
            "pcb",
            "export",
            "step",
            "--force",
            "--subst-models",
            "--no-dnp",
            "--user-origin",
            "0x0mm",
            "-o",
            str(target),
            str(source),
        ]
        proc = subprocess.run(command, capture_output=True, text=True)
        (OUT / "boards" / f"{key}-export.log").write_text(proc.stdout + proc.stderr)
        if proc.returncode or not target.exists() or sha(source) != before:
            raise RuntimeError(f"Export or source identity failed: {key}")
        entry["step"] = {"path": str(target.relative_to(ROOT)), "sha256": sha(target)}
        result[key] = entry
    (OUT / "native-capture.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: {"parts": len(v["footprints"]), "mounts": v["mounts"], "sha256": v["sha256"]}
                for k, v in result.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
