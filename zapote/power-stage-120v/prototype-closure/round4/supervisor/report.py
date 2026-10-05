"""Record replay evidence without promoting connectivity into a release claim."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main(out: Path) -> None:
    erc = json.loads((out / 'erc.json').read_text())
    violations = [v for sheet in erc['sheets'] for v in sheet['violations']]
    if any(v['severity'] == 'error' for v in violations):
        raise ValueError('Typed ERC errors remain; replay cannot pass')
    allowed = {'footprint_link_issues', 'ground_pin_not_ground'}
    if any(v['type'] not in allowed for v in violations):
        raise ValueError('Unreviewed ERC warning class; inspect before reporting')
    with (HERE / 'generated/pins.tsv').open() as f:
        pins = list(csv.DictReader(f, delimiter='\t'))
    footprints = {p['reference']: p['footprint'] for p in pins}
    for v in violations:
        if v['type'] != 'footprint_link_issues':
            continue
        refs = [m.group(1) for item in v['items'] if (m := re.match(r'Symbol (\S+) \[', item['description']))]
        if not refs or any(not footprints.get(ref, '').startswith(('EXTERNAL:', 'REVIEW_ONLY:')) for ref in refs):
            raise ValueError('A standard footprint failed library resolution; not an accepted external-part warning')
    files = [HERE / p for p in ('circuit.rs', 'render.py', 'report.py', 'replay.sh', 'README.md', 'sources.md', 'review-disposition.md', 'generated/pins.tsv', 'generated/bom.csv', 'generated/supervisor.ato', 'generated/build/default.net', 'generated/resolved-components.json')]
    files += sorted((HERE / 'native').glob('*.kicad_sch'))
    files += [out / p for p in ('erc.json', 'kicad-netlist.xml', 'tests.txt', 'atopile-oracle.txt', 'kicad-oracle.txt')]
    record = {
        'status': 'SOURCE_CONNECTIVITY_REPLAY_PASS_DESIGN_NOT_RELEASED',
        'fabrication_release': False, 'powered_test_release': False,
        'tool_versions': {'atopile': json.loads((HERE / 'generated/resolved-components.json').read_text())['atopile_version'], 'kicad_cli': subprocess.check_output(['kicad-cli', 'version'], text=True).strip()},
        'components': len({p['reference'] for p in pins}), 'pins_including_nc': len(pins),
        'connected_pins': sum(p['net'] != 'NC' for p in pins),
        'erc_errors': 0, 'erc_warnings': dict(Counter(v['type'] for v in violations)),
        'warning_disposition': {
            'footprint_link_issues': 'Explicit external hardware and unresolved connector/mount footprints; do not fabricate from this package.',
            'ground_pin_not_ground': 'AUX_0V and CTRL_GND are explicit isolated local grounds; no renamed or shorted nets to silence ERC.'
        },
        'checks_do_not_prove': ['analog tolerances', 'power-up transients', 'switching timing', 'creepage/clearance', 'single fault safety', 'STM32 executable target firmware', 'manufacturability'],
        'sha256': {str(p.relative_to(HERE.parents[4])): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    }
    (out / 'evidence.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in record.items() if k != 'sha256'}, indent=2))

if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
