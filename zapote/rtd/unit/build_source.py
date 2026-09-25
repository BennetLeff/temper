"""Retain a fresh Atopile RTDUnit compilation and strict source export."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'harness-lab'))
import block_source


def run(output: Path) -> None:
    if output.exists():
        raise ValueError('refusing to overwrite a retained source build: ' + str(output))
    (output / 'elec').mkdir(parents=True)
    shutil.copytree(REPO / 'elec/src', output / 'elec/src')
    (output / 'ato.yaml').write_text('ato-version: 0.2.69\nbuilds:\n  default:\n    entry: elec/src/rtd_unit.ato:RTDUnit\n')
    proc = block_source.run_atopile_build(output, 'elec/src/rtd_unit.ato', 'RTDUnit')
    (output / 'stdout.txt').write_text(proc.stdout)
    (output / 'stderr.txt').write_text(proc.stderr)
    receipt = {'command': 'uv tool run --offline --from atopile==0.2.69 ato --non-interactive build elec/src/rtd_unit.ato:RTDUnit',
        'returncode': proc.returncode, 'build_report_failed': 'FAILED' in proc.stdout,
        'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'block_source_sha256': hashlib.sha256((REPO / 'harness-lab/block_source.py').read_bytes()).hexdigest(),
        'source_hashes': block_source.workspace_hashes(output)}
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    block_source.gate_build(proc)
    block_source.run_resolved_export(output, 'elec/src/rtd_unit.ato', 'RTDUnit', output / 'resolved-components.json')
    print(json.dumps({'status': 'compiled-and-exported', 'output': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.output.resolve())
