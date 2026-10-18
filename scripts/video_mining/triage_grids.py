"""Pack kept frames into small labelled grids for cheap model triage.

Each grid holds ROWS x COLS downsampled frames; each tile is stamped with its
frame id (the keep/ filename stem, e.g. t01475.0) in large type so a small
vision model can report per-frame verdicts by id. Tile size keeps the whole
346-frame set near 110k image tokens.

Usage: triage_grids.py <video-id> [cols] [rows] [tile-width]
"""

import csv
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    vid = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    tile_w = int(sys.argv[4]) if len(sys.argv) > 4 else 427
    tile_h = tile_w * 9 // 16
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    out = root / "frames" / "triage"
    out.mkdir(exist_ok=True)
    font = ImageFont.load_default(size=26)

    with open(root / "frames" / "index.csv") as f:
        frames = [r["frame"] for r in csv.DictReader(f)]

    per = cols * rows
    for g in range(0, len(frames), per):
        batch = frames[g : g + per]
        grid = Image.new("RGB", (cols * tile_w, rows * tile_h), "black")
        draw = ImageDraw.Draw(grid)
        for i, name in enumerate(batch):
            im = Image.open(root / "frames" / "keep" / name).resize((tile_w, tile_h))
            x, y = (i % cols) * tile_w, (i // cols) * tile_h
            grid.paste(im, (x, y))
            label = Path(name).stem
            draw.rectangle((x, y, x + 150, y + 34), fill="black")
            draw.text((x + 6, y + 3), label, fill="yellow", font=font)
        grid.save(out / f"grid_{g // per:03d}.jpg", quality=85)
    print(f"{len(frames)} frames -> {-(-len(frames) // per)} grids in {out}")


if __name__ == "__main__":
    main()
