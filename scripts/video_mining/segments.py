"""Slice a video's transcript by chapter into chapters/NN-slug.md.

Primary text is the local Whisper transcript; the YouTube auto-caption text for
the same span is appended so term spellings can be cross-checked.

Usage: segments.py <video-id>
"""

import json
import os
import re
import sys
from pathlib import Path


def mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def caption_events(path: Path) -> list[tuple[float, str]]:
    if not path.exists():
        return []
    out = []
    for ev in json.loads(path.read_text()).get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs") or []).strip()
        if text:
            out.append((ev["tStartMs"] / 1000, text.replace("\n", " ")))
    return out


def main() -> None:
    vid = sys.argv[1]
    root = Path(os.environ.get("MEDIA_ROOT", Path.home() / "temper-media")) / vid
    info = json.loads((root / "video.info.json").read_text())
    chapters = info.get("chapters") or [
        {"start_time": 0, "end_time": info["duration"], "title": "full"}
    ]
    whisper = json.loads((root / "whisper" / "video.json").read_text())["segments"]
    captions = caption_events(root / "video.en.json3")

    out_dir = root / "chapters"
    out_dir.mkdir(exist_ok=True)
    for i, ch in enumerate(chapters):
        start, end = ch["start_time"], ch["end_time"]
        slug = re.sub(r"[^a-z0-9]+", "-", ch["title"].lower()).strip("-")
        lines = [f"# {ch['title']} ({mmss(start)}–{mmss(end)})", "", "## Whisper", ""]
        lines += [
            f"[{mmss(s['start'])}] {s['text'].strip()}"
            for s in whisper
            if start <= s["start"] < end
        ]
        lines += ["", "## YouTube auto-captions", ""]
        lines.append(" ".join(text for t, text in captions if start <= t < end))
        (out_dir / f"{i:02d}-{slug}.md").write_text("\n".join(lines) + "\n")
        print(f"{i:02d}-{slug}.md")


if __name__ == "__main__":
    main()
