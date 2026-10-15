"""Pull transcript passages (Whisper, +/-2 segments of context) that mention
each focus subject, into frames/focus/transcript_<subject>.md.

Usage: subject_quotes.py <video-id>
"""
import json, os, re, sys
root = os.path.join(os.environ.get("MEDIA_ROOT", os.path.expanduser("~/temper-media")), sys.argv[1])
seg = json.load(open(f"{root}/whisper/video.json"))["segments"]
KW = {
 "drive": r"bridge|resonan|capacitor|igbt|mosfet|\bgan\b|silicon|carbide|frequen|hertz|khz|switch|inverter|heat ?sink|\bdc\b|volt|amp|watt|power electronic|drive|kilowatt|efficien",
 "coil": r"coil|ferrite|litz|wire|turns|winding|sensor|sensing|temperature|thermistor|infrared|\bir\b|glass|thermal|paste|rtd|thermocouple|pan detect|inductance",
 "controller": r"processor|mcu|micro|safety|screen|\bota\b|wi-?fi|firmware|software|certif|\bul\b|linux|android|algorithm|knob|connectiv",
}
fmt = lambda t: f"{int(t//60):02d}:{int(t%60):02d}"
for subj, pat in KW.items():
    hits = [i for i, s in enumerate(seg) if re.search(pat, s["text"], re.I)]
    keep = sorted({j for i in hits for j in range(max(0, i-2), min(len(seg), i+3))})
    out, prev = [], -10
    for j in keep:
        if j != prev + 1: out.append("")
        out.append(f"[{fmt(seg[j]['start'])}] {seg[j]['text'].strip()}")
        prev = j
    path = f"{root}/frames/focus/transcript_{subj}.md"
    open(path, "w").write(f"# {subj}: transcript passages (Whisper, +/-2 segments)\n" + "\n".join(out) + "\n")
    print(subj, len(hits), "hits,", len(keep), "lines ->", path)
