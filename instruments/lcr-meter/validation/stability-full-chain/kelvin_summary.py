"""Worst downward-crossing phase margin and minimum |1+T| for the kelvincng{C} loop matrix.

Usage: python3 kelvin_summary.py matrix-final_kelvincng100.md
Also scans each case's <name>_return.csv (written by the run, gitignored) for crossings of the
negative real axis left of -1 (|T| > 1 at 180 deg): none means the multiple unity crossings of the
cable cases cannot encircle -1.
Groups by loop x relay set (nom / str) x fixture (nocable, coax1m = four 1 m Kelvin leads,
cur = lumped stray on HCUR/LCUR, k4closed = reference relay closed, leads unplugged), then by range.
"""
import re
import os
import sys
from collections import defaultdict


def left_of_minus_one(name):
    """Number of negative-real-axis crossings with Re(T) < -1; None if the CSV is missing."""
    path = f'{name}_return.csv'
    if not os.path.exists(path):
        return None
    pts = [tuple(map(float, l.split(',')[1:3])) for l in open(path).read().splitlines()[1:]]
    n = 0
    for (r0, i0), (r1, i1) in zip(pts, pts[1:]):
        if (i0 >= 0) != (i1 >= 0) and i1 != i0:
            r = r0 + (r1 - r0) * (-i0) / (i1 - i0)
            if r < -1:
                n += 1
    return n

ROW = re.compile(r'^\| (final_\S+) \| (.*) \| ([0-9.eE+-]+) at ([0-9.]+) MHz \|$')
CROSS = re.compile(r'([0-9.]+) MHz / (-?[0-9.]+)° \((down|up)\)')
NAME = re.compile(r'kelvinrelay_(r100k|r100|r5k)_(\w+?)_(nocable|coax1m|cur)_stray([0-9.]+)_risolo22_(bnom|bhigh)_(nom|str)_(k4open|k4closed)_')


def main():
    for path in sys.argv[1:]:
        worst = defaultdict(lambda: [999.0, '', 9e9])
        n = defaultdict(int)
        ups = 0
        left, missing = 0, 0
        for line in open(path):
            m = ROW.match(line.strip())
            if not m:
                continue
            name, cr, mind = m.group(1), m.group(2), float(m.group(3))
            g = NAME.search(name)
            rng, dut, fx, stray, _, rset, k4 = g.groups()
            loop = name.rsplit('_', 1)[1]
            fixture = 'k4closed' if k4 == 'k4closed' else fx
            downs = [float(a) for _, a, d in CROSS.findall(cr) if d == 'down']
            ups += sum(1 for *_, d in CROSS.findall(cr) if d == 'up')
            nl = left_of_minus_one(name)
            if nl is None:
                missing += 1
            else:
                left += nl
            for key in ((loop, rset, fixture, 'all'), (loop, rset, fixture, rng), (loop, 'all', 'all', 'all')):
                n[key] += 1
                w = worst[key]
                for a in downs:
                    if a < w[0]:
                        w[0], w[1] = a, name
                w[2] = min(w[2], mind)
        print(f'## {path}\n\nUpward unity crossings: {ups}. Negative-real-axis crossings left of -1: {left} '
              f'(return CSVs missing for {missing} rows).\n')
        print('| Loop | Set | Fixture | Range | Cases | Worst PM (down) | Min abs(1+T) | Worst-PM case |')
        print('|---|---|---|---|---:|---:|---:|---|')
        for key in sorted(worst):
            w = worst[key]
            flag = ' **< 45°**' if w[0] < 45 else ''
            print(f'| {" | ".join(key)} | {n[key]} | {w[0]:.2f}°{flag} | {w[2]:.3f} | {w[1]} |')
        print()


if __name__ == '__main__':
    main()
