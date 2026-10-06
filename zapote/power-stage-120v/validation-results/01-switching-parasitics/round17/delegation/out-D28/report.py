"""Render saved measurements and Rust verdicts as review tables; no new criteria."""
from __future__ import annotations
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def number(value: object, digits: int = 3) -> str:
    return '—' if value is None else f'{float(value):.{digits}f}'

def main() -> None:
    summary = json.loads((HERE / 'summary.json').read_text())
    with (HERE / 'verdicts.csv').open() as stream:
        verdicts = {r['label']: r for r in csv.DictReader(stream)}
    captures = summary['captures']
    lines = ['# Recorded D-28 captures', '',
             'All rows are recorded attempts, not interpolated operating permissions. '
             'INDETERMINATE includes aborted, unsettled, missing-refinement and failed-refinement cases. '
             'The per-transition screens below remain provisional unless `verdicts.csv` qualifies the capture. '
             'The original-startup `v…` attempts and the legacy-matrix 35 kHz anchor are separate from the '
             'native-19 complementary-startup 50 kHz phase campaign. See [METHOD.md](METHOD.md).', '',
             'Power is DC tank-resistor power. The overlap column is the four-transition positive-terminal-power '
             'proxy at 50 kHz (35 kHz for the anchor), not dissipated heat or efficiency. '
             '[Definitions and sources](METHOD.md#switching-measurements-and-limits).', '',
             '| Capture / raw evidence | Bus V | R Ω | Phase ° | Step ns | Transient / periodic | Tank W | Overlap proxy W | Verdict |',
             '|---|---:|---:|---:|---:|---|---:|---:|---|']
    for r in captures:
        name=r['label']
        lines.append(f"| [{name}](runs/{name}/result.json) | {r['bus_V']} | {r['R_ohm']} | {r['phase_deg']} | {r['step_ns']} | {r['transient']} / {r['periodic']} | {number(r['tank_power_W'])} | {number(r['bridge_overlap_proxy_W'])} | {verdicts[name]['verdict']} |")
    lines += ['', '## Per-transition provisional screens', '',
              'Edge 0 turns on the high-side device; edge 1 turns on the low-side device. '
              'Positive current has the desired inductive polarity. CT delay is from the outgoing off command '
              'to the next appropriate current zero; an absent value does not pass the inhibit proposal. '
              'VDS peak is the maximum of both devices in the leg over the full cycle. '
              'Gate peak covers the outgoing device’s commanded-off interval, including other-leg disturbances.', '',
              '| Capture / final replay | Leg, edge | Inductive A | Incoming VDS V | ZVS screen | Off gate V | <3 / <1.9 V | Full-cycle VDS V | <520 V | CT delay ns | Overlap µJ |',
              '|---|---|---:|---:|---|---:|---|---:|---|---:|---:|']
    for r in summary['events']:
        name=r['label']
        lines.append(f"| [{name}](runs/{name}/replay/analysis.json) | {r['leg']}, {r['edge']} | {number(r['current_inductive_A'])} | {number(r['incoming_vds_V'])} | {r['zvs']} | {number(r['off_gate_V'])} | {r['screen3']} / {r['screen1p9']} | {number(r['vds_peak_V'])} | {r['screen520']} | {number(r['ct_zero_delay_ns'],1)} | {number(r['overlap_uJ'])} |")
    (HERE/'TABLES.md').write_text('\n'.join(lines)+'\n')
    lines=['# Numerical qualification attempts', '',
           'These counts forward D-22’s unchanged significant/weak spectral acceptance flags. '
           'All 56 terminal checks must pass in both comparisons, along with the periodic RMS check. '
           'A missing comparison cannot qualify a case. See [NUMERICS.md](../out-D22/NUMERICS.md#L7) '
           'and [verdicts.csv](verdicts.csv).', '',
           '| Fine capture | Reference capture | Comparison | Checks passing | Worst significant change dB | Worst weak difference / floor |',
           '|---|---|---|---:|---:|---:|']
    for path in sorted(HERE.glob('*-qualification.json')):
        q=json.loads(path.read_text())
        for kind in ('cycle','step'):
            rows=q.get(kind,[])
            significant=max((r['maximum_significant_line_change_dB'] for r in rows),default=None)
            weak=max((r['maximum_weak_complex_difference_relative_to_floor'] for r in rows),default=None)
            lines.append(f"| [{q['fine']}]({path.name}) | {q['coarse']} | {kind} | {sum(r['passes_0p2dB_target'] for r in rows)}/{len(rows)} | {number(significant,6)} | {number(weak,6)} |")
    (HERE/'CONVERGENCE.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':
    main()
