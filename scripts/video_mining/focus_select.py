"""Pick the best focus-window frames per subject and re-grab them at 4K.

Reads frames/focus/verdicts_*.jsonl ({frame, subject, score, view, blur}),
normalises ids (models sometimes drop the zero padding of the stamp), ranks
by score then sharpness-proxy order, enforces MIN_GAP seconds between picks
so the set is not one moment repeated, and extracts each pick from video.mkv
into frames/focus/best4k/<subject>_f<seconds>.jpg. Writes best.csv.

Usage: focus_select.py <video-id> [per-subject] [min-gap-s]
"""

import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    vid = sys.argv[1]
    per_subject = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    min_gap = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    focus = root / "frames" / "focus"
    out = focus / "best4k"
    out.mkdir(exist_ok=True)

    rows: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(focus.glob("verdicts_*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                v = json.loads(line)
                v["t"] = float(v["frame"].lstrip("f"))
                if not (focus / v["subject"] / f"f{v['t']:07.2f}.jpg").exists():
                    print(f"warning: no source frame for {v['frame']} ({v['subject']})")
                    continue
                rows[v["subject"]].append(v)

    picks = []
    for subject, vs in rows.items():
        chosen: list[dict] = []
        for v in sorted(vs, key=lambda v: (-v["score"], bool(v.get("blur")), v["t"])):
            if v["score"] < 2 or len(chosen) == per_subject:
                break
            if all(abs(v["t"] - c["t"]) >= min_gap for c in chosen):
                chosen.append(v)
        picks += sorted(chosen, key=lambda v: v["t"])

    for v in picks:
        dest = out / f"{v['subject']}_f{v['t']:07.2f}.jpg"
        if not dest.exists():
            subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{v['t']:.3f}",
                 "-i", str(root / "video.mkv"), "-frames:v", "1", "-q:v", "2", str(dest)],
                check=True,
            )
    with open(focus / "best.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "subject", "seconds", "mmss", "score", "view"])
        for v in picks:
            w.writerow([f"{v['subject']}_f{v['t']:07.2f}.jpg", v["subject"], f"{v['t']:.2f}",
                        f"{int(v['t'] // 60):02d}:{v['t'] % 60:05.2f}", v["score"], v["view"]])
    for subject in rows:
        print(subject, sum(1 for v in picks if v["subject"] == subject), "picks")


if __name__ == "__main__":
    main()
