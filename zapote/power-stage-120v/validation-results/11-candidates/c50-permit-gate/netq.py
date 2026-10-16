"""Tiny KiCad 'E' netlist query: python3 -I netq.py NET.net [ref|net ...]"""
import re, sys
def parse(path):
    s = open(path).read()
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)\s*\(libsource \(lib "[^"]*"\) \(part "([^"]*)"\) \(description "([^"]*)"\)\)\s*\(sheetpath \(names "([^"]*)"', s):
        comps[m.group(1)] = dict(part=m.group(4), desc=m.group(5), path=m.group(6).split(':')[-1], fp=m.group(3))
    nets = {}
    chunks = re.split(r'\(net \(code ', s)[1:]
    for ch in chunks:
        name = re.match(r'"?\d+"?\) \(name "([^"]*)"\)', ch).group(1)
        nodes = [(r, p, '') for r, p in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', ch)]
        m = None
        nets[name] = nodes
    import json, os
    rc = os.path.join(os.path.dirname(path), 'resolved-components.json')
    if os.path.exists(rc):
        for c in json.load(open(rc))['components']:
            a = c['attributes']; d = a.get('designator')
            if d in comps:
                comps[d]['part'] = a.get('mpn', '?') + (' ' + a['value'] if 'value' in a else '')
    return comps, nets
if __name__ == '__main__':
    comps, nets = parse(sys.argv[1])
    pin2net = {}
    for n, nodes in nets.items():
        for r, p, f in nodes:
            pin2net[(r, p)] = (n, f)
    for q in sys.argv[2:]:
        if q in comps:
            c = comps[q]; print(f'== {q} {c["part"]} [{c["path"]}] {c["desc"]}')
            for (r, p), (n, f) in sorted(pin2net.items(), key=lambda x: (x[0][0], int(x[0][1]) if x[0][1].isdigit() else 999)):
                if r == q: print(f'   pin {p:>3} {f or "":<14} -> {n} ({len(nets[n])} nodes)')
        else:
            hits = [n for n in nets if n == q] or [n for n in nets if q.lower() in n.lower()]
            for n in hits:
                print(f'## net {n}: ' + ', '.join(f'{r}.{p}' for r, p, f in nets[n]))
