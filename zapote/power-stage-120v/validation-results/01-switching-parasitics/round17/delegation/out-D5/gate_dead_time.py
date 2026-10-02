"""D5 bounded evidence replay, not a firmware emulator or engineering rule.

Only Python standard library. No network, build, board writes or .so imports.
The SDK ownership trace translates the cited guard predicates; it does not
execute SDK C or assert an observed waveform. Conditional timing is labelled.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import re
import runpy

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / '.git').exists())
BASE = '1f09223516cc37d00f73b5e5e6d33a0197d7a30d'


def main() -> None:
    print(f'Source revision: {BASE}')
    print(f'Runtime: Python {platform.python_version()}; GPT-6 Astra/OpenAI')
    manifest = json.loads((HERE / 'input-hashes.json').read_text())
    for relative, expected in manifest.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Input drift: {relative}: {actual} != {expected}')
        print(f'SHA256 {actual}  {relative}')
    hal = (ROOT / 'firmware/components/hal/esp32/hal_pwm_esp32.c').read_text()
    clock = int(re.search(r'#define MCPWM_TIMER_RESOLUTION_HZ\s+(\d+)', hal)[1])
    assert clock == 80_000_000
    print('\nPROGRAMMING ARITHMETIC (not a physical gap)')
    for ns in (0, 1, 12, 13, 300, 307, 348, 500, 1000, 65535):
        ticks = ns * (clock // 1_000_000) // 1000
        print(f'init request {ns:5} ns -> {ticks:4} ticks -> {ticks * 1e9 / clock:8.1f} ns delay')
    print('init permits uint16_t 0..65535 ns; setter clamps below 500 ns')
    print('guard accepts reported 300..1000 ns; it does not measure dead time')
    sources = sorted((ROOT / 'firmware').rglob('*.c')) + sorted((ROOT / 'firmware').rglob('*.h'))
    calls = []
    for path in sources:
        if 'test' in path.relative_to(ROOT / 'firmware').parts:
            continue
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(), flags=re.S)
        for match in re.finditer(r'hal_pwm\s*->\s*(init|set_dead_time)\s*\(', text):
            calls.append(f'{path.relative_to(ROOT)}: {match[0]}')
    print(f'Production direct hal_pwm->init / ->set_dead_time calls: {calls}')
    assert not calls, 'Revisit caller analysis; this scan is lexical, not a call-graph proof'
    sdk = (HERE / 'source/mcpwm_gen-v5.3.c').read_text()
    for predicate in ('oper->posedge_delay_owner != in_generator',
                      'oper->negedge_delay_owner != in_generator',
                      'ESP_RETURN_ON_FALSE(!delay_module_conflict, ESP_ERR_INVALID_STATE'):
        assert predicate in sdk
    print('\nSDK v5.3 RESOURCE-GUARD TRANSLATION (not executed firmware)')
    pos_owner: str | None = None
    neg_owner: str | None = None
    for gen in ('HS', 'LS'):
        conflict = ((pos_owner is not None and pos_owner != gen)
                    or (neg_owner is not None and neg_owner != gen))
        if not conflict:
            pos_owner = neg_owner = gen
        print(f'nonzero both-edge request from {gen}: '
              f'{"ESP_ERR_INVALID_STATE" if conflict else "ESP_OK"}; '
              f'owners RED={pos_owner} FED={neg_owner}')
    print('HAL init only warns on LS failure; stores request and returns HAL_OK')
    print('HAL setter returns HAL_ERROR after possible HS change; no rollback')
    d1 = runpy.run_path(str(HERE.parent / 'out-D1/dead_time.py'))
    netfile = ROOT / 'zapote/power-stage-120v/frozen/default.net'
    nets = {d1['child'](n, 'name')[1]: {
        f'{d1["child"](node, "ref")[1]}.{d1["child"](node, "pin")[1]}'
        for node in d1['children'](n, 'node')}
        for n in d1['children'](d1['child'](d1['sexpr'](netfile), 'nets'), 'net')}
    print('\nFROZEN POWER-BOARD INPUT NET MEMBERSHIP')
    for net, expected in (('pwm_ha', {'J4.5', 'U1.1'}), ('pwm_la', {'J4.6', 'U1.2'}),
                          ('pwm_hb', {'J4.7', 'U2.1'}), ('pwm_lb', {'J4.8', 'U2.2'})):
        assert nets[net] == expected, f'Connectivity changed: {net}'
        print(f'{net}: {", ".join(sorted(nets[net]))}; no discrete inline component')
    rmin = d1['R_KOHM'] * (1-d1['TOL']) * (1-d1['TCR']*125)
    rmax = d1['R_KOHM'] * (1+d1['TOL']) * (1+d1['TCR']*125)
    lo = 167 + (rmin-20)*(399-167)/30
    hi = 203 + (rmax-20)*(487-203)/30
    print(f'\nD1 interpolated output DTS ESTIMATE: {lo:.3f}..{hi:.3f} ns; NOT limits')
    print('CONDITIONAL INPUT-DOMINATED OUTPUT DTS: p10 TABLE CONVENTION')
    print('Assume correct 500 ns VIL-to-VIH gap at each INA/INB edge, zero path skew,')
    print('nominal clock, datasheet test loads/supplies, no DT extension.')
    for edge in ('HS-off -> LS-on', 'LS-off -> HS-on'):
        for band, dm in (('-40..-10 C', 6.5), ('-10..150 C', 5.0)):
            skew = min(45-26, dm+5)
            print(f'{edge}, {band}: {500-skew:.1f}..{500+skew:.1f} ns (conditional, output90%-to-10%)')
    print('Use explicit p10 90%/10% definitions; p18 Fig6-1 ideal edges do not label 50%.')
    print(f'Conditional max-stack with D1 ESTIMATE: {max(488.5,lo):.3f}..{max(511.5,hi):.3f} ns.')
    print('This assumes a correct 500 ns input gap and transfer of datasheet conditions.')
    print('\nAUTHORITATIVE REVIEW RESULT: UNESTABLISHED for both edges on both legs.')
    print('Actual output/gate min/max unavailable; cannot exclude <348 ns or 307 ns.')
    print('Missing: executed controller identity/config, cable/pad skew, loaded timing,')
    print('39 kohm guaranteed DTS. No firmware or board repair performed.')


if __name__ == '__main__':
    main()
