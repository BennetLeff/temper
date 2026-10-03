#!/usr/bin/env python3
"""Reject incomplete or mixed-identity D15 refinements before publishing tables."""
from __future__ import annotations

import copy
import json

import analyze


def main() -> None:
    focused = json.loads((analyze.HERE / 'refine.json').read_text())
    boundary = json.loads((analyze.HERE / 'refine-boundary.json').read_text())
    identity = analyze.campaign.cache_key(analyze.campaign.identity())
    assert len(analyze.validate_refinements(focused, boundary, identity)) == 40
    aborted = next(row for row in focused if row['aborted'])
    mixed_identity = copy.deepcopy(boundary)
    mixed_identity[0]['identity']['inputs']['wrong-model-sentinel'] = 'changed'
    aborted_identity = copy.deepcopy(focused)
    next(row for row in aborted_identity if row['aborted'])['identity']['inputs']['wrong-options-sentinel'] = 'changed'
    for label, main_rows, boundary_rows in (
        ('missing aborted row', [row for row in focused if row is not aborted], boundary),
        ('missing boundary cohort', focused, []),
        ('duplicate focused row', focused[:-1] + [focused[0]], boundary),
        ('mixed boundary identity', focused, mixed_identity),
        ('mixed aborted identity', aborted_identity, boundary),
    ):
        try:
            analyze.validate_refinements(main_rows, boundary_rows, identity)
        except ValueError:
            continue
        raise AssertionError(f'Analyzer accepted {label}')
    print('PASS: exact 32+8 cohorts; omitted/duplicate cases and mixed identities rejected, including aborts')


if __name__ == '__main__':
    main()
