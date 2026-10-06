"""Verify that both native-21 exports describe the committed circuit source."""
from pathlib import Path
import hashlib
import json


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = json.loads((root / 'frozen/resolved-components.json').read_text())
    assert len(resolved['components']) == 331
    for filename, expected in resolved['source_sha256'].items():
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == expected, filename
    for filename in ('default.csv', 'default.net', 'resolved-components.json',
                     'default.layouts.json', 'manifest.json'):
        assert (root / 'frozen' / filename).read_bytes() == (root / 'native-21/frozen' / filename).read_bytes(), filename
    parts = {c['address'].split('::')[1]: c['attributes'] for c in resolved['components']}
    for leg in ('leg_a', 'leg_b'):
        assert parts[f'{leg}.r_dt']['mpn'] == 'RT0603BRD0749K9L'
        assert parts[f'{leg}.r_dis_pu']['mpn'] == 'RC0603FR-07330RL'
    assert parts['r_th_top']['mpn'] == 'RT0603BRD0710K6L'
    assert not any('RECOM' in str(part) for part in parts.values())
    assert not any('.d_boot' in path or '.c_boot' in path for path in parts)
    result = {'components': len(parts), 'source_hashes_match': True,
              'two_frozen_exports_identical': True, 'native20_protection_parts_retained': True,
              'no_RECOM_or_bootstrap': True, 'source_sha256': resolved['source_sha256']}
    (Path(__file__).parent / 'source-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
