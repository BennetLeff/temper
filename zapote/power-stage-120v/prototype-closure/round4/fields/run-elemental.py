#!/usr/bin/env python3
"""Delegate the pinned runner with only the elemental B output we consume.

No physical solver, field integration, or mesh code is replaced. The default
runner also computes nodal B/H/A and elemental H/A, which the matrix never uses.
This profile requires fixture and native-reference qualification before use.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--oracle', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    here = Path(__file__).resolve().parent
    pins = json.loads((here / '../../round2/d17/upstream-inputs.json').read_text())
    relative = 'zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/run_elmer.py'
    upstream = args.oracle / relative
    if hashlib.sha256(upstream.read_bytes()).hexdigest() != pins[relative]:
        raise ValueError('unqualified upstream runner')
    spec = importlib.util.spec_from_file_location('pinned_elemental_runner', upstream)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = '  Calculate Magnetic Field Strength = Logical True\n'
    second = '{calc_extra}'
    if module.SIF.count(first) != 1 or module.SIF.count(second) != 1:
        raise ValueError('unexpected postprocessor template')
    module.SIF = module.SIF.replace(first, '  Calculate Magnetic Field Strength = Logical False\n')
    module.SIF = module.SIF.replace(second,
        '  Skip Nodal Fields = Logical True\n'
        '  Calculate Magnetic Vector Potential = Logical False\n'
        '  Calculate Magnetic Flux Density = Logical True\n')
    sys.argv = [str(upstream), *remaining]
    module.main()
    # The first two positional arguments remain the original mesh/work CLI.
    result_path = Path(remaining[1]) / 'result.json'
    result = json.loads(result_path.read_text())
    result['postprocessor_profile'] = 'elemental_B_only_no_nodal_projection'
    result['runner_adapter_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result_path.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
