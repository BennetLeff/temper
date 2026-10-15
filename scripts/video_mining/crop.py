"""Crop and upscale a region of a 4K still for close reading.

Regions are given in DISPLAY coordinates of a 2000-px-wide preview (the scale
the frames are reviewed at); they are mapped to the 3840x2160 source. Output
goes under $MEDIA_ROOT/<video-id>/frames/crops/ (never into the repo).

Usage: crop.py <video-id> <frame-path-or-seconds> <x0> <y0> <x1> <y1> <name> [scale]
  frame: a jpg path, or a time in seconds (grabbed from video.mkv at full res)
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter

DISPLAY_W = 2000


def main() -> None:
    vid, frame, *box, name = sys.argv[1:8]
    scale = float(sys.argv[8]) if len(sys.argv) > 8 else 2.0
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    out = root / "frames" / "crops"
    out.mkdir(parents=True, exist_ok=True)
    if Path(frame).exists():
        im = Image.open(frame)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.png"
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", frame,
                            "-i", str(root / "video.mkv"), "-frames:v", "1", str(p)], check=True)
            im = Image.open(p).copy()
    k = im.width / DISPLAY_W
    x0, y0, x1, y1 = (round(float(v) * k) for v in box)
    c = im.crop((x0, y0, x1, y1))
    c = c.resize((round(c.width * scale), round(c.height * scale)), Image.LANCZOS)
    c = c.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))
    dest = out / f"{name}.png"
    c.save(dest)
    print(dest, c.size, "source px", (x0, y0, x1, y1))


if __name__ == "__main__":
    main()
