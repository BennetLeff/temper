#!/usr/bin/env python3
"""One 10000-iteration probe for each exact case still failing at 1000."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import run as campaign

HERE = Path(__file__).resolve().parent


def main() -> None:
    previous = json.loads((HERE / 'recovery-itl4-1000/results.json').read_text())
    jobs = [tuple(r[k] for k in ('vbus', 'il', 'dir', 'dt_ns', 'esl_nH', 'step_ns'))
            for r in previous if r['aborted']]
    destination = HERE / 'recovery-itl4-10000'
    destination.mkdir(exist_ok=True)
    deck = destination / 'losses.cir'
    deck.write_text((HERE / 'losses.cir').read_text().replace('.end\n', '.options itl4=10000\n.end\n'))
    identity = campaign.identity()
    identity['solver_candidate'] = {'itl4': 10000, 'original_itl4': 200, 'single_probe_only': True}
    for path in (deck, Path(__file__)):
        identity['inputs'][str(path.relative_to(HERE.parents[6]))] = campaign.sha(path)
    campaign.HERE = destination
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda job: campaign.one(job, identity, False), jobs))
    (destination / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'cases': len(rows), 'aborted': sum(r['aborted'] for r in rows)}))


if __name__ == '__main__':
    main()
