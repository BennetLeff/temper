# Tank RMS current reconciliation: inductance-range sweep (20.7 A) vs. bus-capacitor ripple (35.4–40 A)

provenance: commit=fed05e82b45c7612a2f1e636b007511e7deda8c1 dirty=true

<!-- fed05e82 dirty=true (this pass's own uncommitted-at-start work), branch tank-current-reconciliation, forked from docs/methodology-loop-discipline -->

**Date:** 2026-07-28
**Method:** Arithmetic reproduction from each source document's own stated
inputs (hand/script recomputation, cross-checked against the existing
simulated JSON where available), plus direct reading of the SPICE pan-load
model and the harnesses that parameterize it. No new simulation was run —
every number below is either reproduced from an existing evidence artifact,
derived analytically from committed/declared values, or explicitly labeled
`UNVERIFIED`.
**Scope:** read-only. No files under `elec/`, `pcb/`, or `simulation/models/`
or `simulation/harness/` were modified. `docs/evidence/` gained only this
file.

## Falsifier, stated up front

*"One figure is derivable from committed values and the other rests on an
uncited assumption. If both are defensible under different but equally valid
assumptions, the finding is that the design point is under-specified — and
what measurement would settle it."*

**Result: fires, but not in the clean binary form as stated.** Neither figure
is purely "derivable from committed values" — both rest on assumptions, of
different character (§3). The bus-cap doc's **lower** bound (35.4 A) genuinely
is derived from committed hardware values, but it is a **protection-trip
threshold converted to RMS**, not a delivered-power operating current — a
category error independent of any R_eff dispute. Its **upper** bound (40 A) is
an uncited "typical" figure. The sweep's 20.7 A is a real simulation output,
but its own R_eff is shown below to be a **mechanical artifact** of a
pan-coupling-model calibration performed at a different coil inductance
(80 µH) than the one the sweep evaluates (150 µH) — not an independently
validated figure at the design point. **Bottom line: the design point is
under-specified**, exactly as the falsifier's fallback predicts, and §7 states
the measurement that would close it.

---

## 1. Reproducing the sweep's 20.7 A

From `docs/evidence/2026-07-27-inductance-range-sweep.md` §2.1 (L=150 µH,
`cast_iron`, fixed `f_sw`=47 kHz, `f_res,loaded`=37.58 kHz, ratio=1.251):
**i_rms = 20.70 A, i_pk = 28.71 A, P_pan = 1798 W.**

**Resonance check (independent recompute).** `C_tank` = `c_tank1`+`c_tank2`
(both 150 nF, wired in parallel — confirmed by reading `elec/src/modules.ato`:
both `p1` tie to `in`, both `p2` tie to `inductor_conn.p1`) = 300 nF.

- Unloaded: `f = 1/(2π√(150µH·300nF))` = **23.73 kHz** — matches
  `zvs-operating-point.md`'s independently-stated 23.7 kHz exactly.
- Loaded (T-model, `K=0.79`, `L2=218µH`, `RPAN=10Ω`, per `pan_load.sub`):
  solving the self-consistent `f_res_loaded_hz()` fixed point (the same
  function `run_tank_coil_sweep.py` added after the pre-correction bug the
  task cites — see §3) lands within ~3% of the doc's reported 37.58 kHz using
  a first-pass `Leff = L1(1-K²) = 56.4µH → 38.7 kHz` approximation; the exact
  T-model number (37.58 kHz) is the more precise, already-simulated figure and
  is used throughout. **Ratio = 47/37.58 = 1.251** — matches the table
  exactly.

**R_eff back-calculation:** `R_eff = P_pan / i_rms² = 1798 / 20.70² = 4.196 Ω`
(sweep doc rounds to 4.20 Ω — reproduced to 4 sig figs).

**Independent cross-check via the model's own closed-form reflected-impedance
formula** (`pan_load.sub` header, `PANLOAD_TRANSFORMER`):
```
M = K·√(L1·L2) = 0.79·√(150µH·218µH) = 1.428e-4 H
ω = 2π·37,580 = 2.361e5 rad/s
ωM = 33.72 Ω  →  (ωM)² = 1137
R_ref = (ωM)²·RPAN / (RPAN² + (ω·L2)²) = 1137·10 / (10² + 51.47²) = 4.14 Ω
```
**4.14 Ω vs. the simulator's 4.20 Ω** — agrees to within ~1.5% (residual from
rounding `f_res,loaded` and the coil's own small series `RCOIL=0.1Ω`, not
modeled in this hand check). **The sweep's 20.7 A and its implied 4.2 Ω are
correctly reproduced from the stated model and inputs.** Provenance:
*simulated* (ngspice, `docs/evidence/2026-07-27-inductance-range-sweep-fixed-fsw.json`), cross-checked *derived* (closed-form, this document).

---

## 2. Reproducing the bus-cap doc's 35.4–40 A

From `docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`:

- **Trip current, from committed hardware:** CT ratio 1:100, burden 4.99 Ω,
  comparator reference 2.500 V (`CurrentSensing` in `elec/src/modules.ato`).
  Secondary trip current = `2.500V / 4.99Ω = 0.5010 A`. Primary (tank) trip
  current = `0.5010 × 100 = 50.1 A` **peak** (no rectifier is actually wired
  despite the BOM costing one — confirmed by that document's own read of the
  sense path; the comparator sees the raw bipolar waveform, RC corner 319 kHz,
  no averaging). **Reproduced exactly: 50.1 A.** This part genuinely is
  derivable from committed component values alone.
- **RMS-equivalent of that threshold, assuming a pure sinusoid:**
  `50.1 / √2 = 35.42 A` → reproduced as **35.4 A**.
- **"Typical 1.8 kW hob" = 40 A RMS** — traced to its root: **no citation
  given anywhere in that document.** `docs/evidence/2026-07-27-coil-pan-
  coupling-prior-art.md` (§"OCP-01 vs. 1800W") independently confirms this:
  *"that 40 A / 1.12 Ω figure is not itself cited to a source in that
  document — it reads as the document's own estimate."*

Implied `R_eff`: `1800/35.4² = 1.437 Ω` (top of OCP-01 window) down to
`1800/40² = 1.125 Ω` ("typical"). **Reproduced: 1.12–1.44 Ω.**

**The bus-cap doc's use of this band is a category conflation, independent of
the R_eff question**: 35.4 A is not an expected *operating* current at
1800 W — it is the RMS-equivalent of a *hardware trip ceiling*. Treating a
protection threshold as the expected delivered current assumes the design
runs right at the edge of tripping its own overcurrent protection at every
use, which is not established anywhere. The 40 A "typical" figure is a
separate, unrelated, uncited industry generalization. **Both numbers in the
"35.4–40 A" band are real numbers correctly transcribed from their sources —
but the band itself conflates two different kinds of quantity (a threshold
and a guess), neither of which is a modeled or measured *delivered* tank
current at this design's actual R_eff.**

---

## 3. Finding the divergence: R_eff is not independently determined at L=150 µH

This is the key finding this document adds beyond what
`inductance-range-sweep.md` §4 had already found (that document identified
*that* the two R_eff figures disagree and traced the bus-cap figure to an
uncited assumption; this section explains *why the sweep's own 4.2 Ω is not
independent evidence either*).

**`pan_load.sub`'s `K=0.79`/`L2=218µH` pair was solved holding `RPAN=10Ω` and,
critically, `L1=80µH` fixed** (`docs/evidence/2026-07-27-pan-model-
correction.md` §1, arithmetic reproduced here):
```
x = (0.60 · L1 · ω) / 2.2,  L1 = 80e-6, ω = 2π·35,000
 → x = 47.98 Ω → L2 = 218.2 µH
 → K² = 0.60·(RPAN²+x²)/x² → K = 0.791
```
**This calibration target was R_eff ≈ 2.2 Ω, at L1 = 80 µH** — 80 µH being
`run_zvs_sweep.py`/`run_tank_coil_sweep.py`'s own pre-existing harness
default, unrelated to the coil the project is actually trying to build.
`l_tank_assumed = 150 µH` was declared as the design's real assumed
inductance in a **later, separate pass** (`inductance-range-sweep.md`, same
day) that swept `L1` (the harness's `PAN_L1` override — confirmed directly in
`simulation/harness/run_inductance_range_sweep.py:101-104` and
`run_tank_coil_sweep.py:175-178`) while **holding `PAN_K`, `PAN_L2`, `PAN_RPAN`
fixed at their 80 µH-calibrated values across the entire 50–250 µH sweep.**
Nobody re-solved `K`/`L2`/`RPAN` at `L1 = 150 µH`.

**Numerical proof this matters, not just a theoretical concern** — recomputing
`R_eff = P_pan/i_rms²` at every point in the coarse sweep grid (§2.1 of the
inductance-range-sweep doc):

| L (µH) | R_eff (Ω), from sweep | R_eff / L (Ω/µH) | Linear prediction from 2.2Ω@80µH |
|---|---|---|---|
| 70  | 1.957 | 0.02795 | 1.925 |
| 90  | 2.516 | 0.02796 | 2.475 |
| 110 | 3.075 | 0.02796 | 3.025 |
| 130 | 3.636 | 0.02797 | 3.575 |
| **150** | **4.196** | **0.02797** | **4.125** |
| 175 | 4.889 | 0.02794 | 4.813 |
| 200 | 5.591 | 0.02796 | 5.500 |
| 225 | 6.296 | 0.02798 | 6.188 |
| 250 | 6.994 | 0.02798 | 6.875 |

**`R_eff/L` is constant to within 0.2% across the entire 50–250 µH range.**
This is not a coincidence or new physics — it falls directly out of the
model's own formula (`R_ref = (ωM)²·RPAN/(RPAN²+(ωL2)²)`, and `M² = K²·L1·L2`
is linear in `L1` when `K`, `L2` are held fixed, with `ω` only weakly
self-referential through the loaded-resonance solve). **The sweep's headline
"R_eff ≈ 4.2 Ω at L=150 µH, inside the literature's 2.0–4.5 Ω range" is
mechanically ≈1.9× the 2.2 Ω calibration point, because 150 µH is ≈1.9× the
80 µH the calibration was performed at — not because of any independent
confirmation that R_eff should be 4.2 Ω specifically at 150 µH.** It sits at
the *top* of the literature range (2.0–4.5 Ω) for exactly this reason: the
2.0–4.5 Ω band itself brackets a factor of ~2.25× (§ `coil-pan-coupling-prior-art.md`), and the model's own L1-scaling artifact happens to land inside it at
this particular L, without that being independent evidence.

**Frequency detail, already flagged in the prior-art doc but relevant here:**
the literature's own **frequency-corrected** central estimate is narrower —
**R_eff ≈ 2.0–2.2 Ω at ~35 kHz** (Infineon's 90–150 kHz-measured 3.3–4.5 Ω,
√f-extrapolated down to this project's band, converges with IJCRT's
independently-assumed 2 Ω design value). The *uncorrected* 3.3–4.5 Ω applies
at 90–150 kHz, a different frequency band than this project's 35–47 kHz —
using it unadjusted (as the "4.2 Ω sits inside 2.0–4.5 Ω" framing implicitly
does) mixes frequency bands.

---

## 4. Triangulating a third figure — what the frequency-appropriate literature R_eff implies

If `R_eff` is treated the physically standard way — a property of the pan
material, coil-pan gap, and frequency, **not of the tank coil's own turn
count/L1** (i.e., held fixed rather than let it float linearly with whatever
`L1` a sweep happens to test) — and the literature-anchored, frequency-
corrected **R_eff ≈ 2.0–2.2 Ω** (`coil-pan-coupling-prior-art.md`'s own
"recommended planning value," not the sweep's L1-inflated 4.2 Ω) is used at
the 1800 W target:

```
I_rms = √(P/R_eff) = √(1800/2.2) to √(1800/2.0) = 28.6 A to 30.0 A
```

**This is a third number — provenance: derived, not simulated, not measured —
that sits between the two disputed figures**: below the bus-cap doc's
35.4–40 A band, above the sweep's 20.7 A. It is closer to the bus-cap doc's
lower (35.4 A, itself a threshold not an operating figure) bound than to the
sweep's headline, but matches neither.

**This is not offered as "the correct answer."** It depends on the same
unresolved physical question the whole evidence chain keeps surfacing:
whether `R_eff` scales with the coil's self-inductance `L1` (the sweep's
implicit assumption, inherited mechanically from holding `K,L2,RPAN` fixed) or
is closer to an `L1`-independent pan/frequency property (the literature
synthesis's framing). **Neither assumption has been bench-verified**, and both
are "equally valid" in the falsifier's sense — this is the under-specification
the falsifier predicts.

---

## 5. Verdict

**Neither headline figure (20.7 A nor 35.4–40 A) should be taken as the
design's actual expected tank RMS current at 1800 W without further work.**

- The sweep's **20.7 A** is a real, correctly-executed simulation output
  (reproduced above), but its R_eff is an artifact of extrapolating a pan-
  coupling calibration performed at a *different* coil inductance (80 µH) out
  to the design's assumed 150 µH — likely an **underestimate** of the true
  current if R_eff does not scale linearly with L1 as the model mechanically
  assumes.
- The bus-cap doc's **35.4 A** is a hardware-derived *protection threshold*
  masquerading as an operating-point estimate; its **40 A** upper bound is an
  uncited guess that the project's own literature research contradicts
  (implying R_eff below even the low end of comparable full-scale sources).
  Likely an **overestimate** as a delivered-power figure, though it remains
  the correct number for what it actually is: the trip-threshold RMS
  equivalent.
- **Best current estimate, with uncertainty stated: I_tank,rms ≈ 20.7–30 A at
  1800 W, L=150 µH assumed**, spanning the sweep's as-simulated figure at the
  low end to the literature-anchored-R_eff triangulation at the high end.
  **This is not a tight number** — it depends on an R_eff assumption that
  varies 2.0–4.2 Ω (≈2.1×) across defensible, differently-reasoned choices,
  none of which is a bench measurement.
- **The falsifier's fallback holds: the design point is under-specified.**
  What would settle it: **a bench measurement of R_eff (or equivalently,
  tank RMS current) on the actual coil and a representative pan, at the
  committed ~37–47 kHz loaded operating band** — the same measurement
  `TANK_COIL_SPECIFICATION.md`, `coil-pan-coupling-prior-art.md`, and
  `zvs-operating-point.md` already independently identify as the terminal
  fix for the coil-inductance question. A single-frequency measurement
  cannot separate `K`, `L2`, `RPAN` (per `pan-model-correction.md` §1's own
  "three unknowns, two equations" caveat) — the three-frequency bench spec
  in `2026-07-27-coil-pan-coupling-resolution.md` §4 (25/35/45 kHz) is
  required to pin all three simultaneously, which is exactly what would also
  settle whether R_eff scales with L1 or not.

**Per the task's explicit note, this reconciliation does not overturn the
bus-cap doc's FAILS verdict** — confirmed quantitatively in §6 below: the
verdict is unchanged (fails 4.1×–5.1× rated current) across all three
candidate tank-current figures, because the low-frequency mains-recharge term
alone already fails 2.8–4.2× independent of any tank-current assumption.

---

## 6. Knock-on effects of the corrected/bracketed current

All three candidate figures (20.7 A / ~29.3 A midpoint of the triangulated
band / 35.4–40 A) are carried through, since none is established as sole
correct.

### 6.1 OCP-01 trip margin (50.1 A peak trip)

| I_rms scenario | I_peak (crest factor) | vs. 50.1 A trip | Margin |
|---|---|---|---|
| 20.7 A (sweep) | 28.71 A (simulated crest 1.387, near-resonant, not pure sinusoid) | clears | **+43%** |
| ~29.3 A (triangulated, §4) | ≈40.6 A (same crest factor applied — not independently simulated) | clears | **≈+19%** |
| 35.4 A (bus-cap lower bound) | 50.1 A (by construction — this figure *is* the trip converted back) | at the edge | **≈0%** |
| 40.0 A ("typical") | 56.6 A (pure-sinusoid crest √2, per `ocp01-vs-full-power-current.md`) | **exceeds** | **trips before 1800W** |

Note the crest factor used for the sweep (1.387) is the *simulated* value at
that exact operating point (28.71/20.70), not the pure-sinusoid 1.414 the
OCP-01 doc assumes for its own conversion — a small (≈2%), previously
unremarked inconsistency between the two documents' methods, immaterial to
the qualitative conclusion but flagged for completeness.

**Effect of this reconciliation: OCP-01 headroom is real but likely
narrower than the sweep's standalone "43% margin" claim** — plausibly
~19–43% rather than a comfortable, robust 43%, and vanishing entirely if the
true operating point is anywhere near the bus-cap doc's assumed band.

### 6.2 Bus-capacitor ripple headroom

Using the bus-cap doc's own per-cap conversion (`actual = 0.3536×I_tank,rms`,
`120Hz-equiv = actual / FM(35kHz≈47kHz, 1.49)`), combined in quadrature with
its unchanged central LF term (9.94 A):

| I_tank,rms | HF term, 120Hz-equiv (A) | Combined (A) | vs. 2.70 A rated | Margin |
|---|---|---|---|---|
| 20.7 A | 4.92 | 11.09 | fails | **4.11×** |
| 29.3 A | 6.95 | 12.13 | fails | **4.49×** |
| 35.4 A | 8.40 | 13.01 | fails | **4.82×** (matches doc's own reported central case) |
| 40.0 A | 9.49 | 13.74 | fails | **5.09×** |

**Verdict unaffected across the full range** — as already noted in
`inductance-range-sweep.md` §4 and independently confirmed here: the LF term
alone (2.8–4.2× rated) already fails the design before any HF/tank-current
term is added. This reconciliation **narrows the total-ripple overage from
4.1–5.1× (vs. the original doc's 4.2–5.8× using only its own 35.4–40 A
band)** but does not change the FAILS verdict.

### 6.3 Tank-capacitor voltage/current rating

**Voltage:** unaffected in any material way. The existing sweep (`docs/
evidence/2026-07-27-inductance-range-sweep.md` §2.3.5) reports peak tank-cap
voltage of 331 V at L=150 µH (128–867 V across the full 50–250 µH range
tested), comfortably inside both the 1600 V part rating and the 572 V
declared floor (`v_tank_peak*1.43`) at every point tested — a ~2× current
uncertainty at fixed L is unlikely to move voltage outside that margin, but
this was **not independently re-simulated at the triangulated ~29 A
operating point** — flagged `UNVERIFIED` below rather than assumed.

**Current/ripple rating:** `elec/src/modules.ato` declares no ripple-current
rating field for `c_tank1`/`c_tank2` (`FKP1U021507E00JSSD`) — only
`voltage_rating`. No committed assertion or BOM figure exists to check the
20.7–40 A tank-cap current range against. **Flagged as a gap, not fabricated**
— the tank capacitor sees essentially the full tank inductor current (they
are in series in the resonant loop), so whichever of the three current
figures is eventually confirmed applies directly to this part's current
rating, which this evidence chain has not yet verified against a datasheet
figure.

### 6.4 IGBT conduction loss

No dedicated IGBT conduction-loss evidence document exists in this project
(searched `docs/`, `docs/evidence/` — none found; only thermal/switching
mentions in `STRATEGY.md`, `FUNCTIONAL_TEST_CRITERIA.md`, `METHODOLOGY.md`,
none with a computed loss figure). Standard two-term IGBT conduction-loss
model: `P_cond ≈ V_ce0·I_avg + r_ce·I_rms²` (per device, each conducting
roughly half the tank waveform in this half-bridge topology). **Qualitatively**:
a current figure uncertain by up to ~2.1× (20.7 A to 4.2 Ω-implied, vs.
~29–40 A at the other assumptions) implies conduction loss uncertain by
roughly the same ~2× on the linear (`V_ce0·I`) term and up to ~4× on the
quadratic (`r_ce·I²`) term. **No specific wattage is stated here** — this
project has not published an `IKW40N120H3` `V_ce(sat)`/`r_ce` figure with
provenance, and fabricating one would violate the measurement-provenance
discipline this task explicitly asks to protect. **Any future IGBT
conduction-loss estimate keyed to either disputed current figure inherits
this same 2–4× uncertainty band until R_eff is bench-measured.**

---

## 7. UNVERIFIED

- **The true tank RMS current at 1800 W** — bracketed 20.7–30 A by this
  document's arithmetic, not measured. Neither endpoint is a bench figure.
- **Whether R_eff scales with the coil's own L1** (sweep's implicit
  assumption) **or is closer to an L1-independent pan/frequency property**
  (literature synthesis's framing) — the single open question that would
  resolve most of this contradiction, not answered by any evidence in this
  repository.
- **K=0.79, L2=218µH, RPAN=10Ω** — all three are "constraint-satisfying, not
  measured" per their own originating document; a bench measurement at
  25/35/45 kHz (already specified in `2026-07-27-coil-pan-coupling-
  resolution.md` §4) would pin all three and settle the L1-scaling question
  simultaneously.
- **Tank-capacitor peak voltage at the triangulated ~29 A operating point** —
  not independently re-simulated; only the sweep's own as-tested 331 V figure
  (at the 20.7 A point) is confirmed.
- **IKW40N120H3 conduction-loss parameters (`V_ce(sat)`, `r_ce`)** — not
  sourced anywhere in this repository's evidence chain; §6.4's uncertainty
  scaling is qualitative only.
- **`c_tank1`/`c_tank2` ripple-current rating** — not declared in
  `elec/src/modules.ato`, not checked against any of the three candidate
  current figures.
- **The crest-factor discrepancy** (1.387 simulated vs. 1.414 pure-sinusoid,
  §6.1) between the sweep and the OCP-01 doc's own conversion method — noted,
  not resolved; a ≈2% effect, immaterial to the qualitative conclusion.

---

## 8. Gate verification (this pass)

Performed in an isolated worktree branched from `fed05e82` (checked out as
local branch `tank-current-reconciliation`), touching only this new file
under `docs/evidence/`.

| Check | Result |
|---|---|
| `make netlist` | Succeeds; assertions report generated, no `FAILED` lines (only pre-existing implicit-declaration deprecation warnings, unrelated) |
| `check_domain_partition` | exit 0 |
| `capacity_budget_gate` | exit 0 |
| `mpn_fabrication_gate` | exit 0 (0 new violations) |
| `check_derived_doc_drift` | exit 0 |
| `check_copper_net_consistency` | exit 0 |
| `check_rust_drc_presence` | exit 0 |
| `check_net_classification` | exit 0 |
| `check_pll_range_consistency` | exit 0 |
| `check_isolation_keepout` | exit 3 (expected, per task) |
| `check_measurement_provenance` | exit 5 (expected, per task) |
| `check_undeclared_imports` | **exit 3** — pre-existing, unrelated to this pass: 29 undeclared imports of `temper_placer`/`sympy` in `scripts/*.py` and `packages/temper-placer/tests/*`, none touched by this task (scope was `simulation/`, `docs/`, `elec/src/` only; `scripts/` and `packages/` are explicitly other agents' territory per the task brief) |
| `check_stale_extensions` | **exit 3** — pre-existing, unrelated: 9 Rust/maturin extensions in `packages/` are stale relative to source files modified by other agents up to ~27 days after the installed `.so` build times; not rebuilt here per the task's explicit "disk space is tight" / worktree-isolation constraints and out-of-scope directories |
| `uv run --no-sync python -m pytest elec/validation -q` | **30 passed** (pointed `UV_PROJECT_ENVIRONMENT` at the main checkout's existing synced `.venv` rather than creating a new one in this worktree, to respect the disk-space constraint — no new venv or packages were installed) |

The two non-green gates (`check_undeclared_imports`, `check_stale_extensions`)
reflect this checkout's baseline state at `fed05e82` — confirmed by running
them immediately after checkout, before any change in this pass — and are
outside this task's declared scope (`simulation/`, `docs/`, `elec/src/`
only; `packages/` and `scripts/` are other agents' active territory per the
task brief).
