"""Recompute the reported coax normalization interval under the amended criterion.

Sampled current cuts are not a proof of a spatial bound; this records the
interval obtained from the cuts already reported in round 6.
"""

import hashlib
import json
from pathlib import Path


def audit() -> dict:
    source = Path(__file__).resolve().parent.parent / (
        '01-switching-parasitics/round6/d1-fem/fixtures/results.json'
    )
    content = source.read_bytes()
    result = json.loads(content)
    row = result['coax']['direct_tree_gauge'][-1]
    currents = row['port_cut_currents_A']
    analytic = result['analytic_coax_nH']
    interval = [2 * row['energy_J'] * 1e9 / current**2
                for current in (max(currents), min(currents))]
    errors = [100 * (value / analytic - 1) for value in interval]
    return {
        'source': str(source.relative_to(source.parents[4])),
        'source_sha256': hashlib.sha256(content).hexdigest(),
        'interpretation': 'sampled normalization interval, not a spatial bound',
        'nominal_inductance_nH': row['nominal_L_nH'],
        'analytic_inductance_nH': analytic,
        'sampled_current_range_A': [min(currents), max(currents)],
        'inductance_interval_nH': interval,
        'error_interval_percent': errors,
        'entire_reported_interval_within_two_percent': all(abs(e) <= 2 for e in errors),
    }


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2, allow_nan=False))
