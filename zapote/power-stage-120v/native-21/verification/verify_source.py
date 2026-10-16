"""Verify that both native-21 exports describe the committed circuit source."""
from pathlib import Path
import hashlib
import json


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = json.loads((root / 'frozen/resolved-components.json').read_text())
    assert len(resolved["components"]) == 372   # stage 48: + 8 LDO EN dividers R136-R143 (S19), + REF25 watchdog R144 / R145 (B13 H1), + BIAS_GOOD readback R146 and its three transfer caps c_ref_xfer_13..15 (C176-C178) (B13 H2); stage 44: + c_ref_xfer_6..12 (C169-C175, SELV return-path transfer caps, candidate 44); stage 40: + hb.vote_b (D20), + hb.rgate (R135), + c_ref_xfer_5 (C168, pwm_hb transfer cap in place of the old verdict isolator's SELV decoupler) (candidate 30a; U44 / C159 / C160 become the HS-B link and its caps); stage 38: - ps_selv (PS1, candidate 23); stage 30: -22 / +21 (candidate 24 heartbeat, HS-A link ISO6721FB, HS-B verdict ISO7710F, U9 RC); stage 28: + r_blw (F2 fault-current limiter); stage 22: - Q1 / Q4 PERMIT FETs and R8 / R16 330 ohm (DIS NAND); stage 21: - link_pos / link_neg studs J7-J10 (BR1 feeds the bus); stage 19b: + c_ref_xfer_1..4 (pwm_hb reference-transfer caps C153-C156); stage 16: + f_blw / j_blw_ac (blower-supply tap); stage 14: -8 (bias modules replace SN6507/T2/T3 path; +1 bus TVS); + c_hs / c_hs_bulk per leg (review B1), + c_hs_1u / c_ls_1u per leg (stage 9), + c_vs1_1u / c_vs2_1u (stage 10), + c_res4 / c_res5 (stage 13)
    for filename, expected in resolved['source_sha256'].items():
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == expected, filename
    for filename in ('default.csv', 'default.net', 'resolved-components.json',
                     'default.layouts.json', 'manifest.json'):
        assert (root / 'frozen' / filename).read_bytes() == (root / 'native-21/frozen' / filename).read_bytes(), filename
    parts = {c['address'].split('::')[1]: c['attributes'] for c in resolved['components']}
    # stage 49 (DECISIONS 68, candidate 34): the bank is 5 x TDK B32643B8104J000 (2000 V DC, P22.5) on its own footprint
    assert all(parts[f'c_res{i}']['mpn'] == 'B32643B8104J000' and
               parts[f'c_res{i}']['footprint'] == 'temper:TDK_B32643B_P22.5_W14.5_L26.5_Radial' for i in range(1, 6))
    for leg in ('leg_a', 'leg_b'):
        assert parts[f'{leg}.r_dt']['mpn'] == 'RT0603BRD0749K9L'
        # stage 22 (DECISIONS 27): DIS = NAND(permit_gate, bias_good); the PERMIT FET and 330 ohm pull-up are gone
        assert parts[f'{leg}.dis_or']['mpn'] == 'SN74LVC1G00DBVR' and f'{leg}.permit_fet' not in parts and f'{leg}.r_dis_pu' not in parts
    assert parts['u_bias_flt']['mpn'] == 'SN74LVC1G17DBVR'   # stage 30: non-inverting Schmitt on the heartbeat hold node
    # stage 27 (DECISIONS 29): J1 carries UL/CSA group B 30 A (the MKDS 3 1711725 was 15 A cULus / 10 A CSA)
    assert parts['j_mains']['mpn'] == '1714971' and parts['j_mains']['footprint'] == 'temper:Phoenix_MKDS-5-2-9.52_1714971'
    # stage 35 (candidate 35): the coil terminals are REDCUBE SMT WP-SMBU 7466004R (the THR 74650074 needs a 1.6-2.0 mm board)
    assert all(parts[p]['mpn'] == '7466004R' and parts[p]['footprint'] == 'temper:Wuerth_REDCUBE-SMT_WP-SMBU_7466004R'
               for p in ('j_coil', 'j_coil_return'))
    for leg in ('leg_a', 'leg_b'):   # stage 26 (DECISIONS 28): low-ESR SVPC variant, same can
        assert parts[f'{leg}.bias_h.cbulk']['mpn'] == parts[f'{leg}.bias_l.cbulk']['mpn'] == '6SVPC220MV'
    # stage 49 (OPEN-ITEMS S23, B'-1.02 V): R33 7.5 k, R34 16 k, R35 11 k (stage 15: 10 k / 12.6 k / 11.7 k)
    assert (parts['r_ocp_ref']['mpn'], parts['r_ocp_sense']['mpn'], parts['r_th_top']['mpn'], parts['r_th_bot']['mpn']) == \
        ('RT0603BRD0710KL', 'RT0603BRD077K5L', 'RT0603BRD0716KL', 'RT0603BRD0711KL')
    # stage 38 (candidate 23, DECISIONS 47): PS1 deleted (the controller logic runs from PS3 over its J13); PS2 is the
    # MEAN WELL MPM-20-24 (touch current < 80 uA / 264 VAC) on the unchanged IRM-20 / Case 219A footprint
    assert 'ps_selv' not in parts and not any(part.get('mpn', '').startswith('IRM-') for part in parts.values())
    assert parts['ps_gate']['mpn'] == 'MPM-20-24' and parts['ps_gate']['footprint'] == 'Converter_ACDC:Converter_ACDC_MeanWell_IRM-20-xx_THT'
    assert parts['f_blw']['mpn'] == '3403.0279.23' and parts['j_blw_ac']['mpn'] == 'B2P3-VH(LF)(SN)'   # stage 16; stage 28 UMT-H 1.5 kA
    assert parts['r_blw']['mpn'] == 'AC05000001507JAC00'   # stage 28: J11 fault-current limiter
    for leg in ('leg_a', 'leg_b'):   # stage 29 (DECISIONS 31): 2EDR8259X drivers with 8.2 ohm gates
        assert parts[f'{leg}.driver']['mpn'] == '2EDR8259XXUMA1'
        # stage 42 (candidate 39, DECISIONS 54): 68 ohm 2512 turn-on resistors and 4.7 nF C0G Cgs
        assert parts[f'{leg}.r_gh']['mpn'] == parts[f'{leg}.r_gl']['mpn'] == '25121WF680JT4E'
        assert parts[f'{leg}.r_gh']['footprint'] == parts[f'{leg}.r_gl']['footprint'] == 'Resistor_SMD:R_2512_6332Metric'
        assert parts[f'{leg}.cgs_h']['mpn'] == parts[f'{leg}.cgs_l']['mpn'] == 'GRM1885C1H472JA01D'
        # stage 43: the 1 kV snubbers are the ordered YAGEO part (C113872); GRM31A5C3A102JW01D is not a Murata part
        assert parts[f'{leg}.c_snub_h']['mpn'] == parts[f'{leg}.c_snub_l']['mpn'] == 'CC1206JKNPOCBN102'
        assert parts[f'{leg}.c_snub_h']['footprint'] == parts[f'{leg}.c_snub_l']['footprint'] == 'Capacitor_SMD:C_1206_3216Metric'
    assert parts['r_shunt']['mpn'] == 'CSS2H-2512R-1L00F' and parts['r_shunt']['footprint'] == 'temper:R_Shunt_Bourns_CSS2H-2512_Kelvin'   # stage 17 (DECISIONS 17)
    assert parts['r_ct_hi_top']['mpn'] == parts['r_ct_lo_bot']['mpn'] == 'RT0603BRD072K21L'
    assert all(parts[f'c_ref_xfer_{i}']['mpn'] == parts['c_fault_or']['mpn'] == 'CC0603KRX7R9BB104' for i in range(1, 16))   # stage 19b; 5: stage 40; 6-12: stage 44; 13-15: stage 48
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
    # stage 30 (DECISIONS 33): the heartbeat (U32) carries the LS and HS-A verdicts (HS-A via a default-LOW ISO6721FB
    # link); stage 40 (candidate 30a): HS-B's too, on its own default-LOW ISO6721FB link and vote diode (D20), so U32 is the
    # group's only HOT -> SELV crossing; the SELV NAND's gate input is held high (rgate); no opto in the monitor group
    assert parts['hb.iso']['mpn'] == 'CA-IS3720HW' and parts['u_iso']['mpn'] == 'CA-IS3720HW'   # stage 31 (DECISIONS 34)
    assert parts['bias_ha.link']['mpn'] == parts['bias_hb.link']['mpn'] == 'ISO6721FBDR' and 'bias_hb.verdict' not in parts
    assert parts['hb.vote']['mpn'] == parts['hb.vote_b']['mpn'] == 'BAT54S-7-F' and parts['hb.rgate']['mpn'] == '0603WAF1002T5E'
    assert parts['hb.buf']['mpn'] == 'SN74LVC1G132DBVR'
    assert parts['hb.cp1']['mpn'] == parts['hb.cp2']['mpn'] == 'C0603C102J5GACTU' and parts['hb.rbleed']['mpn'] == 'RT0603BRD0749K9L'
    assert not any(path.endswith(('.rnotice', '.dnotice', '.qnotice', '.rbase')) for path in parts)
    assert 'bias_or' not in parts and 'r_bias_flt' not in parts and 'c_bias_flt' not in parts
    assert sum(part.get('mpn') == 'CL32B106KBJNNNE' for part in parts.values()) == 24 and not any(part.get('mpn') == 'UMK325AB7106KM-T' for part in parts.values())
    assert parts['r_bf']['mpn'] == '0603WAF1001T5E' and parts['c_bf']['mpn'] == 'CL10C101JB8NNNC'
    # stage 45 (OPEN-ITEMS S16, DECISIONS 59, option 1c-4420): TL431B reference, halfref 4.42 k / 10 k, re-centred taps
    # (validation-results/11-candidates/c45-s16-monitor; bands re-derived there from these exports)
    # stage 46 (S17 hot copper; c46-monitor-grades): the 125 C grades of the same pinouts, TL431BQDBZR and LM2901BIDR
    s45 = {'reference': ('TL431BQDBZR', None), 'monitor': ('LM2901BIDR', None), 'rref': ('RC1206FR-072K2L', '2.2kohm'),
           'rhalf_top': ('RT0603BRD074K42L', '4.42kohm'), 'rhalf_bot': ('RT0603BRD0710KL', '10kohm'),
           'ruv_top': ('RT0603BRD07750RL', '750ohm'), 'ruv_bot': ('RT0603BRD0710KL', '10kohm'),
           'rov_top': ('RT0603BRD072K94L', '2.94kohm'), 'rov_bot': ('RT0603BRD0710KL', '10kohm'),
           'rspanuv_top': ('RT0603BRD0790K9L', '90.9kohm'), 'rspanuv_bot': ('RT0603BRD0711KL', '11kohm'),
           'rspanov_top': ('RT0603BRD07104KL', '104kohm'), 'rspanov_bot': ('RT0603BRD0711KL', '11kohm')}
    for base in ('monitor_ls', 'bias_ha.monitor', 'bias_hb.monitor'):
        for key, (mpn, value) in s45.items():
            part = parts[f'{base}.{key}']
            assert part['mpn'] == mpn and part.get('value') == value, (base, key, part)
            assert part['footprint'] == ('Package_TO_SOT_SMD:SOT-23' if key == 'reference' else
                                         'Package_SO:SOIC-14_3.9x8.7mm_P1.27mm' if key == 'monitor' else
                                         'Resistor_SMD:R_1206_3216Metric' if key == 'rref' else 'Resistor_SMD:R_0603_1608Metric')
    # stage 47 (S17 hot copper; c47-ref25-grade): REF25 on the extended-range LM4050AEM3-2.5 (TA -40..125 C, SNOS455H
    # 5.3 p.5), the LM4040A25I's DBZ pinout (1 K, 2 A, 3 no connection) on the same SOT-23 pads
    assert parts['u_ref']['mpn'] == 'LM4050AEM3-2.5/NOPB' and parts['u_ref']['footprint'] == 'Package_TO_SOT_SMD:SOT-23'
    for base in ('monitor_ls', 'bias_ha', 'bias_hb', 'hb'):
        assert not any(path.startswith(base + '.') and part.get('mpn') == 'VO617A-3X017T' for path, part in parts.items())
    # stage 48 (OPEN-ITEMS S19, B13 H1 / H2; c48-ldo-en-ref-watch): the four TPS70950s on the Q1 grade (SLVSCE6D, +-1 %
    # to 125 C) with EN from 100 k / 27 k dividers; the REF25 watchdog 63.4 k / 11.7 k (0.1 %); the 220 k J4.1 readback
    for base in ('', 'monitor_ls.', 'bias_ha.monitor.', 'bias_hb.monitor.'):
        ldo, top, bot = (('u_ldo', 'r_ldo_en_top', 'r_ldo_en_bot') if not base else
                         (base + 'ldo5', base + 'rldo_en_top', base + 'rldo_en_bot'))
        assert parts[ldo]['mpn'] == 'TPS70950QDBVRQ1' and parts[ldo]['footprint'] == 'Package_TO_SOT_SMD:SOT-23-5'
        assert (parts[top]['mpn'], parts[top]['value']) == ('0603WAF1003T5E', '100kohm'), top
        assert (parts[bot]['mpn'], parts[bot]['value']) == ('0603WAF2702T5E', '27kohm'), bot
    assert (parts['r_ref_wd_top']['mpn'], parts['r_ref_wd_bot']['mpn']) == ('RT0603BRD0763K4L', 'TNPW060311K7BEEA')
    assert parts['r_bias_good_j4']['mpn'] == 'RC1206FR-07220KL' and parts['r_bias_good_j4']['value'] == '220kohm'
    assert not any(part.get('mpn') == 'TPS70950DBVR' for part in parts.values())
    result = {'components': len(parts), 'source_hashes_match': True,
              'two_frozen_exports_identical': True, 'native20_protection_parts_retained': True,
              'RECOM_only_hs_bias_modules': True, 'no_bootstrap': True, 'monitor_crossing_single_ISO7710_heartbeat': True, 'source_sha256': resolved['source_sha256']}
    (Path(__file__).parent / 'source-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
