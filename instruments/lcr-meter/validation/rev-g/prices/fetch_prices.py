"""Same-day JLC assembly-library snapshot of every LCSC code on Rev F's and Rev G's BOMs (read-only search).

    python3 validation/rev-g/prices/fetch_prices.py [REV_F_GIT_REV]    (default study/lcr-in-box)
    -> validation/rev-g/prices/jlc-parts-<today>.json
    python3 validation/rev-g/prices/fetch_prices.py --add
    -> fetches only the codes on the boards' BOMs (Rev G100's too) that the latest snapshot lacks, and adds them to it
       (the codes already there keep their prices, so earlier estimates from that snapshot still reproduce)

One snapshot for both boards, so the Rev F / Rev G cost comparison (compare_f_g.sh) prices them on the same day.
Rev F's bom-complete.csv is read from git; Rev G's is validation/rev-g/bom-complete.csv. The fetch and the schema
(which manufacturing/order_estimate.py reads) are temper_boardkit.jlc.parts, as manufacturing/prices/fetch_jlc_parts.py.
"""
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'cad' / 'tools'))
import boardkit_path  # noqa: E402,F401
from temper_boardkit.jlc import parts  # noqa: E402

ADD = '--add' in sys.argv
args = [a for a in sys.argv[1:] if a != '--add']
REV_F = args[0] if args else 'study/lcr-in-box'
rev_f = subprocess.check_output(['git', 'show', f'{REV_F}:./manufacturing/bom-complete.csv'], cwd=ROOT, text=True)
codes = [r['LCSC'] for r in csv.DictReader(io.StringIO(rev_f))]
for bom in ('validation/rev-g/bom-complete.csv', 'validation/rev-g100/bom-complete.csv'):
    if (ROOT / bom).exists():
        codes += [r['LCSC'] for r in csv.DictReader(open(ROOT / bom))]
if ADD:
    dest = sorted(HERE.glob('jlc-parts-*.json'))[-1]
    old = json.loads(dest.read_text())
    missing = sorted(set(codes) - set(old['parts']))
    new = parts.snapshot(missing)
    old['parts'].update(new['parts'])
    old.setdefault('added', []).append({'fetched': new['fetched'], 'codes': missing})
    parts.write(dest, old)
    print(f'{len(missing)} parts added ({", ".join(missing)}) -> {dest}')
else:
    snap = parts.snapshot(codes)
    dest = HERE / f'jlc-parts-{snap["fetched"]}.json'
    parts.write(dest, snap)
    print(f'{len(snap["parts"])} parts -> {dest}')
