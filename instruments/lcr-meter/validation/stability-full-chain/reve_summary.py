"""Worst downward-crossing phase margin and minimum |1+T| per group of a loop-matrix report.

Usage: python3 reve_summary.py matrix-final_reverelaycng100.md [matrix-final_fixedrelaycng100.md ...]
Groups: grid by relay set (nom/str), attribution by parameter and range, source-driver / follower
loops (drive/high/low, plus the TIA rows of the same cases), weld.
"""
import re
import sys
from collections import defaultdict

ROW = re.compile(r'^\| (final_\S+) \| (.*) \| ([0-9.eE+-]+) at ([0-9.]+) MHz \|$')
CROSS = re.compile(r'([0-9.]+) MHz / (-?[0-9.]+)° \((down|up)\)')


def group(name):
    loop = name.rsplit('_', 1)[1]
    if '_attr' in name:
        m = re.search(r'_attr(\w+?)_(r100k|r100|r5k)_', name)
        return f'attr {m.group(1)} {m.group(2)}', loop
    if '_loops_drv' in name:
        m = re.search(r'_loops_(drv\w+?)_(r100k|r100|r5k)_', name)
        return f'drive-attr {m.group(1)} {m.group(2)}', loop
    if '_loops_' in name:
        return 'loops', loop
    if '_weld_' in name:
        return 'weld', loop
    s = 'str' if '_str_' in name else 'nom'
    rng = re.search(r'_(r100k|r100|r5k)_', name).group(1)
    return f'grid {s}', loop, rng


def main():
    for path in sys.argv[1:]:
        worst = defaultdict(lambda: [999.0, '', 9e9, ''])
        n = defaultdict(int)
        for line in open(path):
            m = ROW.match(line.strip())
            if not m:
                continue
            name, cr, mind = m.group(1), m.group(2), float(m.group(3))
            g = group(name)
            keys = [(g[0], g[1])] + ([(g[0] + ' ' + g[2], g[1])] if len(g) > 2 else [])
            downs = [float(a) for _, a, d in CROSS.findall(cr) if d == 'down']
            for key in keys:
                n[key] += 1
                w = worst[key]
                for a in downs:
                    if a < w[0]:
                        w[0], w[1] = a, name
                if mind < w[2]:
                    w[2], w[3] = mind, name
        print(f'## {path}\n\n| Group | Loop | Cases | Worst PM (down) | Min abs(1+T) | Worst-PM case |\n|---|---|---:|---:|---:|---|')
        for key in sorted(worst):
            w = worst[key]
            print(f'| {key[0]} | {key[1]} | {n[key]} | {w[0]:.2f}° | {w[2]:.3f} | {w[1]} |')
        print()


if __name__ == '__main__':
    main()
