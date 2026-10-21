"""Independent post-build audit of the native board against cad/design.json (read-only).

Run with KiCad's bundled Python:  <kicad-python> validation/independent_check.py REV
Writes validation/independent-verification-rev-<rev>.json.  Separate from rebuild.sh:
it reads the saved .kicad_pcb and a freshly exported netlist, never the build code.
Checks:
  - every source pin's net equals the native pad net and the exported schematic netlist;
  - no non-GND copper on In1 (the ground plane layer);
  - OPA2810 signal pins and THS4551 inputs sit inside In1/In2/B.Cu rule areas (plane relief);
  - OPA2810 supply bypass pad-centre distances;
  - R_iso topology: J3 LO and the LOW follower on DUT_LO; U7A -IN, C104 and RF on TIA_SUM.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
REV = sys.argv[1].lower()
MM = 1e-6
pcb_path = ROOT / 'cad/temper-lcr.kicad_pcb'
board = k.LoadBoard(str(pcb_path))
design = json.loads((ROOT / 'cad/design.json').read_text())
findings = []


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# 1. Source pins vs native pads vs exported netlist.
pads = {}
for f in board.GetFootprints():
    for p in f.Pads():
        if p.GetNumber():
            pads[(f.GetReference(), p.GetNumber())] = (p.GetNetname(), p)
with tempfile.TemporaryDirectory() as tmp:
    xml = Path(tmp) / 'netlist.xml'
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml', '--output', str(xml),
                    str(ROOT / 'cad/temper-lcr.kicad_sch')], check=True, capture_output=True)
    netlist = {}
    for net in ET.parse(xml).getroot().iter('net'):
        name = net.get('name').lstrip('/')
        for node in net.iter('node'):
            netlist[(node.get('ref'), node.get('pin'))] = '' if name.startswith('unconnected-') else name
pins_checked = 0
for part in design['parts']:
    for num, net in part['pins'].items():
        want = net or ''
        native = pads.get((part['ref'], num), (None,))[0]
        if native and native.startswith('unconnected-'):
            native = ''
        sch = netlist.get((part['ref'], num), '')
        pins_checked += 1
        if native != want:
            findings.append(f"pad {part['ref']}.{num}: design {want!r}, board {native!r}")
        if sch != want:
            findings.append(f"netlist {part['ref']}.{num}: design {want!r}, schematic {sch!r}")

# 2. In1 carries only ground copper.
for t in board.GetTracks():
    if t.GetLayer() == k.In1_Cu and t.GetNetname() != 'GND':
        findings.append(f'In1 track on {t.GetNetname()} at {t.GetStart().x * MM:.3f},{t.GetStart().y * MM:.3f}')

# 3. Plane relief under analog signal pins.
rules = [z for z in board.Zones() if z.GetIsRuleArea()]
relief = []
SIGNAL = {'OPA2810IDGKR': ['1', '2', '3', '5', '6', '7'], 'THS4551IRGTR': ['2', '3']}
for f in board.GetFootprints():
    pins = SIGNAL.get(f.GetValue())
    if not pins:
        continue
    for num in pins:
        pad = pads[(f.GetReference(), num)][1]
        c = pad.GetPosition()
        cover = {k.BOARD.GetStandardLayerName(lid) for z in rules for lid in (k.In1_Cu, k.In2_Cu, k.B_Cu)
                 if z.IsOnLayer(lid) and z.Outline().Contains(k.VECTOR2I(c.x, c.y))}
        relief.append({'pin': f'{f.GetReference()}.{num}', 'layers': sorted(cover)})
        if len(cover) != 3:
            findings.append(f'{f.GetReference()}.{num} relief only on {sorted(cover)}')

# 4. OPA2810 bypass distances (supply pad centre to nearest capacitor pad on the same net).
bypass = []
for ref in ('U6', 'U7'):
    for num in ('8', '4'):
        net, pad = pads[(ref, num)]
        c = pad.GetPosition()
        best = min(((r, (q.GetPosition() - c).EuclideanNorm() * MM) for (r, n), (nn, q) in pads.items()
                    if nn == net and r.startswith('C')), key=lambda x: x[1])
        bypass.append({'pin': f'{ref}.{num}', 'net': net, 'capacitor': best[0], 'distance_mm': round(best[1], 3)})
        if best[1] > 2.54:
            findings.append(f'{ref}.{num} bypass {best[0]} at {best[1]:.2f} mm')

# 5. R_iso topology (Rev D).
topology = {}
if REV == 'd':
    expect = {('J3', '2'): 'DUT_LO', ('U7', '5'): 'DUT_LO', ('R94', '1'): 'DUT_LO', ('R94', '2'): 'TIA_SUM',
              ('U7', '2'): 'TIA_SUM', ('C104', '1'): 'TIA_SUM', ('C104', '2'): 'TIA_OUT',
              ('R43', '1'): 'TIA_SUM', ('R44', '1'): 'TIA_SUM', ('R45', '1'): 'TIA_SUM'}
    for (ref, num), net in expect.items():
        got = pads[(ref, num)][0]
        topology[f'{ref}.{num}'] = got
        if got != net:
            findings.append(f'R_iso topology {ref}.{num}: {got}, expected {net}')
    on_sum = sorted(f'{r}.{n}' for (r, n), (net, _) in pads.items() if net == 'TIA_SUM')
    topology['TIA_SUM_pads'] = on_sum
    if on_sum != ['C104.1', 'R43.1', 'R44.1', 'R45.1', 'R94.2', 'U7.2']:
        findings.append(f'TIA_SUM carries unexpected pads {on_sum}')

files = ['cad/temper-lcr.kicad_pcb', 'cad/temper-lcr.kicad_pro', 'cad/design.json', 'cad/routing.json',
         'cad/temper-lcr.kicad_sch'] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'cad').glob('*.kicad_sch')
                                               if p.name != 'temper-lcr.kicad_sch')
out = {
    'revision': REV.upper(), 'board_sha256': sha(pcb_path), 'kicad_version': k.GetBuildVersion(),
    'method': __doc__.strip().split('\n')[0],
    'source_pins_checked': pins_checked, 'native_pads': len(pads), 'netlist_nodes': len(netlist),
    'plane_relief': relief, 'opa_bypass': bypass, 'r_iso_topology': topology,
    'findings': findings, 'pass': not findings,
    'limits': 'Pad-centre and net checks on native data; not electromagnetic extraction or physical qualification.',
    'files_sha256': {f: sha(ROOT / f) for f in files},
}
(ROOT / f'validation/independent-verification-rev-{REV}.json').write_text(json.dumps(out, indent=1) + '\n')
print(f"{pins_checked} pins, {len(relief)} relief pins, findings {len(findings)}")
for x in findings[:20]:
    print(' ', x)
sys.exit(1 if findings else 0)
