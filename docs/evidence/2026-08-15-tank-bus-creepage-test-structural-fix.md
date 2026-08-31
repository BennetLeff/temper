<!-- provenance: commit=d9ab1e723e4973818bb9f786f156071b33f1b33e dirty=UNKNOWN -->

# test_tank_creepage.py structural mask: the tank↔bus shortfall is now caught

**Finding under fix:** `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`
Sec 4.3 — `tank.c_tank1-p2` ↔ DC-bus rails: **2.0 mm provided vs 6.3 mm (PD2) /
10.0 mm (PD3) required**, a 3.2×–5.0× shortfall, PD3 governing as built.
The 2026-08-15 safety-assertion audit (`docs/evidence/2026-08-15-safety-assertion-audit-resumed.md`
Part 0) showed `test_tank_creepage.py` was **structurally incapable** of
catching it. This change fixes the test and the module it tests.

## 1. What was structurally wrong (the audit's four layers)

1. **The pair was not enumerable.** `tank_creepage_pairs()` enumerated only
   (tank-ref × other-HV-*component*-ref) pairs. The bus rails (`+170V_BUS`,
   `DC_BUS_RTN`) are *nets* — a net has no refdes, so it can never appear in
   the pair list, and the test's count pin `len(pairs) == 4 * 42` would pass
   unchanged with the tank↔bus gap at 2.0 mm.
2. **The metric was box-to-box, not copper-to-copper.** The checker computed
   Chebyshev component-bounding-box gaps. The finding is a copper-to-copper
   (pad/pour) distance; the module's own docstring said it was "silent —
   correctly, not by omission" on pad-to-routed-copper creepage.
3. **The pass signal fired on a different shortfall.** The one real assertion
   (`test_rejects_the_committed_placement_at_pd3`) fires on component-body
   pairs (C25↔RV1, C27↔U5 at 0.4 mm box gap) — the tank↔bus 2.0 mm gap was
   invisible. The test was green on a board whose only defect was the
   tank↔bus shortfall.
4. **Liveness was weak.** The suite ran nightly-only (`schedule` /
   `workflow_dispatch`), inside a `continue-on-error: true` step, in a job
   absent from `.github/required-checks.json`'s `required_contexts`.

## 2. What was fixed

### 2.1 Pair enumeration — nets, not just components (`tank_creepage.py`)

- `TANK_BUS_RAIL_NETS`: the DC-bus family from `TEMPER_NET_ASSIGNMENTS`
  (`+170V_BUS`, `DC_BUS_RTN`, `DC_BUS+`, `DC_BUS-`); the evidence doc names
  the first two, the SSOT adds the aliases.
- `TankBusNetPair` + `tank_bus_net_pairs()`: every (tank ref × present,
  HV-classified bus rail) pair. Measured on the committed board: **8 pairs**
  (C25/C26/C27/R30 × `+170V_BUS`/`DC_BUS_RTN`; `DC_BUS+`/`DC_BUS-` are
  declared but not present in the netlist).

### 2.2 Copper-level metric (`tank_creepage.py`)

- `tank_bus_pad_gap_mm()`: **exact** pad-to-pad copper distance via
  `pad_geometry.pad_pair_distance` — the same shape-correct edge-to-edge
  kernel the REQ-SAFE-01 validator uses (no box proxy, no center-to-center
  optimism). Pad world positions use the same rotation kernel as production
  (`temper_geometry.rotate_local_to_world_py`), verified bit-identical
  against `temper_drc_rs.req_safe_01_component_pads` on the real board.
- `tank_bus_pour_contained_pads()`: detects a tank pad **inside** a bus-rail
  zone outline on a layer the pad occupies. **Measured on the committed
  board: C26 pad 2 and R30 pad 1 lie inside the `DC_BUS_RTN` pours on both
  F.Cu and B.Cu** (both THT, layer=all). The zone fill approaches a foreign
  pad to exactly the design's enforced netclass clearance, so for these pads
  the pad-pad distance (27.9 / 30.5 mm) is NOT the copper gap — the pour
  bounds it to the design's own 2.0 mm rule. The evidence doc's "2.0 mm
  provided" is physical copper geometry on the committed board, not a
  routing hypothetical.
- `check_tank_bus_creepage()`: reports violations with kind
  `"pad-pad"` (exact copper) or `"pour-bounded"` (gap = enforced clearance).

### 2.3 The shortfall catch — new assertions in `test_tank_creepage.py`

`TestTankBusEnforcement` asserts the figures the design is **built to**
against the governing requirement (Table 18 functional creepage, >500–800 V:
6.3 mm PD2 / 10.0 mm PD3). **These are RED on the committed design, by
design** — a labelled red beats a green that means nothing:

| Assertion | Enforced today | Required | Verdict |
|---|---|---|---|
| netclass clearance (max of HighVoltageTank/HighVoltage) | **2.0 mm** | 10.0 mm PD3 | **FAIL** |
| netclass clearance | **2.0 mm** | 6.3 mm PD2 | **FAIL** |
| DRU "HighVoltageTank functional creepage" rule figure | **6.3 mm** (`_TANK_POLLUTION_DEGREE = "PD2"`) | 10.0 mm PD3 | **FAIL** |
| SSOT declared creepage (HighVoltageTank / HighVoltage) | **6.3 / 6.0 mm** | 10.0 mm PD3 | **FAIL** |

Plus green falsifier/liveness tests: the bus-net pairs are enumerated and
never collide with component refdeses; the copper metric returns finite
gaps for every pair; the pour containment is pinned (C26.2, R30.1 inside
`DC_BUS_RTN`, C25/C27 not); and `check_tank_bus_creepage` at the PD3 margin
reports exactly the two pour-bounded pairs at gap 2.0 mm.

Also re-derived: the stale `len(pairs) == 4 * 42` pin → `4 * 45` (180). The
pin moved on 2026-08-13 when the HighVoltageSignal carve-out added
K2/R7/R12/R19/R23/U8 to Group B (module docstring's own
`_HV_EQUIVALENT_CLASSES` note); the test's count failure on main predates
this change (verified on a pristine tree).

### 2.4 Liveness (`.github/workflows/python-tests.yml`)

New PR-time hard step **"Run tank↔bus creepage gate (safety shortfall)"** in
the `test` job (which is in `required_contexts` as "Core Tests"): runs
`test_tank_creepage.py` on every PR and every push to main, no
`continue-on-error`, with a pytest_guard floor of 27. The step is expected
**red** until the enforced figures are raised — that is the point. The
nightly `extended-cpsat` job's masked directory step is deliberately left
alone: un-masking the whole `tests/placer/cp_sat/` directory in bulk is the
"un-silence in bulk" the 2026-08-15 handoff warns against; the targeted
PR-time gate achieves liveness without it.

## 3. Bonus find (N1, carried from the audit — NOT fixed here)

The "2.0 mm provided" originates at `scripts/generate_kicad_dru.py:63-67`
(`HV_INTERNAL_CLEARANCE_MM = 2.0`), mirrored by
`design_rules.py`'s `HighVoltage.clearance = 2.0` and
`pcb/temper.kicad_pro`'s HighVoltage/HighVoltageTank netclass clearance.
The arithmetic chain is DERIVED from recovered primary text (Table 15 at
120 V nominal, OVC II → 1 500 V impulse; Table 16 → 0.5 mm basic; cl. 29.1.3
→ 1.5 mm reinforced; cl. 29.1 → +0.5 mm soldering adder) — but the
**application** is unsupported: a reinforced **mains↔PELV barrier** figure
reused as same-domain HV↔HV internal clearance, on a **120 V-only** basis.
At 240 V nominal (OVC II) the same chain gives 3.5 mm. The 2.0 mm figure is
valid only for a ≤150 V-rated appliance. **Fix is out of scope for this
change** (the SafetyValue migration owns it); the test now fails loudly on
the shortfall instead of documenting it in prose.

## 4. Test result on the committed design

```
4 failed, 23 passed   # 4 failures are exactly TestTankBusEnforcement
```

The test now correctly FAILS on the known shortfall: the enforced figures
(2.0 mm clearance / 6.3 mm DRU creepage / 6.0-6.3 mm SSOT creepage) are all
below the governing 10.0 mm PD3 requirement. It flips green only when the
enforced values are raised — never by weakening the assertions.
