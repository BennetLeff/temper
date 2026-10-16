#!/usr/bin/env python3
"""Tiny KiCad netlist query: python3 -I netq.py NETFILE [REF ...] | --net NAME ..."""
import re, sys
def load(path):
    t = open(path).read()
    blocks = re.findall(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)(?=\n    \(net |\n  \)\n\))', t, re.S)
    nets = {n: re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)(?: \(pinfunction "([^"]*)"\))?', b) for n, b in blocks}
    comps = dict(re.findall(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)', t))
    return nets, comps
if __name__ == "__main__":
    nets, comps = load(sys.argv[1])
    args = sys.argv[2:]
    if args and args[0] == "--net":
        for n in args[1:]:
            print(n, ":", " ".join(f"{r}.{p}({comps.get(r,'?')})" for r, p, *_ in nets.get(n, [])))
    else:
        for ref in args:
            pins = sorted([(p, n, f[0] if f else "") for n, nodes in nets.items() for r, p, *f in nodes if r == ref], key=lambda x: x[0])
            print(ref, comps.get(ref), pins)
