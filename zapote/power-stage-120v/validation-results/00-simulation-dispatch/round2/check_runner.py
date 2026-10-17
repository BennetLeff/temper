"""Exercise runner failure propagation without invoking a circuit simulator.

These are transport checks, not evidence about circuit behavior.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

UNIT = Path(__file__).resolve().parents[3]
RUNNER = UNIT / 'validation-plan/sim-kit/common/run_ngspice.py'
spec = importlib.util.spec_from_file_location('kit_runner', RUNNER)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main() -> None:
    cases = (
        ('success', 0, 0, True, False),
        ('primary_nonzero', 1, 0, True, True),
        ('raw_nonzero', 0, 1, True, True),
        ('raw_missing', 0, 0, False, True),
    )
    results = []
    for name, primary_rc, raw_rc, make_raw, expect_abort in cases:
        with tempfile.TemporaryDirectory(prefix='ps-runner-audit-') as directory:
            root = Path(directory)
            deck = root / 'input.cir'
            deck.write_text('* runner transport fixture\n.end\n')

            def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raw = '-r' in args
                if raw and make_raw:
                    Path(kwargs['cwd'], 'waves.raw').write_text('fixture, not a waveform\n')
                return subprocess.CompletedProcess(args, raw_rc if raw else primary_rc,
                                                   'raw transcript\n' if raw else 'value = 1\n', '')

            with patch.object(runner.subprocess, 'run', side_effect=fake_run):
                result = runner.run(deck, {}, keep=root / 'run', raw=True)
            assert bool(result['aborted']) == expect_abort, (name, result)
            assert result['returncode'] == primary_rc
            assert result['raw_returncode'] == raw_rc
            assert (root / 'run/run.log').read_text() == 'value = 1\n'
            assert (root / 'run/raw_run.log').read_text() == 'raw transcript\n'
            results.append({'case': name, 'aborted': bool(result['aborted']),
                            'primary_returncode': primary_rc, 'raw_returncode': raw_rc,
                            'both_logs_retained': True, 'pass': True})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
