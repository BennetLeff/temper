"""Turn a yt-dlp json3 caption file into "[mm:ss] text" lines (one per event).

Usage: captions_to_text.py <media-dir>   -> <media-dir>/captions.txt
"""

import json
import sys
from pathlib import Path


def main() -> None:
    d = Path(sys.argv[1])
    files = sorted(d.glob("video.en*.json3"), key=lambda p: (".en-orig" not in p.name, len(p.name)))
    if not files:
        sys.exit(1)
    ev = json.loads(files[0].read_text())["events"]
    lines = []
    for e in ev:
        text = "".join(s.get("utf8", "") for s in e.get("segs", [])).strip()
        if text:
            t = e.get("tStartMs", 0) / 1000
            lines.append(f"[{int(t // 60):02d}:{int(t % 60):02d}] {text}")
    info = d / "video.info.json"
    title = json.loads(info.read_text()).get("title", "") if info.exists() else d.name
    (d / "captions.txt").write_text(f"# {title}\n" + "\n".join(lines) + "\n")
    print(d.name, len(lines), "lines", title)


if __name__ == "__main__":
    main()
