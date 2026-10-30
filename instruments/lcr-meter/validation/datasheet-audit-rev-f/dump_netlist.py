"""Per-part and per-net text dump of build/netlist.xml (from cad/rebuild.sh) for the datasheet audit.

Usage: python3 validation/datasheet-audit-rev-f/dump_netlist.py  ->  parts.txt, nets.txt beside this file.
"""

import collections
import csv
import pathlib
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
tree = ET.parse(ROOT / "build/netlist.xml").getroot()
bom = {}
for row in csv.DictReader(open(ROOT / "manufacturing/bom-complete.csv")):
    for ref in row["Designators"].split(","):
        bom[ref.strip()] = (row["MPN"], row["LCSC"], row["Assembly"])
pins = collections.defaultdict(list)
nets = {}
for net in tree.iter("net"):
    name = net.get("name")
    nets[name] = [(n.get("ref"), n.get("pin"), n.get("pinfunction") or "") for n in net.iter("node")]
    for ref, pin, fn in nets[name]:
        pins[ref].append((pin, fn, name))


def key(ref):
    head = ref.rstrip("0123456789")
    return head, int(ref[len(head) :] or 0)


lines = []
for comp in sorted(tree.iter("comp"), key=lambda c: key(c.get("ref"))):
    ref = comp.get("ref")
    mpn, lcsc, assembly = bom.get(ref, ("-", "-", "not in BOM"))
    lines.append(f"{ref}  value={comp.findtext('value')}  mpn={mpn}  lcsc={lcsc}  {assembly}  fp={comp.findtext('footprint')}")
    for pin, fn, name in sorted(pins[ref], key=lambda p: (len(p[0]), p[0])):
        lines.append(f"    {pin:>4} {fn:<16} {name}")
(HERE / "parts.txt").write_text("\n".join(lines) + "\n")
out = []
for name in sorted(nets):
    out.append(f"{name}: " + " ".join(f"{r}.{p}" for r, p, _ in sorted(nets[name], key=lambda n: key(n[0]))))
(HERE / "nets.txt").write_text("\n".join(out) + "\n")
print(len(lines), "part lines,", len(nets), "nets")
