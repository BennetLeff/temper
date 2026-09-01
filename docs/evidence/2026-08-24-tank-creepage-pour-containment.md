<!-- provenance: commit=03d0f3697e4021f8e803c965c5424c794e767e48 dirty=true (this document only; no source, board or test file is modified. Every measurement was taken by running the shipped detector against two committed board revisions -- 03d0f3697 and d9ab1e723 -- with the current parser.) -->

# Tank↔bus pour containment — not a vacuity regression, and the old number was weaker than it read

**Date:** 2026-08-24
**Base:** `origin/main` @ `03d0f3697`
**Closes out:** [`2026-08-24-trunk-red-triage.md`](./2026-08-24-trunk-red-triage.md) §1.2

## Bottom line

I flagged this in the triage as a *suspected vacuity regression* — a detector
that used to find things and now finds nothing — and said it worried me more
than the shortfall it sits next to. **That was wrong, and this document is the
correction.**

The detector is fine and fully exercised. It returns empty because the
`DC_BUS_RTN` zone outlines were carved back from the tank pads, which is a real
and intended board change. Three separate things fell out of establishing that,
and the third is the one worth keeping:

1. **Not vacuity.** Every step of the containment chain runs and produces the
   right intermediate values.
2. **The pads did not move.** `C26.2` and `R30.1` are at byte-identical
   coordinates in both revisions. The *pours* moved.
3. **The original expectation was weaker than its own docstring claims.**
   Neither board revision carries a computed zone fill. The test reasons about
   fill geometry from *outline* containment, so "2.0 mm pour-bounded" was
   inferred in the old board too, not measured.

The four **enforcement/SSOT** failures in the same file are untouched by any of
this and remain real. See §4.

## 1. The detector is not vacuous

`tank_bus_pour_contained_pads()` requires four things to line up. Instrumented
at `03d0f3697`, all four resolve; only the last is false:

```
TANK_NODE_NET = tank.c_tank1-p2
DC_BUS_RTN pairs: [('C25',…), ('C26',…), ('C27',…), ('R30',…)]

=== C26 ===
  TANK pin 2: net='tank.c_tank1-p2' layers=['B.Cu', 'F.Cu']   <- net matched, layers resolved
        pad xy=65.920,112.320
        zone Zone_34  ['F.Cu'] covers=False dist=86.408        <- zone net-filtered, layers intersect
        zone Zone_43  ['B.Cu'] covers=False dist=86.408
        …
        -> covered by 0 zone(s)
```

The pads are **86–140 mm** from the nearest `DC_BUS_RTN` pour, on a board whose
copper bbox is roughly 155 × 240 mm. That is not a marginal miss.

Supporting counts at `03d0f3697`: 151 zones parse; 12 carry `DC_BUS_RTN`; they
span all four expected layers (`F.Cu`, `In3.Cu`, `In4.Cu`, `B.Cu`, 3 each). The
inputs the detector needs all exist.

## 2. The pads did not move — the pours did

Same detector, same parser, two committed board revisions. `d9ab1e723` is #1225,
the commit that wrote the expectation:

| | `C26.2` | `R30.1` |
|---|---|---|
| **OLD** (`d9ab1e723`) | xy=(65.92, 112.32) · dist **0.000 mm** · `contained=[('C26.2', ('B.Cu','F.Cu'))]` | xy=(49.10, 124.48) · dist **0.000 mm** · `contained=[('R30.1', ('B.Cu','F.Cu'))]` |
| **NOW** (`03d0f3697`) | xy=**(65.92, 112.32)** · dist **86.408 mm** · `contained=[]` | xy=**(49.10, 124.48)** · dist **79.541 mm** · `contained=[]` |

**Identical coordinates.** The test's docstring anticipated the right outcome by
the wrong mechanism — it says *"re-derive if the board moves the pads out of the
pour (that is the fix)"*. The pads never moved; the pour left.

What changed, measured the same way:

| | zones | `DC_BUS_RTN` zones | `DC_BUS_RTN` outline area |
|---|---:|---:|---:|
| OLD | 96 | 2 | **74,168 mm²** |
| NOW | 151 | 12 | **3,103 mm²** |

Two board-wide outlines became twelve small carved ones — a 96 % reduction in
enclosed area. That is the signature of the creepage-aware zone generator wired
in #1257 (*"creepage-aware carve, holes preserved, islands honest"*) and the
copper regeneration in `23b5daf8d` (*"0 to 36 genuine multi-pad connections,
isolated_copper 109 to 0"*). The carve pulling `DC_BUS_RTN` off an HV tank pad
is the feature working, not a defect.

## 3. The part worth keeping: the old measurement was an outline proxy

The test's docstring explains why containment is a copper-level quantity:

> the zone *fill* approaches a foreign pad to exactly the design's enforced
> netclass clearance, so for a contained pad the pad-pad distance is NOT the
> copper gap — the pour is between them

That reasoning is about the **fill**. But neither revision stores one:

```
                    zone blocks   filled_polygon
OLD (d9ab1e723)          96             0
NOW (03d0f3697)         151             0
```

A zone block declares `(fill yes (thermal_gap 0.5) …)` and then carries only
`(polygon (pts …))` — the **outline**. KiCad writes the computed fill as
`filled_polygon`, and there is none in either file.

So `Polygon(z.polygon).covers(pt)` asks *"is this pad inside the zone
outline?"*, which is not the same question as *"is there pour copper beside this
pad, at the enforced clearance?"* — a fill carves a clearance void around a
foreign-net pad and may place no copper near it at all. **The old
`2.0 mm pour-bounded` figure was therefore inferred from an outline, not
measured from copper.** It read as a geometric measurement and was a proxy.

This is adjacent to open PR #1388 (*"zone fill is nondeterministic on the HV bus
and breaches the mains barrier"*), which is the same subsystem and should be read
alongside.

## 4. What is still genuinely red in this file

Four assertions in `test_tank_creepage.py` are about **declared figures**, not
pour geometry, and nothing above touches them:

```
E  tank<->bus enforced clearance (2.0mm) is short of the governing PD3
   functional creepage (10.0mm)
E  assert 2.0 >= 6.3
E  HighVoltageTank.creepage_mm (6.3) is short of PD3 (10.0mm)
E  assert 'PD3' == 'PD2'
```

Enforced netclass clearance, the `HighVoltageTank` SSOT creepage value, and
which pollution-degree tier the DRU generator selects. These remain owner
questions and this document makes no claim about them.

A fifth, `got 184 pairs … assert 184 == (4 * 45)`, is a hardcoded
`4 tanks × 45 others` count against a board that now yields 46 others.

## 5. Recommendation

- **Re-derive `test_pour_contained_tank_pads_are_detected` and
  `test_pour_bounded_pairs_violate_pd3`** to the empty results. They are stale
  against a real improvement.
- **Do not carry the "2.0 mm pour-bounded" reasoning into the new expectation.**
  §3 shows it was never measured from copper. Either assert against a filled
  board, or say plainly in the docstring that outline containment is a proxy and
  what it does and does not establish.
- **Re-derive the `4 * 45` count** at the same time; it is independent and
  mechanical.
- **Leave §4's four alone** pending an owner decision.

Sequencing note for the triage: §1.3's `K1`↔`R56` creepage violation is on a
different pair and a different boundary (`DC_BUS<->LV_CONTROL`), and nothing
here bears on it.

## 6. Reproducing

```bash
git show d9ab1e723:pcb/temper.kicad_pcb > /tmp/old_board.kicad_pcb
cd packages/temper-placer
uv run python - /tmp/old_board.kicad_pcb <<'PY'
import sys
from pathlib import Path
from shapely.geometry import Point, Polygon
from temper_placer.io.kicad_parser import parse_kicad_pcb, parse_kicad_pcb_v6
from temper_placer.placer.cp_sat import tank_creepage as t
for label, b in (('OLD', Path(sys.argv[1])), ('NOW', Path('../../pcb/temper.kicad_pcb'))):
    nl = parse_kicad_pcb(b, normalize=False).netlist
    zs = parse_kicad_pcb_v6(b).zones
    print(f'=== {label} ===')
    for pair in t.tank_bus_net_pairs(nl):
        if pair.bus_net != 'DC_BUS_RTN' or pair.tank_ref not in ('C26', 'R30'):
            continue
        comp = next(c for c in nl.components if c.ref == pair.tank_ref)
        for p in comp.pins:
            if p.net != t.TANK_NODE_NET:
                continue
            pt = Point(t._pad_world_spec(comp, p)[3:5])
            d = min((Polygon(z.polygon).distance(pt) for z in zs
                     if 'DC_BUS_RTN' in (z.net_classes or [])
                     and set(z.layers) & t._pin_layers(p)), default=float('inf'))
            print(f'  {pair.tank_ref}.{p.number} xy=({pt.x:.2f},{pt.y:.2f}) '
                  f'dist={d:.3f} contained={t.tank_bus_pour_contained_pads(nl, pair, zs)}')
PY

# §3 — neither revision carries a computed fill
grep -c 'filled_polygon' /tmp/old_board.kicad_pcb pcb/temper.kicad_pcb   # -> 0, 0
```

## 7. Sources

- `packages/temper-placer/tests/placer/cp_sat/test_tank_creepage.py:307-343` — the two expectations.
- `packages/temper-placer/src/.../placer/cp_sat/tank_creepage.py` — `tank_bus_pour_contained_pads()`.
- #1225 (`d9ab1e723`) — wrote the expectation; #1257 — the creepage-aware zone generator; `23b5daf8d` — the copper regeneration.
- PR #1388 — zone-fill nondeterminism on the HV bus, same subsystem.
