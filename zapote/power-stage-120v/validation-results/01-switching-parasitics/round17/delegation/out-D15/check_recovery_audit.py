#!/usr/bin/env python3
"""Exercise recovery-audit failure handling with the actual D15 evidence cohort."""
from __future__ import annotations

import copy
import json

import audit_recovery as audit


def main() -> None:
    original = [row for name in ('refine.json', 'refine-boundary.json')
                for row in json.loads((audit.HERE / name).read_text())]
    recovered = json.loads((audit.HERE / 'recovery-itl4-1000/results.json').read_text())
    probes = json.loads((audit.HERE / 'recovery-itl4-10000/results.json').read_text())
    assert audit.unresolved_recovery(original, recovered, probes) == []
    missing = next(row for row in probes if row['il'] == 2)
    partial = [row for row in probes if row is not missing]
    assert audit.unresolved_recovery(original, recovered, partial) == [missing['tag']]
    assert len(audit.unresolved_recovery(original, recovered, [])) == 6
    failed_probe = copy.deepcopy(probes)
    failed_probe[0]['aborted'] = True
    assert audit.unresolved_recovery(original, recovered, failed_probe) == [probes[0]['tag']]
    unexpected = copy.deepcopy(probes)
    unexpected[0]['il'] = 999
    for label, cohort, replacements in (
        ('missing recovery row', recovered[1:], probes),
        ('duplicate recovery row', recovered + [recovered[0]], probes),
        ('duplicate probe', recovered, probes + [probes[0]]),
        ('unexpected probe', recovered, unexpected),
    ):
        try:
            audit.unresolved_recovery(original, cohort, replacements)
        except ValueError:
            continue
        raise AssertionError(f'Audit accepted {label}')
    print('PASS: complete cohort; missing/failed probes stay indeterminate; malformed cohorts rejected')


if __name__ == '__main__':
    main()
