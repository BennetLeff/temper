"""Merge per-agent triage verdicts (frames/triage/verdicts_*.jsonl) with
frames/index.csv into frames/triage/verdicts.csv, and fail loudly on frames
that were scored twice, never scored, or scored under an id not in the index
(a misread stamp).

Usage: merge_triage.py <video-id>
"""

import csv
import json
import os
import sys
from pathlib import Path


def main() -> None:
    vid = sys.argv[1]
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    with open(root / "frames" / "index.csv") as f:
        index = {Path(r["frame"]).stem: r for r in csv.DictReader(f)}

    verdicts: dict[str, dict] = {}
    dupes, unknown = [], []
    for path in sorted((root / "frames" / "triage").glob("verdicts_*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            v = json.loads(line)
            fid = v["frame"]
            if fid not in index:
                unknown.append(fid)
            elif fid in verdicts:
                dupes.append(fid)
            else:
                verdicts[fid] = v
    missing = sorted(set(index) - set(verdicts))

    fields = ["frame", "mmss", "chapter", "pcb_score", "engineering_score", "category", "what"]
    with open(root / "frames" / "triage" / "verdicts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for fid, row in index.items():
            v = verdicts.get(fid, {})
            w.writerow({
                "frame": fid,
                "mmss": row["mmss"],
                "chapter": row["chapter"],
                "pcb_score": v.get("pcb_score", ""),
                "engineering_score": v.get("engineering_score", ""),
                "category": v.get("category", ""),
                "what": v.get("what", ""),
            })

    # Shortlist for 4K inspection: any visible board, plus close non-PCB hardware.
    shortlist = [
        fid
        for fid in index
        if verdicts.get(fid, {}).get("pcb_score", 0) >= 2
        or verdicts.get(fid, {}).get("engineering_score", 0) == 3
    ]
    (root / "frames" / "triage" / "shortlist.txt").write_text("\n".join(shortlist) + "\n")
    print(f"shortlist (pcb>=2 or engineering==3): {len(shortlist)}")

    for s in (3, 2, 1, 0):
        print(f"pcb_score {s}: {sum(1 for v in verdicts.values() if v.get('pcb_score') == s)}")
    print(f"scored {len(verdicts)}/{len(index)}; missing {len(missing)}; dupes {len(dupes)}; unknown ids {unknown}")
    if missing:
        print("missing:", " ".join(missing))


if __name__ == "__main__":
    main()
