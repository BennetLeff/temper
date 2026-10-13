"""Verify that both native-21 exports describe the committed circuit source."""
from pathlib import Path
import hashlib
import json


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = json.loads((root / 'frozen/resolved-components.json').read_text())
    assert len(resolved['components']) == 357   # stage 19b: + c_ref_xfer_1..4 (pwm_hb reference-transfer caps C153-C156); stage 16: + f_blw / j_blw_ac (blower-supply tap); stage 14: -8 (bias modules replace SN6507/T2/T3 path; +1 bus TVS); + c_hs / c_hs_bulk per leg (review B1), + c_hs_1u / c_ls_1u per leg (stage 9), + c_vs1_1u / c_vs2_1u (stage 10), + c_res4 / c_res5 (stage 13)
    for filename, expected in resolved['source_sha256'].items():
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == expected, filename
    for filename in ('default.csv', 'default.net', 'resolved-components.json',
                     'default.layouts.json', 'manifest.json'):
        assert (root / 'frozen' / filename).read_bytes() == (root / 'native-21/frozen' / filename).read_bytes(), filename
    parts = {c['address'].split('::')[1]: c['attributes'] for c in resolved['components']}
    assert all(parts[f'c_res{i}']['mpn'] == 'B32654A1104J000' for i in range(1, 6))
    for leg in ('leg_a', 'leg_b'):
        assert parts[f'{leg}.r_dt']['mpn'] == 'RT0603BRD0749K9L'
        assert parts[f'{leg}.r_dis_pu']['mpn'] == '0603WAF3300T5E'
    assert parts['r_th_top']['mpn'] == 'RT0603BRD0712K6L'   # stage 15, 28 A hardware
    assert parts['f_blw']['mpn'] == '3403.0171' and parts['j_blw_ac']['mpn'] == 'B2P3-VH(LF)(SN)'   # stage 16
    assert parts['r_shunt']['mpn'] == 'CSS2H-2512R-1L00F' and parts['r_shunt']['footprint'] == 'temper:R_Shunt_Bourns_CSS2H-2512_Kelvin'   # stage 17 (DECISIONS 17)
    assert parts['r_ct_hi_top']['mpn'] == parts['r_ct_lo_bot']['mpn'] == 'RT0603BRD072K21L'
    assert all(parts[f'c_ref_xfer_{i}']['mpn'] == parts['c_fault_or']['mpn'] == 'CC0603KRX7R9BB104' for i in range(1, 5))   # stage 19b
    for leg in ('leg_a', 'leg_b'):
        assert parts[f'{leg}.c_hs']['mpn'] == 'CC0805KRX7R9BB104' and parts[f'{leg}.c_hs_bulk']['mpn'] == 'GRM21BZ71E106KE15L'
        assert parts[f'{leg}.c_ls']['mpn'] == 'CC0805KRX7R9BB104'
        assert parts[f'{leg}.c_hs_1u']['mpn'] == parts[f'{leg}.c_ls_1u']['mpn'] == 'CL21B105KBFNNNE'
    # Stage 14: RECOM appears only as the two high-side bias modules on V24_RAW (TCO-switched PS2), not
    # as D-12's SELV-fed module set (DECISIONS 2026-10-06 / 2026-10-09).
    assert {path for path, part in parts.items() if 'RECOM' in str(part)} == {'bias_ha.iso', 'bias_hb.iso'}
    assert parts['c_bus1']['mpn'] == parts['c_bus2']['mpn'] == 'B32676G1905K000'
    assert parts['tvs_bus']['mpn'] == parts['tvs_bus_b']['mpn'] == '30KPA150CA'
    assert not any('.d_boot' in path or '.c_boot' in path for path in parts)
    for base in ('monitor_ls', 'bias_ha.monitor', 'bias_hb.monitor'):
        assert parts[f'{base}.iso']['mpn'] == 'ISO7710DWR'
        assert not any(path.startswith(base + '.') and part.get('mpn') == 'VO617A-3X017T' for path, part in parts.items())
    result = {'components': len(parts), 'source_hashes_match': True,
              'two_frozen_exports_identical': True, 'native20_protection_parts_retained': True,
              'RECOM_only_hs_bias_modules': True, 'no_bootstrap': True, 'monitor_crossings_ISO7710': True, 'source_sha256': resolved['source_sha256']}
    (Path(__file__).parent / 'source-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
