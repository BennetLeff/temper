"""Merge KiCad-plotted per-layer SVGs into one cropped SVG (layer opacity), with optional overlay rectangles/labels.
   python3 composite.py OUT.svg x0 y0 x1 y1 overlay.json layer1.svg[:opacity] ..."""
import sys, re, json
out, x0, y0, x1, y1, ov = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6]
parts = []
for a in sys.argv[7:]:
    f, _, op = a.partition(":")
    s = open(f).read()
    body = s[s.index("<g "):s.rindex("</svg>")]
    parts.append(f'<g opacity="{op or 0.5}">{body}</g>')
over = []
if ov != "-":
    for o in json.load(open(ov)):
        if o["t"] == "rect":
            x, y, X, Y = o["r"]
            over.append(f'<rect x="{x}" y="{y}" width="{X-x}" height="{Y-y}" fill="{o.get("fill","none")}" fill-opacity="{o.get("fo",0.25)}" stroke="{o.get("c","#000")}" stroke-width="{o.get("w",0.4)}" stroke-dasharray="{o.get("dash","")}"/>')
        elif o["t"] == "circle":
            over.append(f'<circle cx="{o["x"]}" cy="{o["y"]}" r="{o["rad"]}" fill="none" stroke="{o.get("c","#000")}" stroke-width="{o.get("w",0.3)}"/>')
        elif o["t"] == "line":
            over.append(f'<line x1="{o["a"][0]}" y1="{o["a"][1]}" x2="{o["b"][0]}" y2="{o["b"][1]}" stroke="{o.get("c","#000")}" stroke-width="{o.get("w",0.4)}" stroke-dasharray="{o.get("dash","")}"/>')
        elif o["t"] == "text":
            over.append(f'<text x="{o["x"]}" y="{o["y"]}" font-size="{o.get("s",3)}" font-family="Helvetica" fill="{o.get("c","#000")}">{o["s_"]}</text>')
W, H = x1 - x0, y1 - y0
svg = (f'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="{W*12}px" height="{H*12}px" viewBox="{x0} {y0} {W} {H}">'
       f'<rect x="{x0}" y="{y0}" width="{W}" height="{H}" fill="#ffffff"/>' + "".join(parts) + "".join(over) + "</svg>")
open(out, "w").write(svg)
