"""Transport complete D28 captures through D22's unmodified spectral comparator."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent
D22=HERE.parent/'out-D22'
sys.path.insert(0,str(D22))
import numeric_compare as compare
import qualify_filter as receiver

# Redirect only output roots. D22's receiver, scenarios, thresholds and math stay intact.
compare.HERE=HERE
receiver.HERE=HERE
(HERE/'tmp').mkdir(exist_ok=True)
tempfile.tempdir=str(HERE/'tmp')

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('coarse')
    parser.add_argument('fine')
    args=parser.parse_args()
    a=HERE/'runs'/args.coarse
    b=HERE/'runs'/args.fine
    coarse=json.loads((a/'result.json').read_text())
    fine=json.loads((b/'result.json').read_text())
    result={'coarse':args.coarse,'fine':args.fine,'status':'indeterminate'}
    if all(row.get('periodic',{}).get('status')=='complete' for row in (coarse,fine)):
        compare.assert_same_operating_point(coarse,fine)
        result['cycle']=compare.compare(b/'prior-fft.npz',b/'fft.npz',args.fine+'-cycle')
        result['step']=compare.compare(a/'fft.npz',b/'fft.npz',args.fine+'-step')
        result['status']='comparisons_complete'
        # Forward D22's own row decisions; final engineering verdict is in Rust.
    (HERE/(args.fine+'-qualification.json')).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
    main()
