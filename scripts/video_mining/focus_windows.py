"""Dense re-sampling of focus windows for subject-specific triage.

For each window in windows/<video-id>.txt: decode the 1080p proxy at FPS,
keep the sharpest frame per 1/KEEP_PER_S seconds, and name it by timestamp.
Then pack each subject's frames into labelled 3x3 grids (same format as
triage_grids.py) for a subject-specific model pass.

Outputs under frames/focus/<subject>/: f<seconds>.jpg, grid_NNN.jpg.

Usage: focus_windows.py <video-id> [fps] [keep-per-s]
"""

import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TILE_W, TILE_H = 427, 240


def sharpness(path: Path) -> float:
    im = Image.open(path).convert("L").resize((960, 540))
    return float(np.asarray(im.filter(ImageFilter.FIND_EDGES), dtype=float).var())


def main() -> None:
    vid = sys.argv[1]
    fps = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    keep_per_s = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    spec = Path(__file__).parent / "windows" / f"{vid}.txt"
    out_root = root / "frames" / "focus"
    if out_root.exists():
        shutil.rmtree(out_root)

    by_subject: dict[str, list[Path]] = defaultdict(list)
    for line in spec.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        subject, start, end = line.split()[:3]
        start, end = float(start), float(end)
        out = out_root / subject
        out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-hwaccel", "videotoolbox",
                 "-ss", str(start), "-to", str(end), "-i", str(root / "proxy.mp4"),
                 "-vf", f"fps={fps}", "-q:v", "2", "-start_number", "0", f"{tmp}/%05d.jpg"],
                check=True,
            )
            buckets: dict[int, list[tuple[float, Path]]] = defaultdict(list)
            for p in sorted(Path(tmp).glob("*.jpg")):
                t = start + int(p.stem) / fps
                buckets[int(t * keep_per_s)].append((t, p))
            for frames in buckets.values():
                t, best = max(frames, key=lambda f: sharpness(f[1]))
                dest = out / f"f{t:07.2f}.jpg"
                shutil.copy2(best, dest)
                by_subject[subject].append(dest)

    font = ImageFont.load_default(size=26)
    for subject, frames in by_subject.items():
        frames = sorted(set(frames))
        for g in range(0, len(frames), 9):
            grid = Image.new("RGB", (3 * TILE_W, 3 * TILE_H), "black")
            draw = ImageDraw.Draw(grid)
            for i, p in enumerate(frames[g : g + 9]):
                x, y = (i % 3) * TILE_W, (i // 3) * TILE_H
                grid.paste(Image.open(p).resize((TILE_W, TILE_H)), (x, y))
                draw.rectangle((x, y, x + 150, y + 34), fill="black")
                draw.text((x + 6, y + 3), p.stem, fill="yellow", font=font)
            grid.save(out_root / subject / f"grid_{g // 9:03d}.jpg", quality=85)
        print(f"{subject}: {len(frames)} frames, {-(-len(frames) // 9)} grids")


if __name__ == "__main__":
    main()
