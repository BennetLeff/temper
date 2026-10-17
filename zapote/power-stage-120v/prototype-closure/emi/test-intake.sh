#!/bin/sh
# Exercise the intake integrity gate without running new simulations.
set -eu
: "${TEMPER_PYTHON:=/Users/bennet/Miniforge3/bin/python3}"
export PYTHONDONTWRITEBYTECODE=1
"$TEMPER_PYTHON" - "$0" "$1" "$2" <<'PY'
if not __debug__:
    raise RuntimeError('PYTHONOPTIMIZE must be disabled: evidence checks require assertions')

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve().parent
checkout = Path(sys.argv[2]).resolve()
output = Path(sys.argv[3]).resolve()
assert not output.is_relative_to(checkout)
with tempfile.TemporaryDirectory(prefix='temper-emi-negative-') as temporary:
    temporary = Path(temporary)
    shutil.copytree(source, temporary / 'intake')
    manifest = json.loads((temporary / 'intake/intake-manifest.json').read_text())
    name = manifest['copied_verbatim'][0]['path']
    target = temporary / 'intake/inputs' / name
    target.write_bytes(target.read_bytes() + b'\n')
    result_dir = temporary / 'out'
    result_dir.mkdir()
    (result_dir / 'verification.json').write_text('{"status":"PASS"}')
    result = subprocess.run(['sh', str(temporary / 'intake/verify-intake.sh'), str(checkout), str(result_dir)], capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert f'AssertionError: {name}' in result.stderr, result.stderr
    assert json.loads((result_dir / 'verification.json').read_text())['status'] == 'INCOMPLETE'
    assert not (result_dir / 'fresh-ac').exists()
    shutil.copytree(source, temporary / 'intake', dirs_exist_ok=True)
    manifest_path = temporary / 'intake/intake-manifest.json'
    wrong_provenance = json.loads(manifest_path.read_text())
    wrong_provenance['source_provenance_sha256'] = '0' * 64
    manifest_path.write_text(json.dumps(wrong_provenance))
    provenance_result = subprocess.run(['sh', str(temporary / 'intake/verify-intake.sh'), str(checkout), str(result_dir)], capture_output=True, text=True, timeout=60)
    assert provenance_result.returncode != 0
    assert 'AssertionError: source provenance identity mismatch' in provenance_result.stderr, provenance_result.stderr
    assert not (result_dir / 'fresh-ac').exists()
    optimized_output = temporary / 'optimized-output'
    optimized_output.mkdir()
    (optimized_output / 'verification.json').write_text('{"status":"PASS"}')
    optimized = subprocess.run(['sh', str(source / 'verify-intake.sh'), str(checkout), str(optimized_output)], env={**os.environ, 'PYTHONOPTIMIZE': '1'}, capture_output=True, text=True, timeout=60)
    assert optimized.returncode != 0
    assert 'RuntimeError: PYTHONOPTIMIZE must be disabled' in optimized.stderr, optimized.stderr
    assert 'PASS' not in optimized.stdout
    assert json.loads((optimized_output / 'verification.json').read_text())['status'] == 'INCOMPLETE'
    assert not (optimized_output / 'fresh-ac').exists()
    wrong_checkout = source.parents[3]
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=wrong_checkout, text=True).strip() != manifest['source_commit']
    wrong_head_output = temporary / 'wrong-head-output'
    wrong_head_output.mkdir()
    (wrong_head_output / 'verification.json').write_text('{"status":"PASS"}')
    wrong_head = subprocess.run(['sh', str(source / 'verify-intake.sh'), str(wrong_checkout), str(wrong_head_output)], capture_output=True, text=True, timeout=60)
    assert wrong_head.returncode != 0
    assert 'source HEAD mismatch' in wrong_head.stderr, wrong_head.stderr
    assert json.loads((wrong_head_output / 'verification.json').read_text())['status'] == 'INCOMPLETE'
    assert not (wrong_head_output / 'fresh-ac').exists()
    forbidden_output = checkout / 'temper-emi-forbidden-output-test'
    assert not forbidden_output.exists()
    forbidden = subprocess.run(['sh', str(source / 'verify-intake.sh'), str(checkout), str(forbidden_output)], env={**os.environ, 'PYTHONOPTIMIZE': '1'}, capture_output=True, text=True, timeout=60)
    assert forbidden.returncode != 0
    assert 'Never write into the source checkout' in forbidden.stderr, forbidden.stderr
    assert not forbidden_output.exists()
    receipt = {'status': 'PASS', 'tamper_detected_before_simulation': True, 'source_provenance_pin_enforced': True, 'stale_success_invalidated': True, 'optimized_python_invalidates_stale_success': True, 'wrong_head_invalidates_stale_success': True, 'foreign_output_rejected_without_writes': True, 'failure': result.stderr.splitlines()[-1]}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'negative-check.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
PY
