"""JLC CPL rotation offsets for keyed parts from the LCSC/EasyEDA package records (KiCad Python).

<kicad-python> cad/tools/placement_offsets.py REF [REF ...]

Same method as sources/placement-rev-c.json: native KiCad pad centres at angle 0 (footprint
coordinates, y down) against the EasyEDA PAD records of the exact LCSC part (10 mil units, y down).
Numbered pads are matched, the common translation removed, and the native set is turned by
R(-offset) for offsets 0/90/180/270 (the audit's convention); the offset with the least RMS is the CPL offset, CPL angle = (board + offset)
% 360.  Records are cached in sources/placement-library/<LCSC>-product.json, fetched when absent
from the lceda.cn mirror of the EasyEDA product API: easyeda.com/api/products answers 403 to
scripted and browser requests since 2026-10-21, and the mirror's PAD records for C2684450 and
C44853692 are identical to the easyeda.com ones fetched the day before.  Results are written into
sources/placement-rev-c.json: rotation_offsets_by_ref and one `parts` entry per LCSC code.
"""
import hashlib
import json
import math
import sys
import urllib.request
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'sources' / 'placement-library'
AUDIT = ROOT / 'sources' / 'placement-rev-c.json'
UNIT = 0.254


def source_url(lcsc):
    return f'https://lceda.cn/api/products/{lcsc}/components?version=6.4.19.5'


def record(lcsc):
    path = LIB / f'{lcsc}-product.json'
    if not path.exists():
        req = urllib.request.Request(source_url(lcsc), headers={'User-Agent': 'Mozilla/5.0'})
        path.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    raw = path.read_bytes()
    return json.loads(raw)['result'], hashlib.sha256(raw).hexdigest(), path.name


# Parts whose EasyEDA pad numbers mean other pins than the KiCad footprint's. The fit matches pads
# by number, so these are renumbered to KiCad's meaning first. C2286 (KT-0603R LED): EasyEDA pad 1 =
# anode, pad 2 = cathode (symbol pins A/K in the same record); KiCad LED_0603 pad 1 = K, pad 2 = A.
# Without this the fit turns D4 by 180 deg, which would reverse the LED. (Diodes C2480 and C2128 use
# 1 = K on both sides and need no entry.)
VENDOR_TO_KICAD_PAD = {'C2286': {'1': '2', '2': '1'}}


def easyeda_pads(result):
    pads = {}
    for item in result['packageDetail']['dataStr']['shape']:
        f = item.split('~')
        if f[0] == 'PAD' and f[8]:
            pads[f[8]] = (float(f[2]) * UNIT, float(f[3]) * UNIT)
    return pads


def fit(native, vendor):
    common = sorted(set(native) & set(vendor))
    out = []
    for offset in (0, 90, 180, 270):
        a = math.radians(-offset)
        # the audit's convention: native pads turned by R(-offset), KiCad y-down
        rot = {n: (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))
               for n, (x, y) in native.items() if n in common}
        cx = sum(p[0] for p in rot.values()) / len(rot) - sum(vendor[n][0] for n in common) / len(common)
        cy = sum(p[1] for p in rot.values()) / len(rot) - sum(vendor[n][1] for n in common) / len(common)
        err = [math.hypot(rot[n][0] - cx - vendor[n][0], rot[n][1] - cy - vendor[n][1]) for n in common]
        out.append((math.sqrt(sum(e * e for e in err) / len(err)), max(err), offset))
    return sorted(out), common


def main():
    board = k.LoadBoard(str(ROOT / 'cad' / 'temper-lcr.kicad_pcb'))
    design = {p['ref']: p for p in json.loads((ROOT / 'cad' / 'design.json').read_text())['parts']}
    audit = json.loads(AUDIT.read_text())
    by_lcsc = {}
    for ref in sys.argv[1:]:
        by_lcsc.setdefault(design[ref]['lcsc'], []).append(ref)
    for lcsc, refs in by_lcsc.items():
        fp = board.FindFootprintByReference(refs[0])
        native = {}
        for pad in fp.Pads():
            if pad.GetNumber():
                rel = pad.GetFPRelativePosition()
                native.setdefault(pad.GetNumber(), (k.ToMM(rel.x), k.ToMM(rel.y)))
        result, sha, name = record(lcsc)
        vendor = easyeda_pads(result)
        swap = VENDOR_TO_KICAD_PAD.get(lcsc, {})
        vendor = {swap.get(n, n): xy for n, xy in vendor.items()}
        ranked, common = fit(native, vendor)
        rms, worst, offset = ranked[0]
        # native lands and the LCSC lands differ by up to 0.3 mm (U3 0.159, Q1 0.200 in the Rev C
        # audit; TQ2SA 0.300: Panasonic's 9.56 mm row span against the library's 10.16 mm, every
        # pad shifted equally); a wrong turn misplaces pads by a pitch or more
        assert rms < 0.35 and ranked[1][0] > 4 * rms, (lcsc, ranked)
        for ref in refs:
            audit['rotation_offsets_by_ref'][ref] = offset
        known = [p for p in audit['parts'] if p['lcsc'] == lcsc]
        if known:   # keep the audited entry; only add references that share its part
            assert known[0]['cpl_offset_ccw_deg'] == offset, (lcsc, known[0]['cpl_offset_ccw_deg'], offset)
            known[0]['references'] = sorted(set(known[0]['references']) | set(refs))
        else:
            audit['parts'].append({
                'lcsc': lcsc, 'mpn': design[refs[0]]['mpn'], 'references': refs,
                'native_footprint': design[refs[0]]['footprint'],
                'source_url': source_url(lcsc),
                'source_file': f'sources/placement-library/{name}', 'source_sha256': sha,
                'library_title': result['packageDetail']['title'], 'cpl_offset_ccw_deg': offset,
                'matched_numbered_pads': len(common), 'pad_center_fit_rms_mm': rms,
                'pad_center_fit_max_mm': worst,
                'candidate_rms_mm': [{'offset': o, 'rms': r} for r, _, o in ranked]})
        print(f'{lcsc:10} {",".join(refs):24} offset {offset:3}  rms {rms:.4f} mm over {len(common)} pads'
              f'  (next {ranked[1][0]:.2f} mm)  {result["packageDetail"]["title"]}')
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n')


main()
