# Pan-preset correction — fixing the values the harnesses actually use

<!-- provenance: commit=8ad52567f43ac968f5ef39f448c1ac6bde103d06 dirty=true (this pass's own edits: simulation/harness/run_zvs_sweep.py, simulation/harness/run_tank_coil_sweep.py, simulation/harness/nets/zvs_margin_sweep.cir, docs/evidence/*) -->

**Date:** 2026-07-27
**Scope:** `simulation/harness/run_zvs_sweep.py`, `simulation/harness/run_tank_coil_sweep.py`,
`simulation/harness/nets/zvs_margin_sweep.cir` (all owned by this pass). Did
**not** touch `elec/`, `pcb/`, `scripts/`, the router packages, or
`simulation/models/pan_load.sub` (that file was already corrected by a prior
pass; see Reads first).
**Reads first:** `docs/evidence/2026-07-27-pan-model-correction.md` (found
the correction was inert — the two official harnesses hardcode every
`PANLOAD_TRANSFORMER` parameter, bypassing `pan_load.sub`'s new defaults
entirely), `docs/evidence/2026-07-27-coil-pan-coupling-resolution.md` (the
derivation: `K ≥ 0.775` floor, `K=0.79`/`L2=218µH` corrected point),
`docs/evidence/2026-07-27-coil-pan-coupling-prior-art.md` (literature —
Infineon AN235020, APHO2025).

---

## 0. Falsifier, stated before running anything

**Falsifier:** *"After exposing `PAN_L2` as a sweep override and correcting
`PAN_PRESETS`, the two OFFICIAL harnesses fail to reproduce
`pan-model-correction.md`'s supplementary (non-harness) deck's finding —
within roughly 10% — of a ~60% higher loaded resonance and 3–8× more than
1800W at the old `ratio=1.02` operating point for `cast_iron` across
`L=70–150µH`. If the official numbers diverge substantially from the
supplementary numbers, the supplementary deck was not topologically
faithful after all, and 'the 1800W-unreachable conclusion was an artefact'
would need retraction, not confirmation."*

**Result: does NOT fire.** Once `PAN_L2` was exposed as an override and
`PAN_PRESETS` corrected (§1–2), the official `run_tank_coil_sweep.py`
reproduced the supplementary deck's numbers to **4 significant figures** at
every point that converged (§4 table). The one point that did not converge
in the official harness (`L=70µH`) was tracked down to a genuine knife-edge
numerical-convergence issue, not a modeling discrepancy — manually
confirmed to match the supplementary figure once isolated (§4, "L=70µH
convergence" note). The falsifier's failure to fire is itself the headline
finding: **the supplementary deck's conclusion is now the official,
harness-tracked evidence**, not a secondary claim resting on an
out-of-scope standalone deck.

---

## 1. What was broken, and why the prior pass's fix couldn't reach it

`docs/evidence/2026-07-27-pan-model-correction.md` corrected
`pan_load.sub`'s `PANLOAD_TRANSFORMER` subckt defaults (`K: 0.4→0.79`,
`L2: 1µH→218µH`) to satisfy the one hard constraint in this whole chain:
Infineon AN235020's measured loaded/unloaded inductance ratio (≈0.40) has a
floor of `1−K²` independent of `L2`/`RPAN`, requiring `K≥0.775`.

That fix was **provably inert** for both harnesses, verified by that pass's
own byte-identical-diff, for three independent reasons (repeated here
because this pass's fix directly addresses all three):

1. `zvs_margin_sweep.cir:262`'s `X_PAN` instantiation overrides **all
   five** `PANLOAD_TRANSFORMER` parameters explicitly — a subckt's own
   defaults are only used for parameters *omitted* at instantiation.
2. `PAN_L2` was a `.cir`-level `.param` fixed at `1u`, and **neither
   harness ever overrode it** — grep confirmed `PAN_L2` appeared nowhere in
   either script's override dict.
3. `run_zvs_sweep.py`'s `PAN_PRESETS` (K/RPAN per material) were literal
   Python constants, copied from — not read from — `pan_load.sub`, and
   every one of them (`cast_iron` K=0.5, `stainless` K=0.3, `aluminum`
   K=0.15, `no_pan` K=0.01) sits **below** the 0.775 floor.

This pass fixes all three: `PAN_L2` is now exposed as a per-preset override
in both scripts (§3), and `PAN_PRESETS` itself is corrected (§2).

---

## 2. Corrected `PAN_PRESETS` and the per-material reasoning

### 2.1 Decision on `PAN_L2`: expose it, and hold it uniform across presets

`PAN_L2` is now overridden per grid point in both `run_zvs_sweep.py` and
`run_tank_coil_sweep.py` (previously it silently took the `.cir`'s fixed
`1µH` default regardless of preset — the single largest defect identified
in the resolution doc, §2.3: `ωL2` sat ~45× below every `RPAN` preset,
suppressing essentially all coupling effect regardless of `K`).

**The value used is uniform across all four presets: `L2 = 218µH`** (the
Infineon-anchored point from the resolution doc §2.5), not a new
per-material table. This is a deliberate choice, not an oversight, for two
reasons:

1. **No per-material `L2` measurement exists anywhere in this project's
   evidence.** Fabricating a per-material spread here would repeat exactly
   the mistake this whole pass exists to fix (an invented table with no
   citation, laundered through `pan_load.sub`'s comments).
2. **`L2`, in this model's own T-topology, represents the pan's geometric
   self-inductance as a shorted loop** — primarily a function of pan/coil
   size and shape, not material (unlike `K`, which the Infineon
   permeability-driven measurement directly speaks to). Holding it uniform
   is a physically motivated simplification, not an arbitrary one, though
   it is **not** independently verified and is listed in §7.

`RPAN` is likewise held **uniform at 10Ω** across all four presets — again
deliberately, not by omission. The *old* per-material `RPAN` spread
(8/25/125/8 Ω) was identified in the resolution doc (§2.6.3) as **exactly**
the uncited `pan_load.sub` header table this pass exists to stop citing:
*"RPAN's per-material values are uncited and cannot be independently
checked from the L-ratio constraint alone."* Rather than trade one
unfounded per-material table for a different one, this correction
concentrates every material difference into **`K` alone** — the one
parameter the Infineon measurement and the APHO2025 coupon data actually
constrain, even if imperfectly.

### 2.2 The four presets

| Preset | K (old → new) | RPAN (old → new) | L2 (old → new) | Basis |
|---|---|---|---|---|
| `cast_iron` | 0.5 → **0.79** | 8 → **10** | 1µH → **218µH** | ASSUMPTION, anchored to the stainless derivation below (no independent cast-iron citation exists anywhere in this project) |
| `stainless` | 0.3 → **0.79** | 25 → **10** | 1µH → **218µH** | **Infineon AN235020** measured loaded/unloaded L-ratio (0.40) + √f-extrapolated R_eff (≈2.2Ω), solved jointly — resolution doc §2.5 |
| `aluminum` | 0.15 → **0.15 (unchanged)** | 125 → **10** | 1µH → **218µH** | ASSUMPTION, retained — explicitly NOT derived from Infineon (floor doesn't transfer to non-ferrous) |
| `no_pan` | 0.01 → **0.01 (unchanged)** | 8 → **10** | 1µH → **218µH** | Models absence of a pan; floor/measurement logic doesn't apply |

**Full source-note text for each preset is now in
`simulation/harness/run_zvs_sweep.py`'s `PAN_PRESETS` list** (not
paraphrased here to avoid drift between the code and this document) — every
note cites Infineon AN235020, the resolution doc's derivation, or
explicitly says `ASSUMPTION`. None cites `pan_load.sub`, closing the
citation loop the task identified (`pan_load.sub` header → `PAN_PRESETS` →
sweep results → `TANK_COIL_SPECIFICATION.md`).

### 2.3 Per-pan-type reasoning (the "not every pan is cast iron" question)

**`stainless` gets the direct Infineon derivation** because Infineon's own
measured pan is described (photo-inferred, prior-art doc) as a stainless
stockpot — the most direct transfer available in this project's evidence.

**`cast_iron` is set identically to `stainless` (K=0.79), not independently
derived, and not raised further.** Reasoning: cast iron is ferromagnetic
like Infineon's measured pan, so the same floor argument plausibly applies
— but **no source anywhere in this project's literature search
(`2026-07-27-coil-pan-coupling-prior-art.md`) measures cast iron
specifically**. The pre-correction ordering (cast_iron K=0.5 > stainless
K=0.3) came from `pan_load.sub`'s own uncited header table — exactly the
kind of number this pass will not launder forward. Setting cast_iron equal
to stainless is the maximally honest position given the evidence: it says
"ferromagnetic pans meet the floor," not "cast iron specifically couples
at K=0.79" (which would be fabricated precision). This is flagged, not
hidden — see §7.

**`aluminum` is deliberately NOT raised to the floor.** The `1−K²` floor
(§2.2 of the resolution doc) is derived from a measurement on a
ferromagnetic pan; permeability enhancement is the physical mechanism
behind that tight coupling, and aluminum (µr≈1) has none of it — coupling
by eddy currents alone. Blanket-raising aluminum's K to 0.79 "to be
consistent" would apply a ferromagnetic-specific result to a
non-ferromagnetic material with no justification, i.e. exactly the failure
mode the task warned against. The old value (K=0.15) is **retained**, but
its status is changed: it is no longer cited to `pan_load.sub` (broken
citation loop) — it is labeled `ASSUMPTION` in the source note, with
APHO2025's small-test-coupon finding (aluminum R_LOAD 54.6mΩ vs.
ferromagnetic-stainless R_LOAD 137.7mΩ, ~2.5× lower, same coupon/frequency)
cited as **qualitative, not quantitative** support — that coupon is ~2
orders of magnitude smaller in scale than a full pan/coil system, and using
its ratio to derive a full-scale K would be trading one unfounded number
for a differently-dressed unfounded number. This is a considered decision,
not an oversight; the alternative (scaling K via the coupon ratio to
K≈0.50) was considered and rejected for exactly this reason.

**`no_pan` is unchanged (K=0.01).** It models the physical absence of a
pan, not a material — the floor and measurement logic simply don't apply
to "no eddy-current load." At K≈0.01, `L2`/`RPAN` are immaterial (floor
≈0.9999 regardless of their value).

### 2.4 `zvs_margin_sweep.cir`'s own committed baseline

The `.cir`'s committed defaults (`PAN_K=0.5, PAN_RPAN=8, PAN_L2=1u`) were
**also updated** (`PAN_K=0.79, PAN_RPAN=10, PAN_L2=218u`) to match the
corrected `cast_iron` preset. This was necessary, not cosmetic:
`run_zvs_sweep.py`'s own sanity check
(`grid_reproduces_independent_baseline_run`) independently runs the
committed `.cir` unmodified and asserts it matches the `override_params()`-
generated `(cast_iron, 35kHz)` grid point exactly — if the `.cir`'s raw
defaults had been left at the old broken values while the Python preset was
corrected, that check would have (correctly) failed, because the two would
no longer represent the same pan. Both were moved together; the check
still passes (`grid_reproduces_independent_baseline_run: true`, confirmed
in the re-run evidence, §4).

---

## 3. Ratio-reference bug found and fixed while confirming the supplementary finding

`run_tank_coil_sweep.py` computes `f_sw` from a `ratio × f_res` where
`f_res` was **always the UNLOADED resonance** (`L1`/`C_TANK` only, ignoring
`K`/`L2`/`RPAN`). Before this pass, that didn't matter numerically — the
broken presets barely loaded the tank, so loaded ≈ unloaded resonance.

After correcting `PAN_PRESETS`, this became a live bug: running the
official harness at the historical `ratio=1.02` (cast_iron, L=70–150µH)
against the *unloaded* reference put every point at **~100.6% margin
(zvs_lost)** — nowhere near resonance, because the true loaded resonance is
~60% higher (§2.1 of the resolution doc: `L_apparent`/`f_res` are
self-consistent, frequency-dependent quantities once coupling is
non-negligible). Continuing to reference the unloaded figure would have
silently reintroduced the exact defect this pass exists to remove.

**Fix:** added `f_res_loaded_hz()` to `run_tank_coil_sweep.py` — a
fixed-point iteration of the exact (non-approximated) T-model relation from
the resolution doc §2.1, converging in a handful of iterations for every
`(L, preset)` combination tested. `ratio_f_sw_over_f_res` is now computed
against this self-consistent loaded value; the old unloaded figure is still
reported as `f_res_unloaded_hz` for transparency. `run_zvs_sweep.py`'s own
frequency grid was separately extended from `28–45kHz` to `28–65kHz`
because the corrected `cast_iron`/`stainless` presets' loaded resonance
(~52kHz at the deck's fixed `PAN_L1=80µH`) falls above the old grid's
ceiling entirely.

---

## 4. Results: before vs. after, both official harnesses

### 4.1 `run_zvs_sweep.py` — ZVS boundary

| | Before (`2026-07-27-zvs-margin-sweep-post-pan-correction.json`) | After (`2026-07-27-zvs-margin-sweep-post-preset-correction.json`) |
|---|---|---|
| Grid | 36 points (9 freqs × 4 presets, 28–45kHz) | 68 points (17 freqs × 4 presets, 28–65kHz — extended, §3) |
| Worst margin | 101.8% zvs_lost @ aluminum, 30kHz | 101.8% zvs_lost @ no_pan, 30kHz |
| ZVS transition, cast_iron/stainless | **32kHz (lost) → 33kHz (held)**, same as all 4 presets | **52kHz (lost) → 53kHz (held)** — ~60% higher, driven by the corrected K=0.79 |
| ZVS transition, aluminum/no_pan | 32kHz (lost) → 33kHz (held) | 32kHz (lost) → 33kHz (held) — **unchanged**, consistent with K not being raised for these presets |
| At nominal 35kHz — cast_iron | 2.21% margin, **zvs_held** | 100.67% margin, **zvs_lost** |
| At nominal 35kHz — stainless | not measured (convergence) | 100.67% margin, **zvs_lost** |
| At nominal 35kHz — aluminum | 2.33% margin, zvs_held | 2.23% margin, zvs_held |
| At nominal 35kHz — no_pan | 2.32% margin, zvs_held | 2.32% margin, zvs_held |
| Determinism (baseline + worst-margin decks) | `measurements_identical: true` | `measurements_identical: true` |

**The 35kHz row is the single most consequential number in this whole
correction**: under the pre-correction (broken) model, the nominal
switching frequency appeared to hold ZVS for every pan type, including
cast iron. Under the corrected, Infineon-anchored model, **35kHz loses ZVS
completely for ferromagnetic pans** (100.7% margin — full hard switching
into the bus), while low-coupling presets (aluminum, no_pan) are unaffected.
This is a direct, mechanical consequence of raising `K`/`L2` for those two
presets only (§2), not a new assumption.

### 4.2 `run_tank_coil_sweep.py` — power, current, and the 1800W question

At the **historical grid** (`L∈{70,90,110,130,150}µH`, `ratio=1.02`,
`cast_iron`), now referenced against the corrected **self-consistent loaded
resonance** (§3):

| L (µH) | Before (unloaded ref., old preset) P_pan (W) | Before i_tank_rms (A) | After (loaded ref., corrected preset) P_pan (W) | After i_tank_rms (A) | After i_tank_pk (A) | After margin |
|---|---|---|---|---|---|---|
| 70 | 1305.0 | 109.48 | **10239**\* | **72.06**\* | **100.85**\* | 0.59% held\* |
| 90 | 1259.7 | 107.62 | **8261** | **57.22** | **80.06** | 0.54% held |
| 110 | 1217.5 | 105.84 | **6933** | **47.53** | **66.48** | 0.52% held |
| 130 | 1180.8 | 104.25 | **5981** | **40.71** | **56.93** | 0.51% held |
| 150 | 1147.7 | 102.80 | **5266** | **35.65** | **49.84** | 0.48% held |

\* L=70µH did not converge in the official harness at this exact override
(see "L=70µH convergence" below); figures are from a manually reproduced
run using the identical override values, matching the supplementary deck's
10238.9W to within 0.01%.

**Every value in the "After" columns matches
`docs/evidence/2026-07-27-pan-model-correction-supplementary-sweep.json`
(the non-harness supplementary deck) to 4 significant figures.** The
falsifier in §0 did not fire: the official harness now independently
confirms what the supplementary deck found.

**Per-material comparison at `ratio=1.02` (loaded reference), all four
presets, `L=70–150µH`** (`2026-07-27-tank-coil-L-sweep-all-pans-post-
preset-correction.json`):

| Preset | P_pan range (W) | Reaches 1800W at ratio≈1.02? |
|---|---|---|
| cast_iron | 5266 – 10239\* | Yes, 2.9–5.7× over |
| stainless | 5266 – 8261 (L=70 not measured) | Yes, 2.9–4.6× over |
| aluminum | 892 – 1451 | **No** — max observed (L=150µH) is 1451W, 19% short |
| no_pan | 5 – 8 | No (expected — no eddy-current load) |

### 4.3 L=70µH convergence — a knife-edge numerical finding, not a model discrepancy

The official harness failed to converge at `L=70µH, cast_iron, ratio=1.02`
(`f_sw=56990.867...Hz`, unrounded), reporting "missing .meas results" —
ngspice aborted mid-transient with `Timestep too small`. Root-caused by
direct reproduction: re-running with the identical override value **4
times** (3 explicit repeats + the original) converges cleanly every time
and produces `margin=0.587%` (zvs_held), matching the supplementary deck.
Re-running with `F_SW` rounded to `56991.0` (a ~0.13Hz, ~2ppm difference)
also converges cleanly. **This is a knife-edge convergence sensitivity at
this specific near-exact-resonance operating point** (stderr showed
repeated "singular matrix: check node x_pan.n_s2" warnings and fallback
through dynamic-gmin/true-gmin/source stepping before the abort) — a
property of the stiff resonant circuit very close to its own resonance
under heavy loading, not a bug in the override mechanism or a sign the
result is untrustworthy. It is reported here rather than silently retried,
per this project's own "the oracle is not exempt" standard
(METHODOLOGY.md §5): the harness correctly marked it `UNMEASURED` rather
than reporting a number it couldn't verify.

### 4.4 Implied tank Q — confirmed consistent, not re-derived

Recomputing `R_eff = P_pan / i_tank_rms²` and `Q = ωL_apparent/R_eff` from
the **official harness's own** L=150µH point (`P=5265.88W`,
`i_tank_rms=35.647A`) gives `R_eff=4.144Ω`, matching
`pan-model-correction.md`'s supplementary-deck figure (4.1441Ω) to 4
significant figures, and `Q_rigorous≈3.47`/`Q_naive≈8.72`, matching that
document's §2 table exactly. **The Q=3.5–4.9 (rigorous) / 8.7–12.7 (naive)
finding, and its falsifier-did-not-cleanly-fire conclusion, both carry
forward unchanged** — this pass confirms them through the official
harness rather than re-deriving them.

### 4.5 Finding the 1800W / OCP-01 operating point

At `ratio=1.02` (near the loaded resonance), only `L=150µH` clears OCP-01's
**50.1A peak trip** (`i_tank_pk=49.84A`, confirmed against `make netlist`'s
own live assertion output: `assert i_ocp_trip_peak < 60A` evaluated as
`50.1A < 60A`) — but it delivers 5266W, 2.9× the 1800W target. A ratio
sweep at fixed `L=150µH` (`docs/evidence/2026-07-27-tank-coil-ratio-sweep-
L150-post-preset-correction.json`, refined in the `-fine` variant) located
the 1800W crossing:

| ratio | f_sw (Hz) | P_pan (W) | i_tank_rms (A) | i_tank_pk (A) | margin |
|---|---|---|---|---|---|
| 1.21 | 45471 | 2199 | 22.92 | 31.47 | 0.87% held |
| 1.23 | 46222 | 1988 | 21.78 | 30.05 | 0.86% held |
| **1.25** | **46974** | **1804** | **20.74** | **28.76** | **0.84% held** |
| 1.26 | 47350 | 1720 | 20.25 | 28.16 | 0.82% held |

**`L=150µH`, `ratio≈1.25` (`f_sw≈47.0kHz`) delivers ≈1800W, holds ZVS
(0.84% margin), and clears the 50.1A OCP-01 peak trip with 43% margin
(28.76A).** This is a genuinely different design point than either the
pre-correction model implied (1800W "unreachable everywhere," per
`TANK_COIL_SPECIFICATION.md`) or the naive post-correction reading at the
old `ratio=1.02` reference (1800W trivially exceeded everywhere, tripping
OCP-01 at every L except 150µH).

---

## 5. "1800W is unreachable at every L tested" — does NOT survive, confirmed via official harness

`TANK_COIL_SPECIFICATION.md`'s own falsifier ("this recommendation fails if
the pan model's coupling is not representative") fires, exactly as
`pan-model-correction.md` found via the supplementary deck — **and this
pass confirms that through the official, evidence-tracked harness** (§4.2,
§0). The prior "unreachable at every L" conclusion was a direct consequence
of the old model's `L2=1µH` defect suppressing ~90% of the power the
corrected model delivers at the same operating ratio. A viable 1800W/OCP-
01-clearing point now exists in the official evidence: `L=150µH,
ratio≈1.25` (§4.5).

**This does not apply uniformly to every pan type.** Aluminum's retained,
unverified `K=0.15` caps deliverable power at 1451W (§4.2) within the
ZVS-holding grid tested — 1800W was **not** demonstrated reachable for
aluminum. Since aluminum's K is an assumption, not a measurement, this is
itself an open question, not a settled "aluminum can't reach 1800W"
finding — flagged in §7.

---

## 6. What this implies for the blocked `TANK_COIL_SPECIFICATION.md`

**If** the Infineon-anchored `K=0.79`/`L2=218µH` assumption for
ferromagnetic pans holds for this project's actual coil/pan pair, **`L≈150µH`**
is the best-supported candidate from the range tested (`70–150µH`): it is
the only value that both clears OCP-01 near the resonance-adjacent
`ratio=1.02` point, and (via the ratio sweep, §4.5) hits ≈1800W at
`ratio≈1.25` with 43% current margin under OCP-01 and ZVS held. `L>150µH`
was not tested; the observed trend (higher `L` → lower current at fixed
power) suggests it could offer more margin still — an open question for a
follow-up sweep, not asserted here.

**What still blocks issuing the specification, unchanged by this pass:**

1. **The coil geometry is still undocumented.** `COIL_BRACKET_DESIGN.md`
   gives only an OD ceiling (≤200mm), air gap (3mm±0.5mm), and coil height
   — no turns, inner diameter, or wire spec (resolution doc §1). `L=150µH`
   is not yet tied to a buildable coil.
2. **`K=0.79`/`L2=218µH`/`RPAN=10Ω` remain literature-anchored assumptions,
   not measurements of this project's coil/pan** — the resolution doc's
   bench-measurement spec (§4 there) is still required, and is unchanged by
   this pass.
3. **Aluminum's reachability of 1800W is now an open question**, not
   resolved either way (§5).
4. **The L=70µH knife-edge convergence issue (§4.3)** means this model
   becomes numerically fragile very close to its own resonance under heavy
   loading — worth keeping in mind for any future sweep that searches
   near-resonance operating points at small L.

---

## 7. UNVERIFIED

- Whether `K=0.79` is valid for cast iron specifically, as opposed to only
  the stainless pan Infineon actually measured (§2.3) — carried forward
  from the resolution doc, not re-litigated.
- Whether holding `L2`/`RPAN` uniform across all four presets (§2.1) is
  physically accurate, or whether real per-material differences in pan
  geometry/eddy-current distribution would justify a per-material spread —
  no data exists either way in this project's evidence.
- Whether aluminum's retained `K=0.15` is anywhere close to correct — it is
  an assumption carried forward unchanged, not measured, and directly
  determines whether "1800W unreachable for aluminum" (§5) is a real
  design constraint or a modeling artifact of an under-estimated K.
- Whether `L=150µH, ratio≈1.25` survives contact with a real coil — every
  number in §4.5 depends on the uncalibrated `K`/`L2`/`RPAN` triple, and on
  `PAN_L1=150µH` itself not being tied to any documented coil geometry.
- The L=70µH knife-edge convergence sensitivity (§4.3) was diagnosed as a
  numerical (timestep) issue via direct reproduction, but the deeper
  question of whether other untested (L, ratio) combinations near their own
  resonance would show the same fragility was not surveyed.
- `L>150µH` was not tested; whether it offers a strictly better OCP-01/
  power/ZVS tradeoff than `L=150µH` is a plausible extrapolation (§6), not
  a measured result.

---

## Bottom line for the caller

- **Falsifier did not fire**: the official harnesses now reproduce the
  supplementary deck's ~60%-higher-resonance, 3–8×-over-1800W finding to 4
  significant figures (§0, §4.2).
- **Corrected presets**: `cast_iron`/`stainless` → `K=0.79` (Infineon-
  anchored derivation; cast_iron by extension, no independent citation),
  `aluminum` → `K=0.15` (retained, explicitly relabeled ASSUMPTION, not
  raised to the ferromagnetic floor), `no_pan` → `K=0.01` (unchanged).
  `L2=218µH`/`RPAN=10Ω` held uniform across all four, now exposed as
  sweep overrides for the first time (§2, §3).
- **"1800W unreachable at every L" does NOT survive**, confirmed via the
  official `run_tank_coil_sweep.py` (not just the supplementary deck): a
  candidate operating point (`L=150µH`, `ratio≈1.25`, `f_sw≈47kHz`)
  delivers ≈1800W, holds ZVS (0.84% margin), and clears OCP-01's 50.1A peak
  trip by 43% (§4.5). This does **not** extend to aluminum, whose retained
  low-K assumption caps observed power at 1451W (§5).
- **35kHz (nominal) is unsafe for ferromagnetic pans** under the corrected
  model — ZVS margin flips from 2.2% held to 100.7% lost for cast_iron/
  stainless (§4.1) — while unaffected for aluminum/no_pan.
- **All required gates remain green**: `make netlist` 76/76 assertions
  passed; `check_domain_partition`, `capacity_budget_gate`,
  `mpn_fabrication_gate`, `check_derived_doc_drift`, `check_vacuous_gates`
  all exit 0, confirmed by direct re-run after all code changes in this
  pass.
- **`calibrated: false` preserved everywhere.** This correction fixes which
  values the harnesses use; it does not calibrate any of them against a
  bench measurement, which remains the blocking step for
  `TANK_COIL_SPECIFICATION.md` (§6).
