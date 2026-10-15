"""One contact sheet per chapter from frames/keep, each thumbnail labelled
with its timestamp, so a reader can triage which 4K stills to open.

Usage: contact_sheets.py <video-id> [columns]
"""

import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

THUMB_W, THUMB_H = 480, 270


def main() -> None:
    vid = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    out = root / "frames" / "sheets"
    out.mkdir(exist_ok=True)

    by_chapter: dict[str, list[dict]] = defaultdict(list)
    with open(root / "frames" / "index.csv") as f:
        for row in csv.DictReader(f):
            by_chapter[row["chapter"]].append(row)

    for n, (chapter, rows) in enumerate(by_chapter.items()):
        nrows = -(-len(rows) // cols)
        sheet = Image.new("RGB", (cols * THUMB_W, nrows * THUMB_H), "black")
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(rows):
            im = Image.open(root / "frames" / "keep" / row["frame"]).resize((THUMB_W, THUMB_H))
            x, y = (i % cols) * THUMB_W, (i // cols) * THUMB_H
            sheet.paste(im, (x, y))
            draw.rectangle((x, y, x + 120, y + 22), fill="black")
            draw.text((x + 4, y + 4), f"{row['mmss']}  {row['seconds']}s", fill="yellow")
        slug = re.sub(r"[^a-z0-9]+", "-", chapter.lower()).strip("-") or "untitled"
        sheet.save(out / f"{n:02d}-{slug}.jpg", quality=85)
        print(f"{n:02d}-{slug}.jpg  {len(rows)} frames")


if __name__ == "__main__":
    main()
