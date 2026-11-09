"""Same-day JLC assembly-library snapshot of every LCSC code on Rev F's and Rev G's BOMs (read-only search).

    python3 validation/rev-g/prices/fetch_prices.py [REV_F_GIT_REV]    (default study/lcr-in-box)
    -> validation/rev-g/prices/jlc-parts-<today>.json

One snapshot for both boards, so the Rev F / Rev G cost comparison (compare_f_g.sh) prices them on the same day.
Rev F's bom-complete.csv is read from git; Rev G's is validation/rev-g/bom-complete.csv. The fetch and the schema
(which manufacturing/order_estimate.py reads) are temper_boardkit.jlc.parts, as manufacturing/prices/fetch_jlc_parts.py.
"""
import csv
import io
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'cad' / 'tools'))
import boardkit_path  # noqa: E402,F401
from temper_boardkit.jlc import parts  # noqa: E402

REV_F = sys.argv[1] if len(sys.argv) > 1 else 'study/lcr-in-box'
rev_f = subprocess.check_output(['git', 'show', f'{REV_F}:./manufacturing/bom-complete.csv'], cwd=ROOT, text=True)
codes = [r['LCSC'] for r in csv.DictReader(io.StringIO(rev_f))]
codes += [r['LCSC'] for r in csv.DictReader(open(ROOT / 'validation/rev-g/bom-complete.csv'))]
snap = parts.snapshot(codes)
dest = HERE / f'jlc-parts-{snap["fetched"]}.json'
parts.write(dest, snap)
print(f'{len(snap["parts"])} parts -> {dest}')
