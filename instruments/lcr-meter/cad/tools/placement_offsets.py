"""JLC CPL rotation offsets for keyed parts from the LCSC/EasyEDA package records (KiCad Python).

<kicad-python> cad/tools/placement_offsets.py REF [REF ...]

Same method as sources/placement-rev-c.json: native KiCad pad centres at angle 0 (footprint
coordinates, y down) against the EasyEDA PAD records of the exact LCSC part (10 mil units, y down).
Numbered pads are matched, the common translation removed, and the native set is turned by
R(-offset) for offsets 0/90/180/270 (the audit's convention); the offset with the least RMS is the CPL offset, CPL angle = (board + offset)
% 360.  The fit, the record cache and the lceda.cn mirror are temper_boardkit.jlc.easyeda (fit_cpl_offset,
record); records live in sources/placement-library/<LCSC>-product.json.  Results are written into
sources/placement-rev-c.json: rotation_offsets_by_ref and one `parts` entry per LCSC code.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boardkit_path  # noqa: E402,F401
from temper_boardkit import kicad  # noqa: E402
from temper_boardkit.jlc import easyeda  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'sources' / 'placement-library'
AUDIT = ROOT / 'sources' / 'placement-rev-c.json'

# Parts whose EasyEDA pad numbers mean other pins than the KiCad footprint's. The fit matches pads
# by number, so these are renumbered to KiCad's meaning first. C2286 (KT-0603R LED): EasyEDA pad 1 =
# anode, pad 2 = cathode (symbol pins A/K in the same record); KiCad LED_0603 pad 1 = K, pad 2 = A.
# Without this the fit turns D4 by 180 deg, which would reverse the LED. (Diodes C2480 and C2128 use
# 1 = K on both sides and need no entry; so does C160472, the LTST-S270KFKT side-view LED: EasyEDA pin
# 1 = C, pin 2 = A.)
VENDOR_TO_KICAD_PAD = {'C2286': {'1': '2', '2': '1'}}


def main():
    board = kicad.load_board(ROOT / 'cad' / 'temper-lcr.kicad_pcb')
    design = {p['ref']: p for p in json.loads((ROOT / 'cad' / 'design.json').read_text())['parts']}
    audit = json.loads(AUDIT.read_text())
    by_lcsc = {}
    for ref in sys.argv[1:]:
        by_lcsc.setdefault(design[ref]['lcsc'], []).append(ref)
    for lcsc, refs in by_lcsc.items():
        native = kicad.footprint_pads(board, refs[0])
        result, sha, name = easyeda.record(lcsc, LIB)
        vendor = easyeda.renumber(easyeda.easyeda_pads(result), VENDOR_TO_KICAD_PAD.get(lcsc, {}))
        ranked, common = easyeda.fit_cpl_offset(native, vendor)
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
                'source_url': easyeda.source_url(lcsc),
                'source_file': f'sources/placement-library/{name}', 'source_sha256': sha,
                'library_title': result['packageDetail']['title'], 'cpl_offset_ccw_deg': offset,
                'matched_numbered_pads': len(common), 'pad_center_fit_rms_mm': rms,
                'pad_center_fit_max_mm': worst,
                'candidate_rms_mm': [{'offset': o, 'rms': r} for r, _, o in ranked]})
        print(f'{lcsc:10} {",".join(refs):24} offset {offset:3}  rms {rms:.4f} mm over {len(common)} pads'
              f'  (next {ranked[1][0]:.2f} mm)  {result["packageDetail"]["title"]}')
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n')


main()
