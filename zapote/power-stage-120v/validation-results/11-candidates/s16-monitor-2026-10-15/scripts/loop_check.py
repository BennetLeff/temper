#!/usr/bin/env python3
"""Negative-rail shunt loop phase margin with the monitor's src-to-n divider loads changed.

The loop model is a verbatim transcription of out-D33 rail_qualification.py loop() (lines 52-66) and corners()
(lines 69-76) from the cb48 snapshot, with the two monitor divider loads (1/14420 + 1/17620 in the original) made
parameters.  It needs only numpy (the snapshot module imports the licensed-macro runner, so it is not imported).

    python3 -I scripts/loop_check.py   -> results/loop_check.json

Control: monitor loads (14.42 k, 17.62 k) reproduce the committed minimum phase margins of rail-qualified/loop.json
(RTOP 6120: 51.61766 deg) and rail-qualified-6k2/loop.json (RTOP 6200: 51.62001 deg) to 1e-6 deg.
"""
import sys as _s; _s.dont_write_bytecode = True
import itertools, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
D33 = Path("/Users/bennet/.claude/jobs/fbfc46b4/tmp/snap-cb48/zapote/power-stage-120v/validation-results/"
           "01-switching-parasitics/round17/delegation/out-D33")


def corners():
    keys = ("bulk_u", "local_u", "bulk_r", "gm", "pole1", "pole2", "banks")
    out = []
    for bulk, local, r, gm, p1, p2, banks in itertools.product((140.8, 316.8), (10, 24), (.67, 1.1), (2, 8), (.5, 2),
                                                                 (.5, 2), (1, 2)):
        out.append(dict(bulk_u=bulk, local_u=local, bulk_r=r, local_r=.04, local_l_n=.5, mid_u=local / 10, mid_r=.1,
                        mid_l_n=.5, hf_u=.32, hf_r=.05, hf_l_n=.1, gm=gm, pole1=p1, pole2=p2, banks=banks))
    return out


def loop(c, rtop, mon):
    f = np.geomspace(1, 1e8, 60000)
    s = 2j * np.pi * f
    y = c["banks"] / 4990 + 1 / (rtop + 10000) + sum(1 / r for r in mon) + c["banks"] / 10000 + c["banks"] * (
        1 / (c["bulk_r"] + s * 10e-9 + 1 / (s * c["bulk_u"] * 1e-6)) +
        1 / (c["local_r"] + s * c["local_l_n"] * 1e-9 + 1 / (s * c["local_u"] * 1e-6)) +
        1 / (c["mid_r"] + s * c["mid_l_n"] * 1e-9 + 1 / (s * c["mid_u"] * 1e-6)) +
        1 / (c["hf_r"] + s * c["hf_l_n"] * 1e-9 + 1 / (s * c["hf_u"] * 1e-6)))
    gain = (c["gm"] * 10000 / (rtop + 10000)) / ((1 + s * 159e-6 * c["pole1"]) * (1 + s * 80e-9 * c["pole2"]) * y)
    cr = np.flatnonzero(np.diff((abs(gain) > 1).astype(int)))
    phase = np.unwrap(np.angle(gain)) * 180 / np.pi
    return (180 + phase[cr]).tolist()


def min_pm(rtop, mon):
    return min(min(loop(c, rtop, mon)) for c in corners())


def main():
    res = {}
    for name, rtop, mon, ref in (("control RTOP 6120 (qualified)", 6120.0, (14420, 17620), "rail-qualified/loop.json"),
                                 ("control RTOP 6200 (BOM)", 6200.0, (14420, 17620), "rail-qualified-6k2/loop.json")):
        got = min_pm(rtop, mon)
        want = json.load(open(D33 / ref))["minimum_margin_deg"]
        assert abs(got - want) < 1e-6, (name, got, want)
        res[name] = {"min_phase_margin_deg": round(got, 4), "committed_deg": round(want, 4)}
    for name, mon in (("s43 as built (14.42 k, 17.68 k)", (14420, 17680)),
                      ("option 2 (15.8k+4.42k, 28.4k+6.2k)", (20220, 34600)),
                      ("option 1c-4420 (0.75k+10k, 2.94k+10k)", (10750, 12940))):
        res[name] = {"min_phase_margin_deg": round(min_pm(6200.0, mon), 4)}
    Path(HERE.parent / "results").mkdir(exist_ok=True)
    json.dump(res, open(HERE.parent / "results/loop_check.json", "w"), indent=1)
    for k, v in res.items():
        print(f"{k:42s} {v}")


if __name__ == "__main__":
    main()
