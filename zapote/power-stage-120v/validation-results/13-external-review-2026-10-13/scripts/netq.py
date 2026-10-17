"""Query the native-21 frozen netlist (KiCad E export from atopile).

Usage: python3 netq.py REF [REF...]      -> pins and nets of each part
       python3 netq.py --net NAME [...]  -> members of each net
Netlist: native-21/frozen/default.net (path relative to the unit root),
or --file PATH. Read-only.
"""
import re, sys, os
here = os.path.dirname(os.path.abspath(__file__))
unit = os.path.abspath(os.path.join(here, '..', '..', '..'))
args = sys.argv[1:]
path = os.path.join(unit, 'native-21', 'frozen', 'default.net')
if '--file' in args:
    i = args.index('--file'); path = args[i + 1]; del args[i:i + 2]
s = open(path).read()
nets = {}
body = s[s.index('(nets'):]
for chunk in body.split('(net (code')[1:]:
    name = re.search(r'\(name "([^"]*)"\)', chunk).group(1)
    nets[name] = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', chunk)
comps = {}
for chunk in s[:s.index('(nets')].split('(comp (ref ')[1:]:
    ref = re.match(r'"([^"]+)"', chunk).group(1)
    m = re.search(r'\(part "([^"]*)"\)', chunk)
    comps[ref] = m.group(1) if m else None
# The netlist's (part ...) field is aliased by atopile 0.2.69 for parts that
# share a footprint; take MPNs from resolved-components.json instead.
import json
rc = os.path.join(os.path.dirname(path), 'resolved-components.json')
if os.path.exists(rc):
    for c in json.load(open(rc))['components']:
        a = c['attributes']
        if 'designator' in a:
            comps[a['designator']] = f"{a.get('mpn')} ({a.get('value', '')})"
bypin = {}
for n, nodes in nets.items():
    for r, p in nodes:
        bypin.setdefault(r, []).append((p, n))
if args and args[0] == '--net':
    for n in args[1:]:
        print(n, '->', ' '.join(f'{r}.{p}' for r, p in nets.get(n, [])))
else:
    for r in args:
        print(r, comps.get(r), sorted(bypin.get(r, []), key=lambda x: x[0]))
