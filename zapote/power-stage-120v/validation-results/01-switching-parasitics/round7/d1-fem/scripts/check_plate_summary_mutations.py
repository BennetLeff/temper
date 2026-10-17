"""Check that changed sources and misleading logs cannot become solved plate results."""

import json
import math
import tempfile
from pathlib import Path

import summarize_plates as summary

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'plates-box0p25-far12-m20'
SUFFIXES = ('-mesh.json', '-source.json', '.sif', '.log', '-exit.txt')
POSITIVE_LOG = ('Magnetic Field Energy: 1.5e-9\nMagnetic Coenergy: 1.5e-9\n'
                'MAIN: *** Elmer Solver: ALL DONE ***\n')


def main() -> None:
    original = {suffix: (ROOT / 'raw/fixtures' / (LABEL + suffix)).read_text()
                for suffix in SUFFIXES}
    original['.log'] = POSITIVE_LOG
    source = json.loads(original['-source.json'])
    mutations = []
    mutations.append(('missing audit', '-source.json', None))
    for name, cuts in [('2 A current', [2., 2., 2.]),
                       ('NaN current', [1., math.nan, 1.])]:
        changed = dict(source, sampled_cut_currents_A=dict(zip(('a', 'b', 'c'), cuts, strict=True)))
        mutations.append((name, '-source.json', json.dumps(changed)))
    for key, value in [('mesh', 'wrong.msh'), ('sif', 'wrong.sif'),
                       ('constant_source_density_A_per_m', 200)]:
        mutations.append((f'wrong {key}', '-source.json', json.dumps(dict(source, **{key: value}))))
    for axis, before, after in [(3, '100.0', '200.0'), (1, '0.0', '1.0')]:
        old = f'Magnetic Field Strength {axis} = Real {before}'
        assert old in original['.sif']
        mutations.append((f'changed SIF axis {axis}', '.sif',
                          original['.sif'].replace(old, old.replace(before, after))))
    mutations.append(('wrong SIF mesh', '.sif', original['.sif'].replace(LABEL, 'other-mesh')))
    for token in ('NaN', 'Inf', '0', '-1e-9'):
        tail = f'Magnetic Field Energy: {token}\nMagnetic Coenergy: {token}\n'
        mutations.append((f'final energy {token}', '.log', POSITIVE_LOG + tail))
    for marker in ('ERROR:: failed', 'FATAL', 'STOP 1', 'Error occurred in umf4num: -1'):
        mutations.append((marker, '.log', POSITIVE_LOG + marker))
    mutations.extend([
        ('exit nonzero', '-exit.txt', '1\n'),
        ('missing completion', '.log', POSITIVE_LOG.replace('ALL DONE', 'not complete')),
        ('energy mismatch', '.log', POSITIVE_LOG + 'Magnetic Coenergy: 1.7e-9\n'),
    ])
    passed = []
    with tempfile.TemporaryDirectory(prefix='ps-r7-summary-mutations-') as directory:
        summary.RAW = Path(directory) / 'raw/fixtures'
        summary.RAW.mkdir(parents=True)
        for name, suffix, content in [('baseline', '.log', POSITIVE_LOG), *mutations]:
            for extension, text in original.items():
                (summary.RAW / (LABEL + extension)).write_text(text)
            target = summary.RAW / (LABEL + suffix)
            if content is None:
                target.unlink()
            else:
                target.write_text(content)
            try:
                result = summary.summarize(LABEL)
                solved = result['status'].startswith('solved_')
            except (ValueError, KeyError, FileNotFoundError):
                solved = False
            if solved != (name == 'baseline'):
                raise AssertionError(f'{name}: unexpected solved={solved}')
            passed.append(name)
        for extension, text in original.items():
            (summary.RAW / (LABEL + extension)).write_text(text)
        final_log = POSITIVE_LOG + 'Magnetic Field Energy: 1.55e-9\nMagnetic Coenergy: 1.55e-9\n'
        (summary.RAW / (LABEL + '.log')).write_text(final_log)
        assert math.isclose(summary.summarize(LABEL)['inductance_nH'], 3.1)
        passed.append('last valid energy replaces earlier energy')
    print(json.dumps({'checks_passed': len(passed), 'checks': passed}, indent=2))


if __name__ == '__main__':
    main()
