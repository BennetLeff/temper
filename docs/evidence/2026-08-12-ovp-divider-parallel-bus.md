<!-- provenance: commit=6d0f0312f169df8c065f77b8ef2fe992d906958e dirty=UNKNOWN -->
branch fix/ovp-divider-parallel-bus, base origin/main b33056c95.
pcb/temper.kicad_pcb NOT modified: sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 unchanged,
`git status --short pcb/` empty before and after every step.
pcb/temper.kicad_dru regenerated from scripts/generate_kicad_dru.py (gitignored),
sha256 bad860a0d199e5b4fa35d0643ba68dae1ddecc50ae5f854c27832139b60e6ae4, and
propagated beside every scratch board measured (the #1086 trap), together with
fp-lib-table and libs/.
pumpkin_engine sha256 7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e
source_commit 5bbf650d47d3a07fffd10a44e7c06c43a0a800bd; scripts/verify_pumpkin_engine.py
--require exit 0 before any solve. kicad-cli 10.0.5 via the ~/.local/bin shim.
Placed boards: BASE sha256 7e1dd81f05185adfcad7b5d05020a140eb06faf643d3e11830b08e54f0b40f2a
(bit-identical to PR #1082's heatsink placed board as recorded in the #1095
provenance header -- the baseline here IS the documented heatsink board, not a
re-derivation of it), CHAIN sha256
520e8d1ff17d59650f76a5f233d644f230898f2e4f0c51b29dbd79261071d6b3.
Routed boards: BASE sha256 3376766024a7894787ae0377eb1c4537a586d2971afe27b27cb1a49292cc4b64,
CHAIN sha256 f2d6610c5fac043c843c751592fb67fb4b283a35f987e40a2ae094226a8f13f5.
All routing via scripts/route_board.py --net-batching --batch-size 10.
DRC sampling N=130 per board (R27's threshold), --all-track-errors, .kicad_pro
AND .kicad_dru present, "project resolvable: True".
NO ceiling entry written; power_pcb_dataset/drc_ceiling.json NOT modified. -->

# The OVP divider's parallel bus is a scattered series chain — co-locating it removes 98% of the pair and moves `clearance` by exactly zero

> **Verdict up front.** The two nets are the interior nodes of one
> **series protective-impedance chain**, `safety.ovp.r_div_top1 -> _top2
> -> _top3`, declared in `elec/domain_manifest.yaml` with `min_length: 3`.
> They are not two unrelated nets that happened to converge: they are the
> **two ends of the same middle resistor, R52**. The manifest constrains
> the chain's *topology* and nothing constrains its *geometry*, so the
> placer scatters the three resistors 73.7mm and 110.7mm apart on a
> 152x234mm board. Both interior nodes therefore leave R52 in the same
> direction and traverse the board together. That is the bus.
>
> A placement constraint fixes it completely. `adjacent` (an existing wire
> type, both backends) between consecutive chain members collapses the
> dominant pair **141 -> 3 violations, −98%**, and the x[40,60) band
> **211 (42.1%) -> 108 (21.6%)**.
>
> **And `clearance` does not move: 501 -> 501.** Not "roughly the same" —
> the same integer, at N=130 medians, from a genuinely different placement
> of all 169 components.
>
> This is the result that matters, and it is the opposite of what the task
> hypothesised. Three prior efforts failed to move `clearance` by changing
> *routing*, and concluded it was therefore a placement property. This is
> the first attempt to move it by changing **placement**, with the target
> mechanism fully dissolved, and it does not move either. `clearance` is
> invariant under both.
>
> §4 shows the mechanism of that invariance, which is the new finding
> here: the violations are **fungible**. Killing the dominant pair does
> not remove 141 violations, it *redistributes* them — distinct violating
> net pairs go **38 -> 82** and the pairs needed to cover 80% of the count
> go **5 -> 24**, at an identical total. The board spends the same
> clearance budget regardless of which nets are adjacent.
>
> Heatsink co-location and the PD2/8.0mm isolation barrier both hold on
> the new board, verified by post-check.
>
> On every other axis CHAIN is the best board measured here — aggregate
> **1070** vs BASE's 1133 and the committed board's 1296, two ceiling
> breaches instead of BASE's seven, at *better* completion than committed
> (331 unconnected vs 428).
>
> **The bar was `clearance` <= 386. It was not met (501). Nothing is
> landed, no ceiling entry is written, and `pcb/temper.kicad_pcb` is
> untouched.**
>
> **Separately and unexpectedly (§3.2b): the committed board no longer
> meets its own ceiling either.** Measured here it is `clearance` **402**
> (ceiling 386) and TOTAL **1296** (ceiling 1266) — the brief's stated
> 386/1264 do not reproduce on today's tree, because the generated
> `.kicad_dru` has changed since the ceiling was recorded. The 386 target
> is being applied under a DRC model in which nothing on `main` achieves
> it.

---

## 1. Why the two nets run parallel

### 1.1 They are one resistor's two terminals

`elec/src/modules.ato:2247-2249`:

```
v_bus.line     ~ r_div_top1.p1
r_div_top1.p2  ~ r_div_top2.p1
r_div_top2.p2  ~ r_div_top3.p1
r_div_top3.p2  ~ comp.INP
```

So `safety.ovp.r_div_top1-p2` joins `r_div_top1.p2` to `r_div_top2.p1`,
and `safety.ovp.r_div_top2-p2` joins `r_div_top2.p2` to `r_div_top3.p1`.
**Both terminate on R52** (`r_div_top2`), on opposite pads of one 1206.

The three resistors are not a design choice that could be made
differently for layout convenience. `elec/domain_manifest.yaml` declares
them as a **protective-impedance chain** (IEC 60335-1), where the split
is the safety mechanism:

```yaml
protective_impedance_chains:
  - name: ovp01_comparator_divider
    chain: [safety.ovp.r_div_top1, safety.ovp.r_div_top2, safety.ovp.r_div_top3]
    boundary_a: "+170V_BUS"
    boundary_b: "safety.ovp.comp-inp"
    min_length: 3
```

with the manifest's own warning (~line 338): *"Shorten a chain and the
declaration stops being honoured, so the crossing reappears as a
violation."* Merging the three back into one part is therefore **not
available** — it is the single-fault tolerance argument (131uA normal /
195uA one-shorted / 386uA two-shorted against a ~1.35mA touch-current
limit). **This is not a schematic change that should be made.**

The interior nodes are also, per the same manifest (~line 347),
deliberately **unclassified** — "genuinely mid-chain, neither HV nor SELV
by voltage". That is why they fall to the `Default` netclass, and why all
of the band's violations fire the one rule `"Default routing"` at 0.2mm
rather than any netclass-specific rule.

### 1.2 The chain is scattered across the whole board

Measured from `pcb/temper.kicad_pcb` (read-only), centre-to-centre:

| chain | pair | centre distance | edge-to-edge |
|---|---|---:|---:|
| `ovp01_comparator_divider` | R51 -> R52 | 73.7mm | 69.10mm |
| `ovp01_comparator_divider` | R52 -> R53 | 110.7mm | 80.97mm |
| `ovp01_adc_sense_divider` | R56 -> R57 | 155.1mm | 131.18mm |
| `ovp01_adc_sense_divider` | R57 -> R58 | 64.3mm | 50.06mm |

on a 152x234mm board. The ADC chain's first hop is **155mm** — longer
than the board is wide.

**So the answer to "is it placement, topology, or the router?" is: it is
placement, forced into visibility by topology.** The topology makes the
two nets share an endpoint component (that part is immovable — it is the
safety construction). The *placement* is what turns two millimetre stubs
into two board-spanning traces that necessarily share a corridor. The
router is not implicated: given R52 at one end of the board and R51/R53
at the other, there is no routing of those two nets that does not run
them together for tens of millimetres.

Confirming that the placer, left alone, has no reason to keep them
together — the same solve **without** the new constraint scatters them
*further* than the committed board does (edge-to-edge: R51-R52
**112.15mm**, R52-R53 93.19mm, R56-R57 152.75mm, R57-R58 29.46mm).

### 1.3 The band characterisation, verified not re-derived

`docs/evidence/2026-08-12-clearance-congestion-band.md` is **not on
`main`** — it was reverted by `c87492f38` (#1100, conflict markers) and
its re-land (`dcc66601c`) sits unmerged on
`feat/router-clearance-floor-reland`. Its §1 figures were read from git
history and re-measured here on the BASE board:

| quantity | doc (heatsink board) | BASE, measured here |
|---|---:|---:|
| `clearance` errors | 505 | 501 |
| x[40,60) band | 205 (40.6%) | 211 (42.1%) |
| `r_div_top1-p2` x `r_div_top2-p2` | 121 | **141** |
| `rtd_pan.low_window-out` x `r_div_top2-p2` | 38 | 41 |
| track-track | 407 | 406 |
| pad-pad | 0 | 0 |
| `actual 0.1500` bucket | 136 | 138 |
| `actual 0.1972` bucket | 149 | **149** |

The characterisation **reproduces**. (The BASE placed board is
bit-identical to the heatsink board — sha256 `7e1dd81f…` — so the
residual differences are the routing nondeterminism the doc itself
reports, not a different board.)

## 2. What was changed

One new module, `packages/temper-placer/src/temper_placer/placer/cp_sat/protective_impedance_colocation.py`,
following `heatsink_colocation.py`'s pattern exactly.

* **Only `adjacent` is emitted** — already registered in both backends
  (Pumpkin `main.rs:358`, OR-Tools `handlers/adjacent.py:22`). No new wire
  type, so the pinned engine binary is used unmodified and neither backend
  is silently under-constrained. No rotation pin: a series chain has no
  shared mechanical face, so there is no orientation requirement.
* **Chain membership is derived, not transcribed.** The manifest names
  atopile instance paths; the board names nets. They meet at the interior
  node, which atopile emits as `f"{instance}-p2"`, so the two components
  carrying a pad on `safety.ovp.r_div_top1-p2` *are* the consecutive pair.
  Verified: the derivation recovers exactly `(R51,R52) (R52,R53)
  (R56,R57) (R57,R58)` — 4 pairs from the manifest's 2 chains of 3. A
  refdes reshuffle cannot silently decouple the constraint from the parts
  it means (the `Q1`/`Q2` failure mode `heatsink_colocation.py`
  documents).
* `MAX_CHAIN_GAP_MM = 10.0` is recorded in the module as a **declaration,
  not a derivation** — no in-repo document states how close chain members
  must sit. It is deliberately loose (~25x the 0.40mm courtyard floor) so
  that it composes rather than tips the model infeasible, and it still
  collapses the committed scatter 7-15x.

`pcb/temper.kicad_pcb` is **not modified**.

## 3. Does `clearance` move? No.

Two boards, identical in every respect except the chain constraint: same
base (netclass + courtyard tau=0.40mm), same PD2/8.0mm isolation barrier
with all 8 isolators, same shared-heatsink co-location at common rotation
1, same engine, same seed, same router flags.

### 3.1 The constraint does what it claims

| | BASE | CHAIN |
|---|---:|---:|
| chain pairs within 10mm | **0/4** | **4/4** |
| `r_div_top1-p2` x `r_div_top2-p2` clearance violations | **141** | **3** |
| x[40,60) band | 211 (42.1%) | 108 (21.6%) |
| track-track clearance errors | 406 | 294 |
| `actual 0.1500` bucket | 138 | 65 |
| `actual 0.1972` bucket | 149 | 30 |
| segments emitted | 4497 | 3516 |
| item occurrences on F.Cu | 680 (70.5%) | 413 (44.7%) |
| item occurrences on B.Cu | 285 (29.5%) | 511 (55.3%) |
| fire rule `Default routing` | 498/501 | 497/501 |

The named mechanism is **gone**: −98% on the pair the task was set to
resolve.

Two things worth noting because they were candidate fixes in their own
right. First, the rule split is unchanged — 498/501 and 497/501 fire
`"Default routing"` at 0.2mm, so this remains a single-rule population and
no netclass-specific rule became load-bearing. Second, **the F.Cu
concentration corrected itself**: the task suggested moving one net to
another layer on the grounds that F.Cu carrying 70% of items meant layer
assignment was doing little work. Co-locating the chains flipped the
board to B.Cu-majority (70.5% F.Cu -> 44.7%) **without any layer-assignment
change at all**, and `clearance` still did not move. That is direct
evidence against the layer hypothesis as well: the imbalance was a
downstream symptom of where the long nets ran, not an independent cause.

### 3.2 The aggregate does not follow

Medians over N=130, `[min-max]` where the category varied. Ceiling column
is `power_pcb_dataset/drc_ceiling.json`'s `violations_by_type`; a category
absent from it has an implicit ceiling of 0.

All three columns measured here, N=130 each, same harness, same
regenerated `.kicad_dru`. **BASE is bit-identical to the heatsink board**
(sha256 `7e1dd81f…`), so its column is that board measured, not quoted.

| category | ceiling | committed | BASE (= heatsink) | **CHAIN** |
|---|---:|---:|---:|---:|
| `clearance` | 386 | 402 [401–402] ❌ | 501 [499–506] | **501 [499–505]** ❌ +115 |
| `shorting_items` | 199 | 199 [199–200] | 137 | **105** ✅ |
| `track_width` | 199 | 199 | 199 | **199** ⚠️ at ceiling |
| `creepage` | 186 | 200 [198–200] ❌ | 102 [100–102] | **142 [140–142]** ✅ |
| `solder_mask_bridge` | 154 | 154 | 49 | **8** ✅ |
| `hole_clearance` | 105 | 105 | 89 | **94** ✅ |
| `courtyards_overlap` | 11 | 11 | 19 | **16** ❌ +5 |
| `copper_edge_clearance` | 10 | 10 | 13 | **3** ✅ |
| `annular_width` | 4 | 4 | 6 | **0** ✅ |
| `drill_out_of_range` | 4 | 4 | 6 | **0** ✅ |
| `via_diameter` | 4 | 4 | 6 | **0** ✅ |
| `hole_to_hole` | 3 | 3 | 0 | **2** ✅ |
| `tracks_crossing` | 1 | 1 | 6 | **0** ✅ |
| **TOTAL errors** | **1266** | 1296 [1294–1296] | 1133 [1129–1137] | **1070 [1067–1074]** ✅ |
| `unconnected_items` | — | 428 | 326 | **331** |

**CHAIN breaches two ceilings** — `clearance` +115 and
`courtyards_overlap` +5 — down from BASE's seven, and its aggregate is
the lowest of the three boards (1070 vs 1133 vs 1296). Four categories
that BASE breached (`annular_width`, `drill_out_of_range`, `via_diameter`,
`tracks_crossing`) go to **zero**. On every axis except `clearance` this
is the best board in the comparison, at *better* completion than the
committed board (331 unconnected vs 428).

It is still not landable, because `clearance` is the blocker and it did
not move.

### 3.2b The committed board no longer meets its own ceiling

**This was not expected and it changes how the 386 target should be
read.** Measured here at N=130 against a `.kicad_dru` regenerated from
`scripts/generate_kicad_dru.py` on today's `main`, the **committed**
board — `pcb/temper.kicad_pcb`, unmodified, sha256 `6928b7c8…` — reports:

* `clearance` **402**, against its recorded ceiling of **386** (+16);
* `creepage` **200**, against **186** (+14);
* TOTAL **1296**, against `error_ceiling` **1266** (+30).

The brief supplied 1264 total / `clearance` 386 as the committed
reference. Those figures do **not** reproduce on today's tree. The DRU
this run generated hashes `bad860a0…`, where the #1095 provenance header
records `ed81027e…` for the same generator — so the rule set has changed
underneath the ceiling since it was recorded (the netclass
case/coverage fix in #1023 and the tank HV↔HV creepage work in
#1098/#1100 are the candidates; **attributing it precisely would need a
bisect this run did not do, and it is reported as unattributed rather
than guessed**).

The consequence for this task is concrete: **`clearance` ≤ 386 is not a
bar the committed board itself clears under the current DRC model.**
Any board measured today is being graded against a ceiling recorded
under a different rule set. That should be resolved — by re-measuring the
ceiling or by pinning the DRU alongside it — before `clearance ≤ 386` is
used as a landing gate for anything.

### 3.3 Pad connectivity — reported as pad connectivity, and labelled as such

This is `route_board.py`'s PRIMARY metric (`pad_connectivity_audit`), not
topology-solved net counts, which are a different metric that has misled
twice.

| | BASE | CHAIN |
|---|---|---|
| **pad-connected (PRIMARY)** | **55/139** | **56/139** |
| fake-completion | 59 | 46 |
| honest-gap | 25 | 37 |
| topology-solved nets (secondary) | 86/103 (83.5%) | 75/103 (72.8%) |
| route wall time | 502.9s | 534.4s |

BASE reproduces the heatsink board's documented **55/139** exactly.
Pad connectivity is **unchanged to within one net** (+1). The topology
figure falls 86 -> 75, the same completion cost every honest constraint
in this lineage has paid.

## 4. Why it does not move: the violations are fungible

This is the new mechanism, and it is measured, not argued.

| | BASE | CHAIN |
|---|---:|---:|
| `clearance` total | 501 | 501 |
| distinct violating net pairs | **38** | **82** |
| largest single pair | 141 | 110 |
| pairs needed to cover 80% | **5** | **24** |

Co-locating the chains did not delete 138 violations. It **spread them**:
the count is conserved while its support more than doubles. The new
dominant pair, `power_in.bypass_relay-coil1` x
`rtd_pan.rail_monitor-outa` at **110**, is a different pair of long nets
of exactly the same shape, and it was not in the top 10 before.

The composition inverted the same way the routing repairs inverted it —
track-track 406 -> 294 while pad-track rose 92 -> 190.

**Read together with the three prior routing results, the conclusion is
stronger than "clearance is a placement property".** It is:

| lineage | what changed | `clearance` |
|---|---|---:|
| heatsink / BASE | — | 501 |
| #1095 variant A | router clearance floor 0.15 -> 0.2 | 502 |
| #1095 variant B | + trace width 0.25 -> 0.20 | 500 |
| #1095 variant C | + per-class rasteriser derivation | 500 |
| **CHAIN (this doc)** | **placement: chains co-located** | **501** |

Five materially different copper realisations, two different placements,
three clearance models, one number. `clearance ~ 500` is not a property
of the router *or* of a particular placement — it survives changing
either. On the available evidence it is a property of **this netlist at
this board area under this DRC model**: 169 components and ~100 routed
nets in 152x234mm produce ~500 sub-0.2mm adjacencies no matter how they
are arranged, and moving parts only decides which nets pay.

**What that implies for the 386 target.** Measured on today's tree, the
committed board reaches `clearance` **402** with **428** unconnected
items; BASE and CHAIN both reach **501** with **326**/**331**. The
~100-error gap tracks how much copper is on the board, not how well it is
arranged: the committed board is "better" on `clearance` largely because
~100 more nets are simply not routed, and every honest repair in this
lineage has bought its clearance reduction with completion.

Getting `clearance` to 386 *at better completion than the committed
board* is therefore not reachable by rearranging 169 components in
152x234mm. It needs either **more board area**, a **coarser DRC model**,
or an accepted completion loss — all three are design decisions, not
placement searches. **That is the honest answer this exercise produces,
and it is the same answer from the placement side that #1052 and #1095
reached from the routing side.**

## 5. Do both constraints still hold? Yes.

* **PD2/8.0mm isolation barrier, all 8 isolators** — `{C6, K1, K2, K3,
  PS1, T1, U3, U7}`, corridor Y [113.0, 121.0]mm, 43 HV-only components
  bounded `y_end <= 113.0` and 106 SELV-only bounded `y_start >= 121.0`.
  The harness's inherited `--relax U6` default is **inert on this board**:
  U6 is not in this board's isolator set, so the relax filter matches
  nothing and **all 8 isolators are fully enforced** (rotation pin plus
  both pad-cluster straddle bounds). Posted into the same solve as the
  chain constraint; the engine returned `optimal`.

  Verified **independently of the solver**, by re-classifying the solved
  board's own geometry against the manifest and measuring every HV-only
  and SELV-only footprint's extent against the corridor:
  **0 barrier crossings on both boards.** (Checking the post-solve
  geometry rather than trusting that a constraint was posted is the
  difference between "the constraint was in the payload" and "the board
  satisfies it".)
* **Shared-heatsink co-location** — U5/U6 both at rot 1 (90deg), centres
  (111.33, 83.10) and (111.55, 58.83), perpendicular offset 0.22mm.
  `check_heatsink_colocation` post-check: **SATISFIED**.
* **Chain co-location** — `check_chain_colocation` post-check: all 4
  pairs within 10.0mm.

All three compose. The solve is not marginal: `optimal` in **1.81s**
against 1.67s for the barrier+heatsink baseline, i.e. the chain
constraint costs ~0.14s and does not push the model anywhere near
infeasibility. **No design conflict.**

## 6. Follow-ups this produced

1. **At least three more series chains are scattered and undeclared.**
   `modules.ato:1323,1329` wire `r_dis1a.p2 ~ r_dis1b.p1` and
   `r_dis2a.p2 ~ r_dis2b.p1`; `power_in.r_zcd_top1-p2` is a third. None
   is in `protective_impedance_chains`, so this constraint does not cover
   them. Measured centre distances:

   | net | committed | BASE | CHAIN |
   |---|---:|---:|---:|
   | `discharge.r_dis1a-p2` (R11-R12) | 126.6mm | 82.7mm | 73.2mm |
   | `discharge.r_dis2a-p2` (R13-R14) | 135.1mm | 116.4mm | 88.1mm |
   | `power_in.r_zcd_top1-p2` (R6-R7) | 169.6mm | 119.0mm | **197.8mm** |

   `discharge.r_dis1a-p2` and `discharge.r_dis2a-p2` appear in the top
   net pairs of *both* boards. Extending the constraint to them is a
   one-line change once the manifest declares them — but §4 predicts it
   will redistribute, not reduce, the aggregate, and that prediction
   should be tested rather than assumed.

2. **The shared venv's `temper_orchestration` extension is stale, and
   `scripts/route_board.py` cannot run on `main` because of it.** The
   installed `.so` is dated Aug 11 19:59; `RouterPipeline` landed
   Aug 12 in `08b1ee8a2` (U-G). Any route on today's `main` with this venv
   dies at `_pipeline_core.py:358` with `AttributeError: module
   'temper_orchestration' has no attribute 'RouterPipeline'`. Worked
   around here by building the crate into a private target dir and
   shadowing the module on `PYTHONPATH` — the shared venv was
   deliberately **not** touched, since other worktrees share it. **This
   needs a real fix (rebuild + reinstall) before anyone else routes.**

3. **`drc_ceiling.json` is stale against the DRU that grades it** (§3.2b).
   The committed board breaches its own recorded `clearance` and
   `creepage` ceilings on an unmodified tree. Either the ceiling needs
   re-measuring under the current rule set, or the `.kicad_dru` hash needs
   pinning beside it so this drift is detectable. Until then no
   `clearance` target derived from that file is meaningful. **This blocks
   interpreting any landing gate, including the one set for this task**,
   and it is the highest-value item on this list.

4. `docs/evidence/2026-08-12-clearance-congestion-band.md` is referenced
   by ongoing work but exists only in git history. Either re-land
   `feat/router-clearance-floor-reland` or restore the document; right now
   the board's best clearance analysis is not on `main`, and the 0.15
   clobber it diagnoses (`_pipeline_core.py:84`) is still live.

## 6b. Test status

`packages/temper-placer/tests/placer/cp_sat/test_protective_impedance_colocation.py`
— **7 passed**. The properties chosen are the ones that break silently:
membership-derivation drift, a vacuous checker (it asserts the committed
board *fails*, with every gap >5x the bound so it is not
tolerance-sensitive), and emission of a wire type only one backend
registers.

`packages/temper-placer/tests/placer/cp_sat` — **245 passed, 5 skipped,
1 failed** at the point the run was stopped.

* The one failure, `test_erc_gate.py::TestErcGateCheck::test_erc_clean`,
  is **pre-existing on `main` and not caused by this change**, verified by
  running it against the unmodified main checkout, where it fails
  identically. This change adds one module that nothing in the production
  path imports, so it cannot reach the ERC gate.
* The run was **stopped, not completed**, at `test_hybrid_pour_stitch_measurement.py`
  (a long benchmark) because it was starving the DRC campaigns of CPU.
  **The remaining ~40% of that directory is therefore UNMEASURED and is
  reported as unmeasured, not as passing.**

## 7. What was NOT done, deliberately

* `power_pcb_dataset/drc_ceiling.json` **not modified**; no
  `Ceiling-Approval:` trailer, no `_march` entry. The bar (`clearance`
  <= 386) was **not** met, so writing ceiling paperwork would be the
  failure that closed PR #1049.
* `pcb/temper.kicad_pcb` **not touched** — sha256
  `6928b7c8…` unchanged, `git status --short pcb/` empty throughout.
* **The schematic was not changed.** Merging the chain would be the only
  topology fix available, and §1.1 shows it is exactly what the safety
  declaration forbids.
* `test_production_board_routing_drc_regression` **not run** — this is not
  PR #1101's branch, where it routes monolithically and OOMs at 58.9 GB.
* The router's `default_clearance_mm = 0.15` clobber
  (`_pipeline_core.py:84`) **left alone** — it is #1095's subject, still
  unmerged, and changing it here would confound this measurement.
