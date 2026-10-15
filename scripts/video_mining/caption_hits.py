"""Print 30-second caption paragraphs that contain engineering keywords.

Usage: caption_hits.py <media-dir> [extra-regex]
Reads <media-dir>/captions.txt (from captions_to_text.py).
"""

import re
import sys
from pathlib import Path

KW = (r"sensor|thermocouple|rtd|igbt|mosfet|silicon carbide|\bsic\b|gan\b|coil|ferrite|litz|khz|frequen|"
      r"pan detect|warp|fail|failure|\bul\b|certif|firmware|\bota\b|algorithm|control loop|latency|"
      r"efficien|emi\b|noise|whine|buzz|fan\b|glass|ceramic|knob|magnet|clean|supplier|factory|"
      r"manufactur|reliab|accura|precision|sous|simmer|preheat|ramp|thermal|watts?\b|kilowatt|amps?\b|"
      r"volt|inverter|resonan|transistor|capacitor|circuit|board|chip|processor|test")


def main() -> None:
    d = Path(sys.argv[1])
    pat = re.compile(KW + ("|" + sys.argv[2] if len(sys.argv) > 2 else ""), re.I)
    lines = (d / "captions.txt").read_text().splitlines()
    print(lines[0])
    paras, cur, t0 = [], [], None
    for line in lines[1:]:
        m = re.match(r"\[(\d+):(\d+)\] (.*)", line)
        if not m:
            continue
        t = int(m[1]) * 60 + int(m[2])
        t0 = t if t0 is None else t0
        cur.append(m[3])
        if t - t0 >= 30:
            paras.append((t0, " ".join(cur)))
            cur, t0 = [], None
    if cur:
        paras.append((t0, " ".join(cur)))
    hits = [(t, p) for t, p in paras if len(pat.findall(p)) >= int(__import__("os").environ.get("MINHITS", "2"))]
    for t, p in hits:
        print(f"[{t // 60:02d}:{t % 60:02d}] {p}")
    print(f"# {len(hits)}/{len(paras)} paragraphs")


if __name__ == "__main__":
    main()
