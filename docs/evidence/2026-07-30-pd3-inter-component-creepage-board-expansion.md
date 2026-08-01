# Does board expansion help the inter-component (bystander) creepage violations?

<!-- provenance: commit=57f0c7550a312bafd69d14f7ae8c0ace16fa12eb dirty=false -->

**Date:** 2026-07-30
**Base:** `origin/main` at `8d188403` (`fix(evidence): verify provenance
commits resolve, not just their shape (#489)`), confirmed an ancestor of
`origin/main` and, separately, that `0a8e7194` (the rotation-convention
fix) is an ancestor of `origin/main` via `git merge-base --is-ancestor
0a8e7194 origin/main` (exit 0). Work done in a dedicated worktree at
`/Users/bennet/Desktop/temper-worktrees/pd3-inter-component`, branch
`experiment/pd3-inter-component-measurement`, branched directly from
`origin/main`. **Not** the primary repo checkout at
`/Users/bennet/Desktop/temper` -- never touched.
**Tool commit:** `1dfc93b9` ports `scripts/measure_cross_domain_creepage.py`
and its test suite (24/24 passing on this checkout) from branch
`feat/pairwise-creepage-tool` (`5401a827f`, itself off `46d4b4c8`) onto the
current `origin/main` tip, since that branch predates `origin/main` by many
commits and the tool did not exist on `main` yet.
**Scope touched (this worktree only):** `scripts/measure_cross_domain_
creepage.py` (new, ported), `scripts/tests/test_measure_cross_domain_
creepage.py` (new, ported), this document. **`pcb/temper.kicad_pcb`,
every footprint, `elec/src/`, and every safety constant are untouched** --
`git status --short` before this document's commit shows only the two
tool files plus this doc. Every board-position variation below is a
**pure in-memory Python object mutation** performed after `load_board()`
returns (`dataclasses.replace()` on `PadInfo`, `shapely.affinity.translate()`
on `FootprintBody.polygon`) -- no temp board file was ever materialised on
disk anywhere, in-repo or out.
**Method:** `make venv-isolate` run first. Every invocation `uv run
--no-sync`. No `git stash` used. The one-off model driver
(`respread_model.py`) is, per this repo's own established precedent for
such drivers (`docs/evidence/2026-07-29-cross-domain-creepage-pd2-vs-pd3.md`
and `docs/evidence/2026-07-30-pd3-board-expansion-measurement.md`), **not
committed** -- it lives at
`/private/tmp/claude-501/-Users-bennet-Desktop-temper/413756c0-69f4-4db3-98b7-0b98b4a5e1f8/scratchpad/pd3/respread_model.py`
and imports `scripts/measure_cross_domain_creepage.py`'s own functions
rather than reimplementing them.

---

## Headline

**Board expansion DOES help the inter-component population -- unlike the
isolator population, which `docs/evidence/2026-07-30-pd3-board-expansion-
measurement.md` already proved is structurally invariant to board size.**

At the real board (152x234mm) and 12.6mm (PD3), there are **196 violating
HV<->SELV pad pairs (75 component-pair groups)**, of which **157 pairs / 68
groups are inter-component** ("bystander" pairs -- HV copper routed near
SELV copper with no barrier component's own body between them) and **39
pairs / exactly 7 groups are intra-component** (`C6, K1, K2, K3, T1, U3,
U7` -- the same 7-of-8 isolator set the CP-SAT experiment found, an
independent cross-check between two unrelated tools).

An idealised uniform re-spread **model** (not a measurement -- see Sec. 3)
shows the inter-component count falling fast with board growth and the
intra-component count staying **exactly, bit-for-bit invariant** at every
scale tested (sanity check passed, Sec. 4):

| Board size (model) | Linear scale | Inter-component violations | vs. baseline |
|---|---:|---:|---:|
| 152 x 234mm (real, measured) | 1.00x | 157 | -- |
| 190 x 292mm | 1.25x | 61 | -61% |
| 228 x 351mm | 1.50x | 36 | -77% |
| **304 x 468mm** (the prior CP-SAT experiment's own **+100%** outer bound) | **2.00x** | **17** | **-89%** |
| 456 x 702mm | 3.00x | 2 | -99% |
| 608 x 936mm | 4.00x | 0 | -100% |

At the same board-growth envelope the sibling CP-SAT experiment already
tested (up to +100% per dimension), this idealised model resolves **89% of
today's inter-component violations** -- a sharp contrast with the isolator
population, which stayed at 7/8 infeasible across the identical size sweep
because board size structurally cannot enter that calculation at all.

**The residual that does NOT resolve, even at 2x-3x linear board growth, is
small and concentrated in two functionally-coupled clusters** (Sec. 5):
switch-node snubber caps `C17`/`C22` packed ~4.3mm from a nearby `+3V3`/
`PWM_LS` SELV cluster (`R32`, `R26`, `L2`, `U15`, `U13`), and the tank
current-sense resistor `R30` packed close to the OVP comparator's own sense
input `R54.1(safety.ovp.comp-inp)` and other SELV sense/reference parts
(`R1`, `R73`). The `R30`/OVP cluster fully resolves by 2x-3x scale; the
`C17`/`C22` <-> `R32` pair is the most stubborn and, by extrapolation of its
own (exactly linear-in-scale, once the fixed intra-footprint pad offset is
accounted for) trend, needs roughly **3.75x linear scale (~570 x 880mm)** to
clear under this idealised model -- a board size with no plausible
relationship to a countertop induction cooker, so this pair should be
treated as **not resolvable by board expansion in practice**, even though
the model shows it is not infinitely stuck either.

---

## 1. Baseline measurements (real board, real placement, both thresholds)

Board: `pcb/temper.kicad_pcb` (169 footprints, 164 with a usable F.Fab/
F.CrtYd body outline; 521 pads total, 99 HV / 221 SELV per
`elec/domain_manifest.yaml`; 0 back-side pads -- the R(+theta)/R(-theta)
convention ambiguity does not apply to this board). Denominator: 99 x 221 =
**21879 cross-domain pairs examined at every threshold**, the full space,
not a pre-filtered subset.

```
uv run --no-sync python scripts/measure_cross_domain_creepage.py --min-creepage-mm 8.0 --json .../baseline_8.0.json
uv run --no-sync python scripts/measure_cross_domain_creepage.py --min-creepage-mm 12.6 --json .../baseline_12.6.json
```

| Threshold | Violating pairs | Violating component-pair groups | Inter-component pairs | Inter-component groups | Intra-component pairs | Intra-component groups |
|---|---:|---:|---:|---:|---:|---:|
| 8.0mm (PD2) | 45 | 23 | 41 | 21 | 4 | 2 (`K2`, `K3`) |
| 12.6mm (PD3) | 196 | 75 | 157 | 68 | 39 | 7 (`C6`, `K1`, `K2`, `K3`, `T1`, `U3`, `U7`) |

("Pairs" = individual HV-pad<->SELV-pad findings; "groups" = collapsing all
pairs between the same two component references into one, matching the
grouping convention implied by the task brief's "57 violating groups"
figure. Grouping by component reference reproduces the exact intra-component
isolator set -- `C6, K1, K2, K3, T1, U3, U7` -- independently confirming
`docs/evidence/2026-07-30-pd3-board-expansion-measurement.md`'s CP-SAT-
derived 7-of-8 infeasible-isolator set via a completely different tool and
method.)

**Discrepancy from the task brief's stated 57 groups / 50 inter / 7 intra:**
this measurement finds 75 groups / 68 inter / 7 intra at 12.6mm on the
pinned commit above. The intra-component figure matches exactly (7). The
totals do not, consistent with the task brief's own caveat ("counts have
moved repeatedly today as the board changed") -- not chased further here
since the board state for this exact, pinned commit is what is reported,
and re-deriving an unpinned prior figure is out of scope. **All numbers in
this document are for commit `8d188403` + the ported tool commit
`1dfc93b9`, nothing else.**

Body-class breakdown at 12.6mm (all 196 violations): `body_free` (fixable
by a routed slot) 26, `body_crossing` (not fixable by a slot at the
*current* placement) 144, `unknown` (no body outline data) 26. Restricted to
the 157 inter-component pairs: `body_free` 26, `body_crossing` 105,
`unknown` 26. Note `body_crossing` here means "crosses a body at today's
placement" -- it does NOT mean "unfixable by re-layout," since moving the
crossing component itself is exactly a re-layout action; see Sec. 5.

## 2. Measurement, not model: additional separation needed, at the real placement

For every one of the 157 inter-component pairs violating at 12.6mm, at the
**real, unmodified board**, `12.6mm - distance_mm` is a direct measurement
of the shortfall -- no model involved.

| Additional separation needed | Pad pairs (of 157) | Component-pair groups, worst-pair-per-group (of 68) |
|---|---:|---:|
| < 1mm | 30 | 4 |
| 1-2mm | 35 | 20 |
| 2-5mm | 58 | 25 |
| 5-10mm | 32 | 17 |
| >= 10mm | 2 | 2 |

Median shortfall: 2.65mm. Mean: 3.36mm. Only two pairs need 10mm or more:
`C17.2(hb.gate_hs.driver-p2) <-> R32.1(+3V3)` (11.695mm, the single worst
pair in the whole dataset at 12.6mm) and `C22.2(hb.gate_hs.driver-p2) <->
L2.2(+3V3)` (10.631mm) -- the same cluster the re-spread model
independently flags as its own worst case (Sec. 5). This is the "how much
would any re-layout have to buy, without assuming a specific one" bound
the task brief asked for as the more honest number: most of this population
is a few mm short, not tens of mm short, which is consistent with (though
does not by itself prove) the re-spread model's finding that most of it
resolves at modest board growth.

## 3. The idealised re-spread model -- method and justification

The tool measures a *fixed* board; expanding `pcb/temper.kicad_pcb`'s
outline alone changes nothing; nothing else moves. Per the task brief, two
options were considered:

1. **Uniform affine re-spread**: scale every component's position outward
   from the board centre in proportion to how much the board outline
   grows, holding each component's own physical size and internal pad
   geometry fixed (parts don't get bigger, they just move apart). Answers
   "if the layout were re-spread proportionally into a bigger board, how
   many pairs resolve?"
2. **Additional-separation-needed distribution** (Sec. 2): bounds what any
   re-layout could achieve without assuming one, by measuring the shortfall
   directly at the real placement.

**Both were done.** Sec. 2 is the *measurement* (no model, no assumption
about how a re-layout would actually behave). This section is the *model*:
it makes a specific, stated assumption (proportional outward re-spread from
the board centre) in order to give a concrete, falsifiable answer to "does
more area actually help," and its own worst-case pair (Sec. 5) is
cross-checked against Sec. 2's independent, model-free shortfall ranking --
they agree on which pair is hardest, which is the cross-validation the task
brief asked for between the two approaches.

**Implementation, precisely:** for board-centre `(96, 137)` (measured
directly from the real board's `Edge.Cuts` `GrPoly`, bbox X 20..172mm / Y
20..254mm = 152 x 234mm, matching `docs/evidence/2026-07-30-pd3-board-
expansion-measurement.md`'s independently-stated board size) and a scale
factor `s`, every footprint's own placed position `(fx, fy)` (read directly
from the `.kicad_pcb`, independent of which of its pads are HV/SELV-
classified, so every footprint gets a translation vector, not just ones
with classified pads) maps to `(96 + s*(fx-96), 137 + s*(fy-137))`. The
resulting per-footprint translation delta is then applied as a **rigid
translation** (not a scale) to every one of that footprint's own
`PadInfo.cx/cy` (and `cx_alt/cy_alt`, so the rotation-convention-sensitivity
machinery still works on the moved board) and to that footprint's own
`FootprintBody.polygon` (via `shapely.affinity.translate`, so body-crossing
classification stays geometrically consistent with the pads that moved with
it -- a body left behind at its old position while its own pads moved would
have produced meaningless crossings). `measure_all_pairs`/
`classify_violations` are then re-run, unmodified, from
`scripts/measure_cross_domain_creepage.py` against the moved pad/body sets.

**This is a model, explicitly**: real re-layout is not a uniform proportional
spread -- it is subject to routing congestion, connector/mounting-hole
positions, and the actual shape of each functional cluster, none of which
this model represents. It is presented as an **idealised upper bound** on
what proportional-growth alone could buy, not a claim about what an actual
re-layout would achieve. A real re-layout is more likely to do *worse* than
this idealised bound than better.

## 4. Sanity check: intra-component invariance (per task brief, run first)

**PASSED**, exactly, at every scale tested. The rigid-per-footprint-
translation construction guarantees intra-component pad-to-pad distances
cannot change (both pads of a single footprint pair move by the identical
delta), and this was verified numerically, not just assumed: all 45
intra-component HV<->SELV pad pairs were re-measured at scale 1.25, 1.5,
2.0, 3.0, and 4.0, and every one showed **`max |distance_mm change| =
0.000000000mm`** versus the scale-1.0 (identity) baseline -- bit-identical,
not merely "close." The set of violating intra-component references also
stayed exactly `{C6, K1, K2, K3, T1, U3, U7}` at every scale, with zero
additions or removals. Also, scale=1.0 (identity transform) reproduces the
real-board baseline exactly: 196 total violations, 157 inter, 39 intra --
matching Sec. 1's direct measurement bit-for-bit, confirming the model
implementation itself introduces no spurious drift at the identity point.

## 5. Which inter-component violations survive board growth, and why

At 2.0x scale (304 x 468mm, the prior experiment's own tested outer bound),
17 of 157 inter-component pairs remain (all listed; none are `unknown`-only
artifacts of missing body data at this scale):

```
7.486mm short  C17.2(hb.gate_hs.driver-p2)     <-> R32.1(+3V3)
5.600mm short  R30.1(tank.c_tank1-p2)          <-> R1.2(power_in.bypass_relay-coil1)
5.239mm short  R30.2(tank-out)                 <-> R1.1(+15V)
4.546mm short  C17.1(hb.gate_hs.driver-p1-1)   <-> R32.1(+3V3)
3.135mm short  R30.2(tank-out)                 <-> R73.1(+3V3)
2.685mm short  R30.1(tank.c_tank1-p2)          <-> R32.1(+3V3)
2.660mm short  C17.1(hb.gate_hs.driver-p1-1)   <-> R26.1(PWM_LS)
2.003mm short  C22.1(hb.gate_hs.driver-p1-1)   <-> U15.4(RTD_HW_FAULT)
1.894mm short  R30.1(tank.c_tank1-p2)          <-> R1.1(+15V)
0.912mm short  C17.1(hb.gate_hs.driver-p1-1)   <-> U13.3(gnd)
0.674mm short  C22.1(hb.gate_hs.driver-p1-1)   <-> U15.3(gnd)
0.649mm short  C22.2(hb.gate_hs.driver-p2)     <-> U15.4(RTD_HW_FAULT)
0.648mm short  R30.1(tank.c_tank1-p2)          <-> R54.2(gnd)
0.402mm short  R30.2(tank-out)                 <-> R32.1(+3V3)
0.367mm short  C22.2(hb.gate_hs.driver-p2)     <-> L2.2(+3V3)
0.280mm short  R30.1(tank.c_tank1-p2)          <-> R54.1(safety.ovp.comp-inp)
0.020mm short  C22.1(hb.gate_hs.driver-p1-1)   <-> C16.1(+15V)
```

These fall into exactly two footprint clusters, both packed extremely
close together *today* (baseline footprint-centre separation, not pad
separation): `C17`/`R32` are only **~4.3mm apart** centre-to-centre;
`R30`/`R54`/`R1`/`R73` are a similarly tight cluster. Under a uniform scale
about a distant board centre, two footprints already almost co-located
move almost in lockstep (both roughly the same direction and radius from
centre), so their *separation* only grows linearly in `s` from a small,
mostly-fixed intra-footprint-offset baseline -- it does not "snap open" the
way two footprints on opposite sides of the board would. Solving that
linear trend for the worst pair (`C17.2<->R32.1`: 5.114mm at s=2, 9.386mm at
s=3) for the 12.6mm target gives **s ~= 3.75** (a ~570 x 880mm board) before
it clears in this model; every other pair in the cluster clears earlier (by
s=4.0, all 17 are resolved, confirmed by direct re-run).

**Assessment, not a measurement:** `R30`'s cluster (tank current-sense,
including the OVP comparator's own sense input `R54.1(safety.ovp.comp-inp)`)
is exactly the kind of pairing where a real design argument for necessary
proximity could exist -- an over-voltage sense input arguably wants a short,
low-noise trace to the node it's protecting. But the model shows this
specific cluster *does* fully resolve by 2x-3x scale, so whatever proximity
argument applies here is not so strong that it survives realistic expansion;
it reads more like "currently packed tight because there was no reason to
spread it," not "must be adjacent by function." The `C17`/`C22` <-> `R32`/
`L2` pair (switch-node snubber caps against nearby SELV logic/reference
pins) is the one genuinely stubborn case, needing an unrealistic ~3.75x
linear board growth to clear even in this idealised, generous model -- for
a countertop appliance, that is not a plausible design point, so **this
pair should be treated as not resolvable by board expansion in practice**,
regardless of what the infinite-scale limit of the model eventually shows.

## 6. Answering the task's headline question

**Of the 157 inter-component pad-pair violations measured at 12.6mm on this
pinned commit:**

- **~140 pairs (89%)** are plausibly resolvable by additional board area
  plus re-layout: the idealised re-spread model already clears them by 2x
  linear board growth (304x468mm), the same envelope the sibling CP-SAT
  isolator experiment tested and found *isolators* structurally unaffected
  by. This is a model result, not a measurement, and a real (non-uniform)
  re-layout could plausibly do somewhat worse than this idealised bound --
  but the shortfall distribution in Sec. 2 (median 2.65mm, 78% of pairs
  needing under 5mm more) independently supports that most of this
  population is a modest-distance problem, not a structural one.
- **A small residual, on the order of a handful of pairs (17 at 2x scale,
  narrowing to essentially 1 component-pair -- `C17`/`C22` <-> `R32`/`L2`
  -- by 3x scale)** is not plausibly resolvable by board expansion at any
  size this product could reasonably use. This is not because the two nets
  "must" be routed close by function in the strong sense the isolator
  population is (those parts are not barrier/isolator components at all,
  per the CP-SAT experiment's own isolator list) -- it is because they are
  packed close enough *today*, on two nearly-co-located footprints, that a
  uniform proportional spread barely separates them; only a board several
  times larger in each dimension would. A **non-uniform, purpose-built
  re-layout** that deliberately moves just this cluster apart (rather than
  relying on proportional growth) was **not evaluated here** and is the
  most likely real fix -- this document does not rule that out, only rules
  out "board expansion" in the generic, whole-board-growth sense the task
  posed.

**Verdict: board expansion buys most, but not all, of the inter-component
half of this problem.** This is the opposite conclusion from the isolator
population (`docs/evidence/2026-07-30-pd3-board-expansion-measurement.md`),
where board size is proven structurally incapable of ever helping. Here,
board size helps substantially (a model result) and the raw shortfalls are
mostly small (a measurement), but a real design still needs either extra
area *and* a re-layout, or a targeted local re-layout of the `C17`/`C22`/
`R32`/`L2` cluster specifically, to fully clear the inter-component
population -- board area alone, without any re-layout at all, buys nothing
(the outline-only-growth premise stated in the task brief), and even an
idealised proportional re-layout leaves a small, identifiable residual.

## What was not established

- **No non-uniform / purpose-built re-layout of the stubborn cluster was
  attempted.** The uniform re-spread model is a lower bound on what
  proportional growth buys, but says nothing about whether a targeted
  local move of `C17`/`C22`/`R32`/`L2` (independent of overall board size)
  would resolve that residual at the *current* board size. That is a
  distinct, unanswered question.
- **Routing/DRC feasibility of any modelled position was not checked.**
  This tool and this model both measure pad-to-pad geometry only; whether
  the components could actually be placed at the modelled positions without
  breaking other constraints (thermal, mechanical, other nets) is out of
  scope here, exactly as it is out of scope for `scripts/measure_cross_
  domain_creepage.py` itself (see its own module docstring).
- **The discrepancy between this document's 68/75 inter/total group counts
  and the task brief's stated 50/57** was not chased down to a specific
  intervening commit; it is reported, not resolved, per the pinned-commit
  discipline stated above.
