# Pan-load model correction — `PANLOAD_TRANSFORMER` K/L2, and what changes downstream

<!-- provenance: commit=f9bb27a173ad4f84a2b6b3cd617ef91492224559 dirty=true (this pass's own edits) -->

**Date:** 2026-07-27
**Scope:** `simulation/models/pan_load.sub` (owned by this pass), read-only
runs of `simulation/harness/run_zvs_sweep.py` and
`run_tank_coil_sweep.py` (owned by another agent, **not modified**), plus a
supplementary standalone deck built to answer a question those two harnesses
cannot currently answer without a change outside this pass's ownership
boundary (explained in §3).
**Reads first:** `docs/evidence/2026-07-27-coil-pan-coupling-resolution.md`
(the derivation this correction implements), `docs/hardware/
TANK_COIL_SPECIFICATION.md` (the Q=143 / "1800W unreachable" findings this
doc re-examines).

---

## 0. Falsifier, stated before any simulation was re-run

**Falsifier:** *"The corrected model brings the implied tank Q into the
realistic ~10-20 range."*

**Result: does not cleanly fire, and the reason why is itself the finding.**
Whether it fires depends on which of two Q formulas is used, and the
difference between them is caused directly by the correction:

- Computed the physically correct way (`Q = ω·L_apparent / R_eff`, using the
  corrected model's own reduced apparent inductance): Q lands at **3.5-4.9**
  across the L values tested — *below* the realistic 10-20 band, not inside
  it.
- Computed the way `TANK_COIL_SPECIFICATION.md`'s own Q=143 figure was
  computed (`Q = ω·L1 / R_eff`, using the **uncoupled** coil inductance,
  valid only when coupling barely reduces L — true for the broken model,
  no longer true for the corrected one): Q lands at **8.7-12.7** — mostly
  *inside* the 10-20 band for the smaller L values.

Both are reported in §2 rather than picking whichever looks better. The
gap between them (a factor of ~2.6-3x) exists *because* the correction
does exactly what it was supposed to do — pull apparent inductance down
from ~99.99% of L1 to ~39-40% of L1 — which breaks the old formula's
implicit assumption. Reporting only the naive number would hide that; both
are shown.

---

## 1. Chosen point and arithmetic (full derivation lives in the resolution doc; summarized here for the parameters actually written into the file)

Full derivation: `docs/evidence/2026-07-27-coil-pan-coupling-resolution.md`
§2.2-2.5. Summary, holding `pan_load.sub`'s own pre-existing (uncited)
`L1=80u` and `RPAN=10` fixed and solving the two literature-derived
constraints — Infineon AN235020's measured loaded/unloaded ratio (0.40) and
its √f-extrapolated `R_eff` (≈2.2 Ω) — simultaneously for `K` and `L2`:

```
Ratio eq:  K^2 x^2 / (RPAN^2 + x^2) = 0.60         [x = omega*L2, omega = 2*pi*35000]
Rref  eq:  K^2 * L1 * omega * x * RPAN / (RPAN^2+x^2) = 2.2

=> x = (0.60 * L1 * omega) / 2.2 = (0.60 * 80e-6 * 219911) / 2.2 = 47.98 Ohm
=> L2 = x / omega = 47.98 / 219911 = 218.2 uH
=> K^2 = 0.60 * (RPAN^2 + x^2) / x^2 = 0.60 * (100 + 2302) / 2302 = 0.6261
=> K  = 0.791
```

Written into the file (rounded): **K = 0.79, L2 = 218 µH**, `L1 = 80u` and
`RPAN = 10` unchanged.

**Underdetermination, stated plainly (this is not resolved, and the file
header says so):** three unknowns (`K`, `L2`, `RPAN`), two literature
equations. Holding `RPAN` at a different — equally uncited — value produces
a *different* `(K, L2)` pair that satisfies the same two constraints
equally well. This is one point in that family, chosen because it holds the
file's own two pre-existing defaults fixed rather than introducing a third
new assumption. It is **derived from a measurement at a different frequency
band (90-150kHz) on an unstated-diameter stockpot**, not measured for this
coil or this pan. `calibrated: false` is unchanged — this moves the model
from *provably wrong* to *plausibly right*, nothing more.

The header points at `docs/evidence/2026-07-27-coil-pan-coupling-
resolution.md` §4 (the bench spec) as what supersedes these numbers,
including its requirement of three frequency points (25/35/45 kHz) to
separate `L2` from `RPAN` — a single-frequency measurement cannot do this
(resolution doc §2.5).

---

## 2. Implied Q, before and after

Computed at the same grid TANK_COIL_SPECIFICATION.md swept
(`ratio = f_sw/f_res = 1.02`, cast-iron-preset-equivalent operating points,
`L1 ∈ {70,90,110,130,150} µH`), using **live re-runs**, not the old doc's
numbers:

| L (µH) | Before: P_pan (W) | Before: I_tank (A) | Before: R_eff (Ω) | Before: Q (ωL1/R) | After: P_pan (W) | After: I_tank (A) | After: R_eff (Ω) | After: Q (ωL_app/R, rigorous) | After: Q (ωL1/R, naive/inherited) | After: L_apparent/L1 |
|---|---|---|---|---|---|---|---|---|---|---|
| 70  | 1305.0 | 109.48 | 0.1089 | 143.12 | 10238.9 | 72.06 | 1.9717 | **4.91** | 12.71 | 0.386 |
| 90  | 1259.7 | 107.62 | 0.1088 | 162.44 | 8260.7  | 57.22 | 2.5229 | **4.36** | 11.22 | 0.389 |
| 110 | 1217.5 | 105.84 | 0.1087 | 179.70 | 6933.3  | 47.53 | 3.0688 | **3.98** | 10.16 | 0.392 |
| 130 | 1180.8 | 104.25 | 0.1086 | 195.44 | 5981.4  | 40.71 | 3.6093 | **3.69** | 9.35  | 0.395 |
| 150 | 1147.7 | 102.80 | 0.1086 | 210.02 | 5265.9  | 35.65 | 4.1441 | **3.47** | 8.72  | 0.398 |

Sanity check on the arithmetic: `L_apparent/L1` at every point lands within
1% of the 0.40 target ratio the correction was solved to hit — the
correction is internally consistent, evaluated at its own operating points
(the small drift from exactly 0.40 is because `x = ωL2` depends on the
*actual* operating frequency, which itself shifts once `L_apparent`
changes — see §4).

**Before: Q=143-210, rising with L** (matches `TANK_COIL_SPECIFICATION.md`'s
143 figure at L=70µH to within rounding — reproduced live, not copied).
**After: Q=3.5-4.9 (rigorous) or 8.7-12.7 (naive), falling with L either
way.** The rigorous number overshoots *past* realistic on the low side; the
naive number (computed the same way the original doc computed 143) lands
close to realistic for the smaller L values. Both are a >10x improvement
over the pre-correction Q regardless of which is used — the direction of
the fix is right; the magnitude is genuinely ambiguous pending the bench
measurement, and K≈0.79 being outside every literature range found (per
the resolution doc) is one plausible explanation for the rigorous number's
overshoot.

---

## 3. Why the two official harnesses show NO CHANGE at all — verified, not assumed

**Both `run_zvs_sweep.py` and `run_tank_coil_sweep.py` were re-run,
unmodified, before and after the `pan_load.sub` edit. Every result is
byte-identical.** This was verified by diffing the parsed `results` arrays
of both runs in Python (`==` on the full list of dicts), not eyeballed.

This is not because the correction is wrong or the harnesses are somehow
already correct — it is because **neither harness's numeric output can be
reached by editing `pan_load.sub` at all**, for three independent, redundant
reasons, each confirmed by reading the actual code/netlist (not inferred):

1. `zvs_margin_sweep.cir`'s `X_PAN` instantiation line explicitly overrides
   **all five** `PANLOAD_TRANSFORMER` parameters:
   `X_PAN tank_mid2 0 PANLOAD_TRANSFORMER L1={PAN_L1} L2={PAN_L2} K={PAN_K}
   RPAN={PAN_RPAN} RCOIL={PAN_RCOIL}`. A `.subckt` line's own defaults are
   only used for parameters *omitted* at instantiation — none are omitted
   here.
2. `PAN_L2` is a `.cir`-level `.param PAN_L2 = 1u` statement, fixed in the
   committed netlist. Neither `run_zvs_sweep.py` nor
   `run_tank_coil_sweep.py` ever overrides `PAN_L2` — grep confirms `PAN_L2`
   appears nowhere in either script's `overrides` dict.
3. `run_zvs_sweep.py`'s `PAN_PRESETS` (K/RPAN per material) are literal
   Python constants (lines 121-127) — copied from, not read from,
   `pan_load.sub`. Changing `pan_load.sub`'s `PANLOAD_CASTIRON`/
   `PANLOAD_STAINLESS` preset subcircuits (which this pass did **not**
   touch — see the file header) would *also* not reach these harnesses,
   since they never instantiate those preset subcircuits either — only
   `PANLOAD_TRANSFORMER` directly, with every parameter pinned as above.

Per this task's ownership boundary (**must not modify `simulation/
harness/*`**), this gap cannot be closed from this pass. It is flagged
here as an actionable finding for whoever owns that directory: **exposing
`PAN_L2` as a sweep/override parameter (or reading `PAN_K`/`PAN_RPAN` from
`pan_load.sub` itself instead of duplicating them as Python constants) is
required before this correction — or any future one — can ever reach the
two evidence artifacts these harnesses produce.**

To still determine what the corrected model *implies*, §4 uses a
**supplementary, non-harness deck**: `zvs_margin_sweep.cir`'s content was
copied (never modified in place) to a scratch location outside
`simulation/harness/`, its `.include` paths rewritten to absolute paths
(the only change), and it was run with `PAN_L2`/`PAN_K`/`PAN_RPAN`
overridden to the corrected values — something only possible because that
script lives outside the directory this task must not modify. Before any
override was applied, the copy was run at the exact committed baseline
(K=0.5, RPAN=8, L1=80u, L2=1u, F_SW=35k) and its outputs were diffed against
the official `zvs_sweep_BEFORE.json`'s `(cast_iron, 35000Hz)` grid point:
**exact match** (`vce_hs_last=-7.517233`, `i_tank_rms_last=67.5092`,
identical to 6 significant figures) — the copy is topologically faithful,
not a reimplementation that could have silently diverged.

---

## 4. Dependent-simulation results: before vs. after, and which prior conclusions survive

| Simulation | Metric | Before (re-run 2026-07-27) | After (re-run 2026-07-27, official harness) | Verdict |
|---|---|---|---|---|
| `run_zvs_sweep.py` (official) | Worst ZVS margin, 36-point grid | 101.8% (zvs_lost) @ aluminum, 30kHz | **Byte-identical**: 101.8% @ aluminum, 30kHz | **Unaffected — see §3 for why.** Not confirmed, not falsified; untestable via this harness without a change outside this pass's scope. |
| `run_zvs_sweep.py` (official) | ZVS transition | Collapses between 32-33kHz, all 4 presets | **Byte-identical** | Same as above. |
| `run_tank_coil_sweep.py` (official) | P at ratio=1.02, L=70-150µH, cast_iron | 1305/1260/1217/1181/1148 W | **Byte-identical**: 1305/1260/1217/1181/1148 W | Same as above. |
| Supplementary deck (non-harness, §3) | Resonance at L=70µH | f_res (naive, uncoupled) = 34.7kHz | f_res (corrected, coupled) = **55.9kHz** (+61%) | **New finding, not in either "before" set** — see below. |
| Supplementary deck | P_pan at ZVS-held optimum (ratio≈1.02 above *corrected* resonance), L=70-150µH | n/a (this operating point didn't exist under the old model's resonance assumption) | **5266-10239 W** across all 5 L values | **"1800W is unreachable at every L tested" does NOT survive — see below.** |
| Supplementary deck | ZVS-vs-ratio qualitative rule | "ZVS holds for f_sw ≥ ~1.02×f_res" | Still holds directionally: at L=70µH, ratio=1.00 (exactly at corrected resonance) gives margin=56.8% (zvs_lost); ratio=1.02 gives margin=0.58% (zvs_held) | **Survives, but anchored to a ~60% higher absolute frequency than previously assumed.** |
| Gates: `make netlist` | 76 assertions | 76 PASSED (baseline, before edit) | 76 PASSED, 0 FAILED (after edit) | Unaffected (expected — pan model isn't part of the netlist assertions). |
| Gates: `check_domain_partition`, `capacity_budget_gate`, `mpn_fabrication_gate`, `check_derived_doc_drift`, `check_vacuous_gates` | exit code | All 0 (before) | All 0 (after) | Unaffected, confirmed by direct re-run, not assumed. |

### "1800 W is unreachable at every L tested" — **VOID, not confirmed, was an artefact**

`TANK_COIL_SPECIFICATION.md`'s own falsifier ("this recommendation fails if
the pan model's coupling is not representative... only the ZVS boundary
survives") **fires, more strongly than that document itself concluded.**
Not only is the power axis untrustworthy under the broken model — under the
corrected model, evaluated at the operating point the corrected model's own
(much higher) resonance implies, **every L value tested delivers 3-8x more
than 1800W at the same ZVS-holding ratio**, not less. The prior "unreachable
at every L" conclusion was a direct consequence of the pan model absorbing
~10x too little power (§2's Q=143-210), which the correction addresses
directly. This flips the coil specification's blocked status: the actual
open question is no longer "can any L reach 1800W" but **"which L, ratio,
and frequency deliver *exactly* 1800W without exceeding the 50.1A OCP-01
trip"** (tank current at the tested ZVS-held points still ranges 35.7-72.1A
— several points already exceed 50.1A, so this is not free of its own new
constraint, just a different one than "unreachable").

**This is reported as a supplementary-deck finding, not an official-harness
one** (§3) — it should be treated as directionally strong (the topology is
verified faithful, the arithmetic is shown, the shift is consistent across
all 5 L values at ~59-61%) but not as a replacement for
`TANK_COIL_SPECIFICATION.md`'s own committed evidence chain, which requires
the harness-ownership gap in §3 to be closed first.

### "ZVS holds for f_sw ≥ ~1.02×f_res, recommend ≥1.05" — survives, but the frequency it points at moves

The ratio-based rule of thumb held up under the corrected model at every L
tested (§4 table). What changes is *what f_res means*: under the broken
model f_res was computed from the near-unloaded L1 (coupling reduced it by
<0.01%); under the corrected model f_res must be computed from the
coupled/loaded apparent inductance (down 60-61%), which is a **frequency-
dependent, self-referential quantity** (§1's ratio depends on `ω`, which is
what you're solving for) — not a single fixed number the way the old model
made it look. Any future coil spec needs to solve for this self-consistent
point (iteration shown in the supplementary sweep driver script, not
hand-waved) rather than reuse the old formula.

### Tank current vs. OCP-01 (50.1A trip) — reframed, not resolved

Previously: "every ZVS-holding point drew more than 50.1A" (109.5A at best).
Now: tank current at the ZVS-held optimum ranges **35.7A (L=150µH) to
72.1A (L=70µH)** — some points now clear OCP-01, some don't, and the
points that clear it (L=130-150µH) also deliver 5-6kW at that exact
frequency, i.e., far more than the 1800W target, meaning the real design
question is where in the now-much-larger achievable-power envelope the
1800W/50A operating point actually sits — not addressed by this pass, and
explicitly out of scope (would require a proper 2D ratio×L search under the
corrected model, which the harness-ownership gap in §3 also blocks from
being run as an official, evidence-tracked sweep).

---

## 5. Determinism

- **Official harnesses:** `run_zvs_sweep.py`'s own determinism check (3
  runs each of the baseline and worst-margin decks) passed
  `measurements_identical=True` both before and after the edit — see
  `docs/evidence/2026-07-26-zvs-margin-sweep.json` (before, pre-existing;
  re-run live this pass and confirmed byte-identical to this pre-existing
  file, not merely re-cited) vs.
  `docs/evidence/2026-07-27-zvs-margin-sweep-post-pan-correction.json`
  (after, this pass). `run_tank_coil_sweep.py` does not run its own
  determinism check (inherited from `run_zvs_sweep.py`'s scope
  limitation, unchanged by this pass); its 5/5 points converged both times,
  and the two full result sets are byte-identical (§3) — including an
  exact match against the pre-existing `docs/evidence/2026-07-26-tank-coil-
  L-sweep.json` for the overlapping grid points — which is itself a
  determinism-adjacent confirmation.
- **Supplementary deck (§3/§4):** the L=70µH, corrected-params, ratio≈1.02
  point was run 3 times. `stdout_byte_identical=False` (same
  adaptive-timestep diagnostic-line noise `run_zvs_sweep.py` already
  documented for this resonant topology), `measurements_identical=True`.
  See `docs/evidence/2026-07-27-pan-model-correction-supplementary-sweep.json`
  `determinism_check` field.

---

## 6. Verification against the hard gates

Re-run directly (not assumed) after the `pan_load.sub` edit:

| Check | Before | After |
|---|---|---|
| `make netlist` (76 assertions) | 76 PASSED, 0 FAILED | 76 PASSED, 0 FAILED |
| `scripts/check_domain_partition.py` | exit 0 | exit 0 |
| `scripts/capacity_budget_gate.py` | exit 0 | exit 0 |
| `scripts/mpn_fabrication_gate.py` | exit 0 | exit 0 |
| `scripts/check_derived_doc_drift.py` | exit 0 | exit 0 |
| `scripts/check_vacuous_gates.py` | exit 0 | exit 0 |

None of these gates inspect `simulation/models/pan_load.sub` or its
dependent harnesses, so this is an expected-unaffected result, confirmed
rather than assumed.

---

## 7. UNVERIFIED

- Whether `K≈0.79` is physically plausible for this project's actual
  flat-coil/flat-pan geometry at a 3mm air gap — carried over from the
  resolution doc, not re-litigated here. The rigorous-Q overshoot in §2
  (3.5-4.9, below the realistic 10-20 band) is *consistent with* K being
  set too high, but does not prove it — L2/RPAN could equally be the
  off elements in this three-unknown, two-equation system.
- Whether the supplementary deck's ~59-61% resonance-shift finding and
  "1800W now trivially exceeded" finding would survive a proper, harness-
  official re-sweep once `PAN_L2` is exposed as an override — the
  supplementary deck is topologically verified faithful (§3) but is not
  the same evidence-tracked artifact chain as the two official harnesses.
- Which exact `(L, ratio, f_sw)` combination delivers precisely 1800W
  while clearing the 50.1A OCP-01 trip under the corrected model — not
  searched; would need a dedicated 2D sweep, blocked on the same
  harness-ownership gap as everything else in §3-4.
- Whether the `PANLOAD_SIMPLE`/`PANLOAD_VARIABLE`/preset subcircuits
  (`PANLOAD_CASTIRON`, `PANLOAD_STAINLESS`) — left uncorrected, per this
  pass's scope (`PANLOAD_TRANSFORMER` only) — are used by any simulation
  not surveyed here. Grep of `simulation/` found none; not exhaustively
  proven absent from documentation-only references.

---

## Bottom line for the caller

- **Chosen point:** `K=0.79`, `L2=218µH`, holding `L1=80µH` and `RPAN=10Ω`
  (both pre-existing, still-uncited defaults) fixed — full arithmetic in
  §1, underdetermined family explicitly flagged in the file header and
  here.
- **Falsifier ("Q lands in realistic 10-20 range") does not cleanly fire**:
  Q after correction is 3.5-4.9 computed rigorously (below the band) or
  8.7-12.7 computed the way the original 143 figure was computed (mostly
  inside the band) — both are reported; neither is picked to look better.
  Either way, Q improves by >10x from the broken model's 143-210.
- **Both official harnesses (`run_zvs_sweep.py`, `run_tank_coil_sweep.py`)
  produce byte-identical output before and after this correction** —
  verified by direct diff, not assumed — because they hardcode every
  `PANLOAD_TRANSFORMER` parameter independent of `pan_load.sub`'s own
  defaults (§3). This correction cannot reach either official evidence
  artifact without a change to `simulation/harness/*`, which this task's
  ownership boundary forbids.
- **A supplementary, topology-verified-faithful standalone deck** (built
  outside `simulation/harness/`, never modifying it) shows the corrected
  model implies a ~60% higher loaded resonant frequency and 3-8x MORE
  power than 1800W at the ZVS-holding optimum for every L tested —
  **"1800W is unreachable at every L tested" does not survive; it was an
  artefact of the pan model under-absorbing power, exactly as
  `TANK_COIL_SPECIFICATION.md`'s own stated (and now-triggered) falsifier
  anticipated.** This is reported as directionally strong supplementary
  evidence, not a replacement for an official, harness-tracked re-sweep.
- **`calibrated: false` preserved everywhere**, including the new
  supplementary evidence JSON. All five required gates and the 76-assertion
  netlist build remain green, confirmed by direct re-run before and after.
