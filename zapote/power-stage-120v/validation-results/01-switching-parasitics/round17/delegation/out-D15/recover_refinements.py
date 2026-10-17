#!/usr/bin/env python3
"""Bounded, separately identified iteration-budget qualification of failed refinements."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import run as campaign

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--itl4', type=int, choices=(1000, 10000), default=1000)
    args = parser.parse_args()
    source = json.loads((HERE / 'refine.json').read_text())
    source += json.loads((HERE / 'refine-boundary.json').read_text())
    points = sorted({tuple(r[k] for k in ('vbus', 'il', 'dir', 'dt_ns', 'esl_nH'))
                     for r in source if r['aborted']})
    if args.itl4 == 10000:
        previous = json.loads((HERE / 'recovery-itl4-1000/results.json').read_text())
        points = sorted({tuple(r[k] for k in ('vbus', 'il', 'dir', 'dt_ns', 'esl_nH'))
                         for r in previous if r['aborted']})
    destination = HERE / f'recovery-itl4-{args.itl4}'
    destination.mkdir(exist_ok=True)
    original = (HERE / 'losses.cir').read_text()
    candidate = original.replace('.end\n', f'* D15 separate solver qualification; original tolerances unchanged.\n.options itl4={args.itl4}\n.end\n')
    deck = destination / 'losses.cir'
    deck.write_text(candidate)
    identity = campaign.identity()
    identity['solver_candidate'] = {'itl4': args.itl4, 'original_itl4': 200}
    identity['inputs'][str(deck.relative_to(HERE.parents[6]))] = campaign.sha(deck)
    identity['inputs'][str(Path(__file__).relative_to(HERE.parents[6]))] = campaign.sha(Path(__file__))
    jobs = [(*point, step) for point in points for step in (.2, .1, .05)]
    # Reuse the exact scalar runner against an isolated output root and deck.
    campaign.HERE = destination
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda job: campaign.one(job, identity, False), jobs))
    (destination / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'cases': len(rows), 'aborted': sum(r['aborted'] for r in rows)}))


if __name__ == '__main__':
    main()
