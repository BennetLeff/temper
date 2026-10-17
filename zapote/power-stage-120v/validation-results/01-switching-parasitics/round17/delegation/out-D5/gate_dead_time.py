"""D-5 audit evidence, not a firmware implementation or hardware qualification.

Run from any directory with Python 3.12. Reads only tracked source/board inputs;
stdout is the evidence. DT estimates reproduce D-1's stated interpolation.
"""
from __future__ import annotations

import hashlib
import platform
from pathlib import Path
import re
import runpy
import subprocess

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '.git').exists())
BASE = 'f9b13b483d6d4ed52439d4da419c7670bab6966c'
POWER = Path('zapote/power-stage-120v')
ROUND = POWER / 'validation-results/01-switching-parasitics/round17'
HAL = Path('firmware/components/hal/esp32/hal_pwm_esp32.c')


def read(path: Path) -> str:
    data = (ROOT / path).read_bytes()
    print(f'SHA256 {hashlib.sha256(data).hexdigest()} {path}')
    return data.decode()


def source_hits(path: Path, pattern: str) -> None:
    for number, line in enumerate((ROOT / path).read_text().splitlines(), 1):
        if re.search(pattern, line):
            print(f'{path}:{number}: {line.strip()}')


def main() -> None:
    print(f'INPUT REVISION: {BASE}')
    print(f'RUNTIME: Python {platform.python_version()}; GPT-6 Astra / OpenAI')
    inputs = [HAL, Path('firmware/components/hal/include/hal_types.h'),
              Path('firmware/components/hal/esp32/hal_init.c'),
              Path('firmware/components/safety/pwm_guard.c'),
              Path('firmware/components/safety/include/pwm_guard.h'),
              Path('firmware/components/hal/include/temper_pins.h'),
              Path('firmware/main/main.c'), Path('firmware/config.yaml'),
              Path('firmware/config.h'), Path('firmware/sdkconfig.defaults'),
              Path('firmware/CMakeLists.txt'), Path('.github/workflows/release-artifacts.yml'),
              Path('elec/src/main.ato'), Path('elec/src/modules.ato'),
              POWER / 'frozen/default.net', POWER / 'frozen/default.csv',
              ROUND / 'delegation/out-D1/dead_time.py']
    for path in inputs:
        read(path)
        original = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
        if original != (ROOT / path).read_bytes():
            raise ValueError(f'Input changed since cited revision: {path}')
    for path in [POWER / 'native-17/section.kicad_pcb', Path('datasheets/ucc21550.pdf')]:
        data = (ROOT / path).read_bytes()
        print(f'SHA256 {hashlib.sha256(data).hexdigest()} {path}')
        if data != subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT):
            raise ValueError(f'Input changed since cited revision: {path}')

    print('\nFIRMWARE SOURCE EVIDENCE')
    source_hits(HAL, r'RESOLUTION_HZ|delay_ticks|set_dead_time|dead_time_ns|invert_output|return HAL_OK')
    source_hits(Path('firmware/components/safety/include/pwm_guard.h'), r'DEADTIME_NS')
    source_hits(Path('firmware/components/safety/pwm_guard.c'), r'dead_time_ns|get_state')
    source_hits(Path('firmware/main/main.c'), r'mcpwm_init|hal_init')
    source_hits(Path('firmware/components/hal/esp32/hal_init.c'), r'hal_pwm =')
    source_hits(Path('firmware/components/hal/include/temper_pins.h'), r'PIN_PWM')
    source_hits(Path('.github/workflows/release-artifacts.yml'), r'espressif/idf')

    print('\nTRACKED PRODUCTION C AUDIT (comments stripped; not proof about external binaries)')
    cpaths = subprocess.check_output(['git', 'ls-files', 'firmware'], cwd=ROOT, text=True).splitlines()
    application_hits: list[str] = []
    for name in cpaths:
        if not name.endswith('.c') or name.startswith('firmware/test/') or '/mock/' in name:
            continue
        text = (ROOT / name).read_text()
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(r'hal_pwm\s*->\s*(?:init|set_dead_time)\s*\(|hal_pwm_config_t\s+\w', line):
                application_hits.append(f'{name}: {line.strip()}')
    print('application init/set_dead_time/config instances:', application_hits)
    if application_hits != [f'{HAL}: hal_pwm_config_t config;']:
        raise ValueError('New application PWM owner: redo timing audit')
    print('Only HAL internal storage; no application initializer or calls found.')

    hal = (ROOT / HAL).read_text()
    hz = int(re.search(r'#define MCPWM_TIMER_RESOLUTION_HZ\s+(\d+)', hal)[1])
    tick = 1e9 / hz
    if '.posedge_delay_ticks = delay_ticks' not in hal or '.negedge_delay_ticks = delay_ticks' not in hal:
        raise ValueError('HAL edge programming changed')
    print(f'\nCONFIGURATION ARITHMETIC: tick = {tick:g} ns; ticks = floor(ns * {hz // 1000000} / 1000)')
    print('init accepts uint16 0..65535 ns, with no minimum clamp; setter clamps below 500 ns.')
    print('requested_ns ticks rounded_ns (arithmetic only, not physical dead time)')
    for ns in (0, 1, 12, 13, 300, 307, 348, 391, 499, 500, 501, 1000, 65535):
        ticks = ns * (hz // 1000000) // 1000
        print(f'{ns:5} {ticks:4} {ticks * tick:9.3f}')

    # Reuse the already committed D-1 S-expression reader; no workspace imports.
    d1 = runpy.run_path(str(ROOT / ROUND / 'delegation/out-D1/dead_time.py'))
    child, children, sexpr = d1['child'], d1['children'], d1['sexpr']
    nets = {child(n, 'name')[1]: {f'{child(p, "ref")[1]}.{child(p, "pin")[1]}'
            for p in children(n, 'node')} for n in children(child(sexpr(ROOT / POWER / 'frozen/default.net'), 'nets'), 'net')}
    pcb: dict[str, set[str]] = {}
    for fp in children(sexpr(ROOT / POWER / 'native-17/section.kicad_pcb'), 'footprint'):
        props = {p[1]: p[2] for p in children(fp, 'property')}
        for pad in children(fp, 'pad'):
            for net in children(pad, 'net'):
                pcb.setdefault(net[-1], set()).add(f'{props["Reference"]}.{pad[1]}')
    print('\nPOWER BOARD PATHS: netlist membership == native-17 pad assignments')
    for name, expected in [('pwm_ha', {'J4.5', 'U1.1'}), ('pwm_la', {'J4.6', 'U1.2'}),
                           ('pwm_hb', {'J4.7', 'U2.1'}), ('pwm_lb', {'J4.8', 'U2.2'})]:
        if nets[name] != expected or pcb[name] != expected:
            raise ValueError(f'Board/netlist contradiction: {name}; STOP')
        print(f'{name}: {", ".join(sorted(expected))}; no intervening component')
    print('Controller-to-J4 cable, GPIO edge/threshold skew: UNKNOWN, not zero.')

    # TI SLUSE89C p10; D-1 interpolation and tolerance assumptions.
    rmin = 39 * .99 * (1 - 100e-6 * 125)
    rmax = 39 * 1.01 * (1 + 100e-6 * 125)
    dmin = 167 + (rmin - 20) * (399 - 167) / 30
    dmax = 203 + (rmax - 20) * (487 - 203) / 30
    print(f'\nD-1 ESTIMATE: min={dmin:.6f}, nominal={8.6 * 39 + 13:.6f}, max={dmax:.6f} ns')
    print('Unloaded, datasheet-condition propagation 26/33/45 ns; same-edge mismatch cold 6.5 ns, warm 5 ns; PWD 5 ns.')
    print('Opposite-edge skew <= min(45-26, mismatch+PWD): cold 11.5 ns; warm 10 ns.')
    print('CONDITIONAL ESTIMATE ONLY: G = max(DTS, F + path_skew + propagation_skew).')
    print('DTS is already an output interval: do NOT subtract channel mismatch from DTS a second time.')
    print('F is measured INA/INB threshold non-overlap below; path_skew = 0 by scenario, not a board fact.')
    print('F_ns temperature edge min_est_ns max_est_ns')
    for f in (0, 300, 348, 500, 1000):
        for label, mismatch in [('cold', 6.5), ('warm', 5.0)]:
            skew = min(45 - 26, mismatch + 5)
            for edge in ('HSoff-LSon', 'LSoff-HSon'):
                print(f'{f:4} {label:4} {edge:11} {max(dmin, f-skew):10.3f} {max(dmax, f+skew):10.3f}')
    print('\nACTUAL BOARD OUTPUT TIMING: U1/U2, both edges: minimum UNKNOWN; maximum UNKNOWN.')
    print('500 ns minimum verified: NO. Below 348 ns excluded: NO. Retain 307 ns stress case.')
    print('No Rust/native/firmware build, circuit edit, simulation, or physical measurement performed.')


if __name__ == '__main__':
    main()
