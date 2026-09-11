from pathlib import Path
import hashlib, importlib.util, json, re, shutil, subprocess, sys
root = Path('/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan')
out = root / 'zapote/rtd/unit/evidence/root-circuit-final-review'
out.mkdir(parents=True, exist_ok=True)
receipt_path = root / 'zapote/rtd/unit/evidence/circuit-import-final/receipt.json'
receipt = json.loads(receipt_path.read_text())
for row in receipt['files']:
    assert hashlib.sha256((root / row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
source = root / 'zapote/rtd/circuit'
observed = json.loads((source / 'rtd_observed_faults.json').read_text())
frozen = out / 'inputs'
frozen.mkdir(exist_ok=True)
for name, expected in observed['source_model_hashes'].items():
    p = source / name
    assert hashlib.sha256(p.read_bytes()).hexdigest() == expected, name
    shutil.copy2(p, frozen / name)
result = subprocess.run([sys.executable, str(frozen / 'rtd_observed_faults.py')], check=True, capture_output=True)
assert result.stdout == (source / 'rtd_observed_faults.json').read_bytes()
(out / 'replayed-observations.json').write_bytes(result.stdout)
spec = importlib.util.spec_from_file_location('producer', frozen / 'rtd_observed_faults.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
transient = (frozen / 'rtdin_transient_model_results.txt').read_text()
mutations = {
  'missing_force_plus_endpoints': (mod.transient_observations, re.sub(r'^RTD=.*case=FORCE\+.*\n', '', transient, flags=re.M)),
  'nonfault_open_margin': (mod.transient_observations, re.sub(r'final_target_margin_v=[+\-0-9.e]+', 'final_target_margin_v=+0.1', transient, count=1)),
  'nonfault_short_margin': (mod.short_observations, re.sub(r'final_low_margin_v=[+\-0-9.e]+', 'final_low_margin_v=+0.1', transient, count=1)),
  'missing_short_case': (mod.short_observations, re.sub(r'^SHORT_INIT=.*\n', '', transient, count=1, flags=re.M)),
}
rejected = {}
for name, (fn, text) in mutations.items():
    try:
        if fn is mod.transient_observations:
            fn(text, observed['timing']['analytic_max_rc_bound_ms'], observed['source_model_hashes']['rtdin_transient_model.py'])
        else:
            fn(text)
    except ValueError as error:
        rejected[name] = str(error)
    else:
        raise AssertionError(f'mutation accepted: {name}')
summary = {
 'scope': 'Independent exact-hash import check, producer replay and receipt mutation rejection; not a physical or whole-unit acceptance result',
 'import_files_verified': len(receipt['files']),
 'observations_byte_identical': True,
 'observation_count': len(observed['observed_faults']),
 'observations_sha256': hashlib.sha256(result.stdout).hexdigest(),
 'mutation_rejections': rejected,
 'physical_status': observed['physical_status'],
 'input_hashes': observed['source_model_hashes'],
}
(out / 'receipt.json').write_text(json.dumps(summary, indent=2)+'\n')
shutil.copy2(__file__, out / 'check.py')
shutil.copy2(receipt_path, out / 'import-receipt.json')
print(json.dumps(summary, indent=2))
