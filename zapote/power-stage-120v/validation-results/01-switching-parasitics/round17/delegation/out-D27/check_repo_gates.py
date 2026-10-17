"""Read-only invocation of existing repo gates; keep caches/logs inside out-D27."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'zapote').is_dir())
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('import_gate', ROOT/'scripts/import_linter_gate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def lint(config_path: str) -> tuple[int, str]:
    # The gate's normal uv invocation would create a root cache; add only --no-cache.
    command = [str(HERE/'.venv/bin/lint-imports'), '--config', config_path, '--no-cache']
    env = dict(os.environ, PYTHONPATH=str(ROOT/'packages/temper-placer/src'))
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    return result.returncode, result.stdout+'\n'+result.stderr


module.run_lint_imports = lint
with (HERE/'import-gate.log').open('w') as log:
    oldout, olderr = sys.stdout, sys.stderr
    try:
        sys.stdout = sys.stderr = log
        try:
            import_exit = module.main()
        except SystemExit as exc:
            import_exit = exc.code
    finally:
        sys.stdout, sys.stderr = oldout, olderr
with (HERE/'regen-check.log').open('w') as log:
    regen = subprocess.run([sys.executable, str(ROOT/'scripts/regen_derived.py'), '--check'],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
report = {'import_gate_exit': import_exit, 'regen_check_exit': regen.returncode,
          'import_invocation': 'existing gate, same config/parser/allowlist; CLI --no-cache; source on PYTHONPATH',
          'regen_invocation': 'scripts/regen_derived.py --check (report-only make regen-check entry point)',
          'write_regeneration': 'not run: user allows writes only to out-D27'}
(HERE/'repo-gates.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
