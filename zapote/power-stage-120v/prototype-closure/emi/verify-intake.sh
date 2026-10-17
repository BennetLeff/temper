#!/bin/sh
# Reuse the pinned D22 analysis; no replacement numerical implementation.
# Usage: sh verify-intake.sh /path/to/ps-r17-d22/temper /absolute/output/directory
set -eu
: "${TEMPER_PYTHON:=/Users/bennet/Miniforge3/bin/python3}"
export PYTHONDONTWRITEBYTECODE=1
"$TEMPER_PYTHON" - "$1" "$2" "$0" <<'PY'
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

checkout = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
source = checkout / 'zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D22'
expected_commit = '7d1c97b92c0ed42be1c28a32d4ccaadd512d2238'
if output.is_relative_to(checkout):
    raise RuntimeError('Never write into the source checkout')
output.mkdir(parents=True, exist_ok=True)
(output / 'verification.json').write_text(json.dumps({'status': 'INCOMPLETE', 'expected_source_commit': expected_commit, 'attempted_source_checkout': str(checkout)}) + '\n')
if not __debug__:
    raise RuntimeError('PYTHONOPTIMIZE must be disabled: evidence checks require assertions')
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() == expected_commit, 'source HEAD mismatch'
sys.path.insert(0, str(source))

def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

intake = Path(sys.argv[3]).resolve().parent
intake_manifest = json.loads((intake / 'intake-manifest.json').read_text())
assert intake_manifest['source_commit'] == expected_commit
for record in intake_manifest['copied_verbatim']:
    assert digest(intake / 'inputs' / record['path']) == record['sha256'], record['path']
    assert digest(checkout / record['source_path']) == record['sha256'], record['source_path']
assert digest(source / 'provenance.json') == intake_manifest['source_provenance_sha256'], 'source provenance identity mismatch'
provenance = json.loads((source / 'provenance.json').read_text())
for group, base in (('inputs', checkout), ('outputs', source)):
    for name, expected in provenance[group].items():
        assert digest(base / name) == expected, (group, name)
import numpy as np
from periodic import analyze, read_binary
from filter_stage import MODEL
from pack_spectra import verify_archive
tests = subprocess.run([sys.executable, '-m', 'unittest', 'test_evidence', '-v'], cwd=source, capture_output=True, text=True, check=True)
(output / 'upstream-tests.log').write_text(tests.stdout + tests.stderr)
print('Source hashes and upstream tests PASS', flush=True)

summary = json.loads((source / 'envelope-summary.json').read_text())
assert summary['numerically_qualified_cases'] == summary['expected_cases'] == 16
assert summary['all_cases_meet_6dB']
selected = set()
for case in summary['cases']:
    selected.add(case['case'])
    result = json.loads((source / 'periodic-runs' / case['case'] / 'result.json').read_text())
    config = result['identity']['config']
    step = config['step']
    previous = {0.25: 0.5, 0.125: 0.25, 0.1: 0.25, 0.0625: 0.125}
    reference = config.get('reference_label')
    if reference is None:
        reference = case['case'].removesuffix(f'-s{step:g}') + f'-s{previous[step]:g}'
    selected.add(reference)
replayed = []
for name in sorted(selected):
    directory = source / 'periodic-runs' / name
    saved = json.loads((directory / 'result.json').read_text())
    assert saved['status'] == 'complete', name
    waves = read_binary(gzip.decompress((directory / 'waves.raw.gz').read_bytes()))
    with tempfile.TemporaryDirectory(prefix='temper-emi-fft-replay-') as temporary:
        temporary = Path(temporary)
        actual = analyze(waves, saved['identity']['params'], temporary)
        assert actual['status'] == saved['status'], name
        for filename in ('fft.npz', 'prior-fft.npz'):
            with np.load(temporary / filename) as a, np.load(directory / filename) as b:
                assert set(a.files) == set(b.files)
                for key in a.files:
                    np.testing.assert_allclose(a[key], b[key], rtol=1e-11, atol=1e-12)
    replayed.append({'case': name, 'raw_sha256': digest(directory / 'waves.raw.gz'), 'fft_sha256': digest(directory / 'fft.npz')})
    del waves
    print('Raw replay PASS', name, flush=True)

archives = []
for manifest in ('exploratory-ac-archive.json', 'receiver-spectra-archive.json'):
    for record in json.loads((source / manifest).read_text()):
        archives.append({'archive': record['archive'], 'members_verified': verify_archive(record, root=source)})

# Fresh simulations of both frequencies at the nominal and most limiting
# reported proposed-filter sensitivity, all three coherent source ports.
ac = []
for scenario in ('proposed_nominal', 'old_low_leakage'):
    for frequency in (35000, 60000):
        for port in ('A', 'B', 'DM'):
            name = f'{scenario}-f{frequency}-{port}'
            original = source / 'harmonic-transfer-v3' / name
            run = output / 'fresh-ac' / name
            run.mkdir(parents=True, exist_ok=True)
            (run / 'case.cir').write_bytes(original.with_suffix('.cir').read_bytes())
            (run / '.spiceinit').write_text('set filetype=ascii\n')
            proc = subprocess.run(['/opt/homebrew/bin/ngspice', '-b', '-r', 'waves.raw', 'case.cir'], cwd=run, capture_output=True, text=True, timeout=60, check=False)
            (run / 'run.log').write_text(proc.stdout + proc.stderr)
            assert proc.returncode == 0, name
            assert not any(s in (proc.stdout + proc.stderr).lower() for s in ('simulation(s) aborted', 'singular matrix', 'fatal error'))
            waves = MODEL['read_raw'](run / 'waves.raw')
            with np.load(original.with_suffix('.npz')) as expected:
                for key in expected.files:
                    np.testing.assert_allclose(waves[key], expected[key], rtol=1e-9, atol=1e-12)
            with gzip.open(run / 'waves.raw.gz', 'wb') as compressed:
                compressed.write((run / 'waves.raw').read_bytes())
            (run / 'waves.raw').unlink()
            ac.append({'case': name, 'deck_sha256': digest(run / 'case.cir'), 'raw_sha256': digest(run / 'waves.raw.gz'), 'status': 'PASS'})
            print('Fresh AC PASS', name, flush=True)

report = {
    'status': 'PASS', 'source_commit': expected_commit,
    'intake_runner_sha256': digest(Path(sys.argv[3]).resolve()),
    'intake_manifest_sha256': digest(intake / 'intake-manifest.json'),
    'intake_files_verified': len(intake_manifest['copied_verbatim']),
    'scope': 'Full recorded source hashes; upstream tests; all 16 selected nonlinear captures and their refinement references replayed; archives verified; 12 selected AC decks freshly simulated. No new nonlinear transient simulation or physical measurement.',
    'inputs_verified': len(provenance['inputs']), 'outputs_verified': len(provenance['outputs']),
    'source_provenance_sha256': digest(source / 'provenance.json'),
    'raw_captures_replayed': replayed, 'archives_verified': archives,
    'fresh_AC_simulations': ac,
    'upstream_envelope_summary_sha256': digest(source / 'envelope-summary.json'),
    'upstream_numerically_qualified_cases': summary['numerically_qualified_cases'],
    'upstream_minimum_proposed_AV_dB': summary['qualified_minimum_proposed_AV_dB'],
    'upstream_minimum_after_1dB_reserve': summary['qualified_minimum_after_reserve_dB'],
    'ngspice': subprocess.check_output(['/opt/homebrew/bin/ngspice', '-v'], text=True),
}
(output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS:', len(replayed), 'raw captures;', len(ac), 'fresh AC decks', flush=True)
PY
