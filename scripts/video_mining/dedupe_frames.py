"""Collapse raw frames to a distinct, readable set indexed by timestamp + chapter.

Handheld teardown footage defeats plain perceptual-hash dedupe: the camera
never stops moving, so a 16x16 pHash at any useful threshold still keeps
~40 % of 1 fps frames (measured on Sue70X7ZeS0: 2413 -> 923 at distance 80).
Instead:

1. Within each STRIDE-second bucket keep only the sharpest frame (variance of
   an edge filter) -- the moment the camera holds still on a board.
2. Drop a pick whose 8x8 dHash is within MIN_DIST bits of any pick kept in
   the preceding WINDOW seconds.

Scene-cut frames are always kept: they mark a deliberate shot change.

Usage: dedupe_frames.py <video-id> [stride-s] [min-dist] [window-s]
"""

import csv
import json
import os
import shutil
import sys
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageFilter


def sharpness(im: Image.Image) -> float:
    return float(np.asarray(im.filter(ImageFilter.FIND_EDGES), dtype=float).var())


def main() -> None:
    vid = sys.argv[1]
    stride = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    min_dist = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    window = float(sys.argv[4]) if len(sys.argv) > 4 else 90.0
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    raw = root / "frames" / "raw"
    keep = root / "frames" / "keep"
    if keep.exists():
        shutil.rmtree(keep)
    keep.mkdir(parents=True)

    dense_start = float((raw / "dense_start.txt").read_text())
    dense = []
    for p in sorted(raw.glob("dense_*.jpg")):
        im = Image.open(p).convert("L").resize((960, 540))
        t = dense_start + int(p.stem.split("_")[1])
        dense.append((t, p, sharpness(im), imagehash.dhash(im, hash_size=8)))

    picks = [
        max(dense[s : s + stride], key=lambda f: f[2]) for s in range(0, len(dense), stride)
    ]
    kept: list[tuple[float, Path, imagehash.ImageHash]] = []
    for t, p, _, h in picks:
        if any(t - kt <= window and h - kh <= min_dist for kt, _, kh in kept):
            continue
        kept.append((t, p, h))

    scene_times = (raw / "scene_times.txt").read_text().split()
    selected = [(t, p) for t, p, _ in kept] + [
        (float(t), raw / f"scene_{i:05d}.jpg") for i, t in enumerate(scene_times, start=1)
    ]
    selected.sort()

    info = json.loads((root / "video.info.json").read_text())
    chapters = info.get("chapters") or []

    def chapter_of(t: float) -> str:
        for ch in chapters:
            if ch["start_time"] <= t < ch["end_time"]:
                return ch["title"]
        return ""

    rows = []
    for t, path in selected:
        name = f"t{t:07.1f}.jpg"
        shutil.copy2(path, keep / name)
        rows.append((name, f"{t:.1f}", f"{int(t // 60):02d}:{t % 60:04.1f}", chapter_of(t), path.name))

    with open(root / "frames" / "index.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "seconds", "mmss", "chapter", "source"])
        w.writerows(rows)
    print(f"{len(dense)} dense -> {len(picks)} sharpest -> {len(kept)} distinct (+{len(scene_times)} scene cuts)")


if __name__ == "__main__":
    main()
