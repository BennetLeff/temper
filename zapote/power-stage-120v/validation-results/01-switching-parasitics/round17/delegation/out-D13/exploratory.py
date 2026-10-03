#!/usr/bin/env python3
"""Four separately identified hot-remedy iteration-cap probes, not qualification."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent


def main() -> None:
    jobs = []
    for cap in (1000, 10000):
        variant = f'F6-itl4-{cap}'
        source = (HERE / 'decks/F6.cir').read_text()
        source = source.replace('.temp {TJ}', f'.temp {{TJ}}\n.options itl4={cap}')
        (HERE / 'decks' / f'{variant}.cir').write_text(source)
        for scenario, current in [('S1', 37), ('S4', -20)]:
            jobs.append((variant, 150, scenario, 198, current, 0, 348, 10, .2))
    provenance = {'purpose': 'Exploratory transfer only; no solver qualification; original campaign retained.',
                  'shared_physics_and_runner': 'provenance-refine.json',
                  'changed_option': 'itl4 200 -> 1000 or 10000; all tolerances and circuit unchanged',
                  'input_hashes': {str(p.relative_to(HERE)): run.sha(p) for p in [Path(__file__), HERE / 'run.py', HERE / 'decks/F6.cir', HERE / 'decks/F6-itl4-1000.cir', HERE / 'decks/F6-itl4-10000.cir']}}
    (HERE / 'provenance-exploratory.json').write_text(json.dumps(provenance, indent=2) + '\n')
    with ThreadPoolExecutor(2) as pool:
        rows = list(pool.map(run.one, jobs))
    (HERE / 'results-exploratory.json').write_text(json.dumps(rows, indent=2) + '\n')


if __name__ == '__main__':
    main()
