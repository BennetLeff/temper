"""Minimal read-only KiCad .kicad_pcb footprint/pad extractor (stdlib only)."""
import re


def _tokens(text):
    for m in re.finditer(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text):
        yield m.group(0)


def parse(text):
    stack = [[]]
    for t in _tokens(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            node = stack.pop()
            stack[-1].append(node)
        elif t.startswith('"'):
            stack[-1].append(t[1:-1])
        else:
            stack[-1].append(t)
    return stack[0][0]


def footprints(path):
    """Return {ref: {name, x, y, rot, layer, pads:[{num,x,y,w,h,type,shape}]}}."""
    tree = parse(open(path, encoding="utf-8").read())
    out = {}
    for n in tree:
        if not (isinstance(n, list) and n and n[0] == "footprint"):
            continue
        fp = {"name": n[1], "pads": [], "layer": None, "rot": 0.0}
        ref = None
        for c in n[2:]:
            if not isinstance(c, list) or not c:
                continue
            if c[0] == "layer" and fp["layer"] is None:
                fp["layer"] = c[1]
            elif c[0] == "at":
                fp["x"], fp["y"] = float(c[1]), float(c[2])
                fp["rot"] = float(c[3]) if len(c) > 3 else 0.0
            elif c[0] == "property" and c[1] == "Reference":
                ref = c[2]
            elif c[0] == "pad":
                p = {"num": c[1], "type": c[2], "shape": c[3]}
                for q in c[4:]:
                    if isinstance(q, list) and q:
                        if q[0] == "at":
                            p["x"], p["y"] = float(q[1]), float(q[2])
                        elif q[0] == "size":
                            p["w"], p["h"] = float(q[1]), float(q[2])
                fp["pads"].append(p)
        if ref:
            out[ref] = fp
    return out
