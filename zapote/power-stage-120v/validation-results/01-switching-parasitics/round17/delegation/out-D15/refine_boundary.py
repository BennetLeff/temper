#!/usr/bin/env python3
"""Extra timestep checks at the sampled 10 A / 443 ns ZVS boundary."""
import itertools
import json
from concurrent.futures import ThreadPoolExecutor

import run as campaign

if __name__ == '__main__':
    identity = campaign.identity()
    jobs = [(170, 10, direction, 443, esl, step)
            for direction, esl, step in itertools.product((0, 1), (1.06, 10), (.1, .05))]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda job: campaign.one(job, identity, True), jobs))
    (campaign.HERE / 'refine-boundary.json').write_text(json.dumps(rows, indent=2) + '\n')
