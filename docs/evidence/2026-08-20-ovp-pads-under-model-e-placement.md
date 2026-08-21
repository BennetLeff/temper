<!-- provenance: branch analysis/ovp-pads-under-model-e, base
     origin/analysis/per-pairing-placer-solve (30edd0a93). Branched from that tip
     rather than origin/main because reproducing the model-E placement needs the
     per-pairing barrier model, which has not landed on main. Nothing was merged.
     Board measured: pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b -- verified
     identical before and after every measurement; never opened for writing. Every
     solve and census below is an in-memory measurement; the row-E placement went
     to a scratch path outside the repo.
     Environment: this worktree's OWN .venv (`make venv-isolate` under
     `env -u CONDA_PREFIX`). `scripts/check_stale_extensions.py` PASSED 10/10 fresh
     before the first measurement, and `resolve_insulation_declaration` was verified
     present on the temper_design_bundle_python surface before any per-pairing run. -->
---
module: placer
tags: [creepage, clearance, iec60335, ovp, isolation-barrier, per-pairing, instrument-defect]
problem_type: diagnosis
---

# 2026-08-20: the OVP pads under the compliant placement — 6 of 8 resolved, 2 intra-package, and 3 newly below the functional bar

**Authority: analysis and measurement only.** `pcb/temper.kicad_pcb` was not
modified.

## 0. Headline

The question was whether the compliant model-E placement of
`docs/evidence/2026-08-19-per-pairing-placer-solve.md` resolves the OVP
pad-clearance violations on the four mid-chain protection nets
`safety.ovp.r_{div,adc}_top{1,2}-p2` (8 pads, 2 per net, zero routed copper).

**Partially — and the answer differs by which figure you ask about.** Nobody had
checked, and the reason nobody had is structural: **the eight pads are in neither
the HV set nor the SELV set of the 36 → 8 census**, because all four nets are
undeclared in `elec/insulation_manifest.yaml`. That census never graded them.
They are neither among the 36 nor among the 8.

| bucket | bar | committed | model-E | verdict |
|---|---|---:|---:|---|
| vs **LV** classes (`Power`/`Default`/`FinePitch`) | 20.0 mm netclass projection | 7/8 below | **2/8 below** | 6 resolved; **both residuals INTRA-PACKAGE** |
| vs **manifest SELV** (the barrier crossing) | **NOT DERIVABLE** | 1.64–21.96 mm | 1.80–107.16 mm | separation improves hugely; **still INDETERMINATE** |
| vs **HV** classes (functional) | 2.0 mm clearance | 2/8 below | **4/8 below** | **REGRESSION — 3 new inter-component pairs** |

## 1. Which figure applies — and the reason there isn't one

All four nets are `HighVoltage` in Table A (`TEMPER_NET_ASSIGNMENTS`). None is
declared in `elec/domain_manifest.yaml`'s HV or SELV domain, so
`insulation_coordination.requirement_for_nets` **raises
`InsulationDeclarationError`** against every counterparty tried
(`+170V_BUS`, `gnd`, `V_BUS_SENSE`, `PWR_RTN`, `tank-out`):

> `not declared in elec/insulation_manifest.yaml. Every net of
> elec/domain_manifest.yaml's HV and SELV domains must be declared in exactly one
> group; an undeclared net has no requirement and none is assumed.`

That is the module behaving correctly and fail-closed. The consequence is that
**no per-pairing creepage figure exists for these nets at all** — not 4.8, not
8.0, not 20.0. Any barrier-crossing verdict on them is INDETERMINATE by
construction, and clearing a distance is not passing.

The figures that *do* apply are netclass projections, and they are not the same
thing:

| counterparty class | figure | source | what it really is |
|---|---:|---|---|
| `HighVoltage` etc. | **2.0 mm clearance** | `netclass_rules.yaml` `HighVoltage.clearance` | FUNCTIONAL insulation, HV↔HV |
| `HighVoltage` etc. | 0.0 mm creepage | `pair_creepage.generated.yaml` | no creepage backstop for HV↔HV |
| `Power`/`Default`/`FinePitch` | 20.0 mm | `pair_creepage.generated.yaml` | **tank-contaminated** — 20.0 only because `tank-out` shares the `HighVoltage` class (§9.3 of the per-pairing doc) |

**These pads are compliant against one figure and not another, and the
barrier-crossing figure is the one that does not exist.**

## 2. Per pad, exact copper-to-copper

`pad_pair_distance` (exact Minkowski kernel), committed board vs the model-E
placement, reproduced in one process. Intra-package pairs flagged: rotating a
footprint rotates every pad *and* every pad position together, so those
distances are invariant under everything the placer can decide.

### 2a. vs HV classes — bar 2.0 mm functional clearance

| pad | OVP net | committed | counterparty | **model-E** | counterparty | intra? | verdict |
|---|---|---:|---|---:|---|---|---|
| R46.2 | `r_div_top1-p2` | 1.8000 | `+170V_BUS` | **0.9100** | `PWR_RTN` | no | **FAIL** (new) |
| R47.1 | `r_div_top1-p2` | 66.4344 | `+170V_BUS` | **1.6895** | `+170V_BUS` | no | **FAIL** (new) |
| R47.2 | `r_div_top2-p2` | 67.4147 | `+170V_BUS` | **1.6704** | `PWR_RTN` | no | **FAIL** (new) |
| R48.1 | `r_div_top2-p2` | 9.2950 | `power_in.ntc-no` | 4.7162 | `tank-out` | no | PASS |
| R51.2 | `r_adc_top1-p2` | 1.8000 | `+170V_BUS` | 1.8000 | `+170V_BUS` | **yes** | FAIL (unchanged) |
| R52.1 | `r_adc_top1-p2` | 66.4160 | `+170V_BUS` | 6.9742 | `hb-gnd` | no | PASS |
| R52.2 | `r_adc_top2-p2` | 63.6097 | `+170V_BUS` | 8.5532 | `hb-gnd` | no | PASS |
| R53.1 | `r_adc_top2-p2` | 23.1932 | `hb-gnd` | 24.2250 | `w1_2` | no | PASS |

**2/8 → 4/8 below 2.0 mm. The placement makes this bucket worse.**

### 2b. vs manifest SELV — the barrier crossing

| pad | committed | counterparty | **model-E** | counterparty | intra? |
|---|---:|---|---:|---|---|
| R46.2 | 21.9553 | `+3V3` | **88.9254** | `gnd` | no |
| R47.1 | 2.6004 | `RTD_SCK` | **88.0663** | `gnd` | no |
| R47.2 | 2.8112 | `RTD_SCK` | **87.8035** | `gnd` | no |
| R48.1 | 1.8000 | `safety.ovp.comp-inp` | 1.8000 | `safety.ovp.comp-inp` | **yes** |
| R51.2 | 14.9651 | `gnd` | **107.1580** | `gnd` | no |
| R52.1 | 4.1277 | `RTD_SCK` | **32.0467** | `gnd` | no |
| R52.2 | 2.2320 | `RTD_SCK` | **32.8048** | `gnd` | no |
| R53.1 | 1.6423 | `gnd` | 1.8000 | `V_BUS_SENSE` | **yes** |

Six of eight go from 1.6–21.9 mm to 32–107 mm. **Every verdict here is
INDETERMINATE** — the requirement does not exist (§1). The improvement is in
measured separation, not in certified compliance.

### 2c. vs LV classes — 20.0 mm netclass projection

7/8 below → **2/8 below**. The two residuals are **R48.1 ↔ R48.2** and
**R53.1 ↔ R53.2**, both at 1.8000 mm, both **INTRA-PACKAGE**.

## 3. The mechanism, per residual

### 3a. The two persisting residuals are a table defect, not a placement defect

Sheetpaths establish the two divider chains:

```
+170V_BUS -> R46 (r_div_top1) -> r_div_top1-p2 -> R47 (r_div_top2)
          -> r_div_top2-p2 -> R48 (r_div_top3) -> safety.ovp.comp-inp -> R49 -> gnd
+170V_BUS -> R51 (r_adc_top1) -> r_adc_top1-p2 -> R52 (r_adc_top2)
          -> r_adc_top2-p2 -> R53 (r_adc_top3) -> V_BUS_SENSE       -> R54 -> gnd
```

R48 and R53 are the **last top resistor** of each chain. Their two terminals are
the last mid-chain node (`HighVoltage`) and the divider output (`Default` /
`Power`) — so the projection charges **20.0 mm creepage across a single 1206
resistor whose body is 3.2 mm long**. No placement can satisfy that, and it is
not an insulation gap: the two nodes are separated by a 430 kΩ / 169 kΩ series
element, i.e. protective impedance. The 20.0 mm itself is only there because
`tank-out` shares the `HighVoltage` class.

This is structurally identical to T1/T2 — an intra-package shortfall no placement
can fix — but unlike T1/T2 the requirement being charged is itself wrong.

### 3b. The three new sub-2.0 mm HV↔HV pairs are the model's own named gap

§1 of `2026-08-19-per-pairing-placer-solve.md` states it outright:

> **What it still does not encode.** HV↔HV functional pairings ... sit entirely
> on the barrier's HV side; this family says nothing about them.

The barrier model pushes every HV pad to its group's setback from the SELV side.
`pair_creepage` charges HV↔HV **0.0 mm**, so nothing in the encoded model resists
crowding *inside* the HV pocket, and the 2.0 mm functional clearance of
`netclass_rules.yaml` is not a constraint the placer enforces between two
`HighVoltage` nets. R46.2 lands 0.9100 mm from `PWR_RTN`.

**This is a real, placement-caused regression on functional insulation, and it is
the honest residual of the compliant placement.** It was not visible to census 2
(HV↔SELV only) or to census 1 (HV↔HV required = 0.0).

## 4. Census membership — the direct answer to "among the 467 or the 36?"

* **Census 2 (36 → 8):** 8 OVP pads on the board, **0 graded**. Neither set.
* **Census 1 (503 → 132, 467 resolved):** 122 of the 496 committed offender keys
  carry an OVP pad. **120 resolved, 10 introduced, 2 persist.** The 2 persisting
  are exactly R48.1↔R48.2 and R53.1↔R53.2 from §3a. All 10 introduced are against
  `discharge.*` / `power_in.bypass_relay-coil*` nets that sit in `Default` on
  Table A — the same 7 nets `fix/netclass-tables-reconcile` (6f9aa0f63)
  reclassifies to `HighVoltageSignal`; under that reconciliation they become
  HV↔HV and the 20.0 mm stops applying.

## 5. SECONDARY FINDING — the census harness mis-composes the pad angle

Reported, not fixed; it needs its own measurement.

`2026-08-19-per-pairing-placement-compliance.py` builds each pad tuple with
`math.radians(pin.pad_rotation_deg)`. The parser stores that field **relative to
the footprint** — it is `0.0` for every 1206 on this board even though the file
writes `(at -1.4625 0 90)` inside a footprint that is itself `(at ... 90)` — and
`pin_world_position_at` rotates pin **positions** by the component quadrant while
the pad rectangle stays axis-aligned. The pad's copper is therefore modelled in
the wrong orientation whenever the component is not at quadrant 0.

**Convention-independent proof.** Whatever a writer does with pad angles,
rotating a footprint rotates its pads *with* it, so intra-package pad distance
cannot change under re-placement. Measured across the whole board, committed vs
model-E:

| pad-angle handling | intra-package pairs whose distance drifts | worst drift |
|---|---:|---:|
| `pad_rotation_deg` alone (the committed harness) | **1 243** | **5.1500 mm** (K1.13↔14) |
| composed with the component quadrant | **0** | 0.0000 mm |

Consequences on census 2 itself:

| | committed | model-E |
|---|---:|---:|
| as published (`pad_rotation_deg` alone) | 36 | 8 |
| **composed world rotation** | **35** | **5** |

and on the isolator geometry the UNSAT-core argument quotes:

| pair | as published | composed |
|---|---:|---:|
| T1.1↔T1.4 (quadrant 1) | 7.8000 | **9.1000** |
| T2.1↔T2.4 (quadrant 0) | 9.1000 | 9.1000 |

T2 sits at quadrant 0, so composition is a no-op for it — but the §3/§4c tables
of the per-pairing document report **T2 at 7.800 mm exact**, "short by 0.200 mm",
and that figure does not reproduce here under either convention. **The `{T1, T2}`
UNSAT core was produced by the barrier model, not by this kernel, so nothing
above overturns the core** — but the exact-kernel figures quoted alongside it
should be re-derived before they are relied on. Named and handed on.

## 6. What did not reproduce from the brief

The brief's committed-board figures — 0.8625 mm (R53 pad 1 → a `V_BUS_SENSE`
via), 0.91, 1.4006, 1.555, 1.8 — were re-measured with the exact kernel. Only
**1.4006** (R47.2 ↔ R29.2 `sclk`) and **1.8** reproduce.

**0.8625 mm does not reproduce, and its attribution is wrong.** On the committed
board the nearest routed-copper item of any net to R53 pad 1 is 15.7525 mm (an
`i2c_scl_ui` trace on In3.Cu); the nearest `V_BUS_SENSE` via is **18.3283 mm**.
R53.1's nearest foreign copper is a *pad* — R67.2 (`gnd`) at 1.6423 mm. No via or
trace is the nearest neighbour of **any** of the eight pads. The board also
contains **151 zones and zero `filled_polygon`**, so there is no pour geometry
that could supply a closer counterparty. No source for 0.8625 or 1.555 exists
anywhere in `docs/` or `scripts/`.

Two of the eight are also **not** within 2.0 mm of foreign copper on the
committed board: R52.1 at 2.8799 mm and R52.2 at 2.0800 mm.

## 7. Constraints observed

* `pcb/temper.kicad_pcb` sha256 `26981fea…c110b` verified identical before and
  after. Never opened for writing.
* No threshold, clearance, creepage, ratchet or allowlist was changed. No test
  was skipped, `xfail`ed, deleted or weakened. No oracle was re-pinned.
* No new solve was invented: row E of the committed harness was re-run
  (`optimal`, 168/168, 38.9 s) and **verified to be the documented placement** by
  reproducing census 1 exactly — 503 → 132, 467 resolved, 90 introduced — and
  census 2 exactly — 36 → 8 with the same 1/3/4/28 and 4/0/0/4 splits.
* Every figure above is from this session's own run on this branch, except where
  a branch is named.

## 8. Reproduce

```bash
scripts/check_stale_extensions.py      # 10/10 fresh FIRST

python docs/evidence/2026-08-19-per-pairing-route-solve-model-e.py \
    --rows E --emit /tmp/placement_e.json        # from agent/per-pairing-placement-route

python docs/evidence/2026-08-20-ovp-pads-model-e-compliance.py  --placement /tmp/placement_e.json
python docs/evidence/2026-08-20-ovp-pads-census-membership.py   --placement /tmp/placement_e.json
python docs/evidence/2026-08-20-ovp-pads-nearest-copper.py      --placement /tmp/placement_e.json
python docs/evidence/2026-08-20-pad-rotation-composition-census2.py --placement /tmp/placement_e.json
```

## 9. What this leaves open

1. **The four OVP nets are undeclared in `elec/insulation_manifest.yaml`.** Until
   they are, no barrier-crossing verdict on them is possible. They reach full
   `+170V_BUS` under the Clause 8.1.4 single fault, so this is not a bookkeeping
   gap. **Highest-value next action.**
2. **Three HV↔HV functional-clearance pairs at 0.91–1.69 mm are introduced by the
   compliant placement** (§3b). Either the placer gains an HV↔HV functional
   constraint at 2.0 mm, or the placement is not landable as-is.
3. **20.0 mm is charged across single 1206 resistors** (§3a) because `tank-out`
   shares the `HighVoltage` class — the re-partition owned by
   `fix/netclass-tables-reconcile`.
4. **The pad-angle composition defect** (§5) affects every consumer that builds a
   pad tuple from `pad_rotation_deg` alone.
