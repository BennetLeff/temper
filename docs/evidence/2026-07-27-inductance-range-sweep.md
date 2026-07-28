# Inductance-range sweep: does the electrical design survive tank-coil L uncertainty?

<!-- provenance: commit=96ec18c76de9ff824aab4a7a414a89b123af4484 dirty=UNKNOWN -->

**Date:** 2026-07-27/28
**Base commit:** `e87e8b90` (`docs/methodology-loop-discipline`). Work done on branch
`inductance-range-sweep`, created from that commit in an isolated worktree
(no files under `elec/`, `pcb/`, `scripts/`, or the router packages were
touched outside `elec/src/main.ato`, per the task's contention boundary).
**Scope touched:** `simulation/harness/run_inductance_range_sweep.py` (new),
`elec/src/main.ato` (declared `l_tank_assumed` + clarifying comments, no
existing value changed), this document, and its supporting evidence JSON
files under `docs/evidence/`.

## Falsifier, stated up front

*"The 0.84% ZVS margin is a real, robust operating point. If it turns out to
be an artifact of the specific assumed L — i.e. the margin swings from
comfortable to hard-switching within the plausible range — then the design
is not fab-ready on assumption alone."*

**Result: FIRES.** At the committed, fixed `f_switching = 47kHz`
(`main.ato:91`), ZVS is **completely lost** (100.4–101.1% margin — full
hard-switching of the 1200V half-bridge) for both ferromagnetic pan presets
(`cast_iron`, `stainless`) at every tested `L` below **≈97–98 µH**, which
sits inside the geometrically-derived plausible range (§1), and below every
literature-referenced comparable real coil this project has already cited
(§1.3, 47–50 µH). The design is not fab-ready on the L=150µH assumption
alone. This is the headline finding.

---

## 1. Deriving [L_min, L_max]

### 1.1 What the geometry docs fix, and what they leave open

`docs/COIL_BRACKET_DESIGN.md` (REQ-MECH-02): OD **up to 200mm**, air gap
**3mm ± 0.5mm**, coil height **5.0mm ± 0.1mm** (§3.3 stack-up table narrows
this locally to ±0.2mm, but the requirements section states ±0.5mm — the
wider figure is used here since it is the actual requirement, not the
stack-up example). **No turn count, inner diameter, or wire gauge is
specified anywhere in this document or in
`docs/hardware/TANK_COIL_SPECIFICATION.md`.** Air gap and coil height affect
coupling (`K`) and mechanical clearance, not `L1` itself in this project's
lumped model — `L1` is set by the coil's own turns/geometry, which these
documents do not constrain.

### 1.2 Geometry-only bound: uninformative, as anticipated

Using the standard circular-spiral current-sheet inductance formula (Mohan
et al. 1999, the modern standard replacement for the classic 1928 Wheeler
formula, widely used for flat/pancake coils):

```
L = (mu0 * N^2 * d_avg * c1 / 2) * [ln(c2/rho) + c3*rho + c4*rho^2]
c1=1.00, c2=2.46, c3=0.00, c4=0.20   (circular-coil constants)
d_avg = (OD+ID)/2,  rho = (OD-ID)/(OD+ID)
```

computed directly (`/private/tmp/.../scratchpad/wheeler.py`, arithmetic
re-run and spot-checked by hand for N=20/ID=60mm/OD=200mm: d_avg=0.13m,
rho=0.538, L=51.5uH — matches the script's 51.53uH) over OD ∈
{150,180,200}mm, turn count N ∈ {6,10,...,50}, and ID ∈ {20,...,120}mm:

**L spans ≈2.5 µH (N=6, tightest winding) to ≈660 µH (N=50, ID=120mm,
OD=200mm) — a >250× range.** This confirms the task's anticipated finding:
**turn count and inner diameter are completely unconstrained by the
committed geometry documents, and the geometric bound alone is not
informative.** Stated per the task's instruction rather than silently
narrowed without a reason.

### 1.3 Narrowing with typical design practice + already-cited external references

Two independent narrowings, both disclosed as their own layer of assumption
(not measurements):

**(a) Plausible turn-count/ID band for a domestic single-zone hob coil.**
Restricting to N=15–30 turns and ID=20–100mm at OD=180–200mm (this project's
ceiling) — a turn range chosen because it is the range needed to reach
inductances of the same order as the values already in play in this
project's own evidence (150µH assumption, 135µH implied by
`f_resonant_nominal`, 80µH simulation default) — gives:

**L ≈ 19 µH to ≈210 µH** across that grid. Still wide (>10×), but no longer
spanning three orders of magnitude, and it brackets both the 150µH
assumption and the external references below.

**(b) Already-fetched external references for comparable real coils —
labelled EXTERNAL, not measured on this project's coil.** These were
fetched and read (not newly searched — this session's web-search budget was
exhausted; these are the same documents `docs/evidence/2026-07-27-coil-pan-
coupling-prior-art.md` already retrieved and cites in full):

| Source | L (unloaded) | Conditions |
|---|---|---|
| Infineon AN235020 *EVAL_2KW_SiC_IH*, Fig. 9 (measured, impedance sweep) | **≈48–50 µH** | 2kW-class flat spiral coil, no pot, 90–150kHz sweep |
| Würth Elektronik 760308101303 (commercial off-the-shelf coil datasheet) | **≈47 µH** | Cross-checked against APHO2025's own bench measurement of the same part |
| APHO2025 Asian Physics Olympiad solution, §1.4 (measured, avg of 4 measurements) | **≈48.7 µH** | Bench coil, various C |

Three independent sources, same order of power class (2kW-ish) and same
topology (flat/pancake coil), converge to a tight **47–50 µH** cluster — but
at a considerably **higher** switching frequency (90–150kHz, Infineon) than
this project's 25–47kHz target band. If reactance/current handling is held
roughly comparable across designs (`L ∝ 1/f` for similar `ωL`), scaling that
reference down by the frequency ratio (~120kHz / ~38kHz ≈ 3.2×) lands at
**≈150–160 µH** — strikingly close to this project's own 150µH assumption.
**This is a plausibility check, not a derivation** — it does not confirm
150µH, it only shows the assumption is not obviously unreasonable relative
to a real, comparable, already-cited coil once frequency is accounted for.

### 1.4 Range used for the sweep

**L_min = 50 µH, L_max = 250 µH.** Lower bound anchored to the tight,
independently-corroborated real-coil cluster (§1.3b) taken at face value
(no frequency scaling applied — the conservative, lower-L reading). Upper
bound covers the higher-turn-count geometric estimates (§1.3a) with margin
above the 150µH assumption. **This range is a bounded estimate, not a
measurement**, and is now the declared `assert l_tank_assumed within 50uH
to 250uH` in `main.ato` (§5).

---

## 2. The sweep

**Harness:** `simulation/harness/run_inductance_range_sweep.py` (new,
reuses `run_zvs_sweep.py` and `run_tank_coil_sweep.py` directly — no
reimplementation). Two modes:

- **`fixed-fsw`** (primary): holds `F_SW` at the **committed**
  `F_SWITCHING_NOMINAL_HZ = 47kHz` (`main.ato:91`) and sweeps only `L`. This
  is the physically correct test for "does the single committed number
  survive coil-to-coil L variation" — a fabricated coil's `L` cannot be
  changed after the fact, and no confirmed real-time PLL retuning to a
  *measured* loaded resonance exists in this project's simulation model
  (only a swept `ratio` parameter, which presumes `L` is already known).
- **`ratio-track`** (secondary, §4): re-derives `f_sw` per `L` to hold a
  fixed `ratio=1.25` over the self-consistent **loaded** resonance
  (`f_res_loaded_hz()`, reused unmodified from `run_tank_coil_sweep.py`).
  Explores the alternative control strategy — PLL-style tracking — rather
  than a fixed nominal frequency.

Grid: `L ∈ {50,70,90,110,130,150,175,200,225,250} µH`, all four
`PAN_PRESETS` (`cast_iron`, `stainless` — both `K=0.79`, identical preset,
hence identical results; `aluminum` `K=0.15`; `no_pan` `K=0.01`), plus a
finer 30-point grid (85–148 µH, `cast_iron` only) to locate the exact
crossings. All runs measured `i_pan_rms_last` → `p_pan_w`,
`i_tank_pk/rms_last`, and (newly surfaced — see harness docstring)
`v_ctank_max/min_last`, already present in the committed `.cir` but never
previously read out by either base harness's own reporting code.

**Smoke test against the known operating point:** `L=150µH, f_sw=47kHz,
cast_iron` reproduces `docs/evidence/2026-07-27-pan-preset-correction.md`'s
reported 0.84% margin, 28.7A peak, ~1800W to within simulation noise
(28.71A vs. the doc's 28.76A; 1797.6W vs. 1804W) — the harness is
consistent with the existing evidence chain before any new claim is made.

### 2.1 Coarse grid, fixed f_sw=47kHz — cast_iron/stainless (identical preset)

| L (µH) | f_res,loaded (kHz) | ratio f_sw/f_res | ZVS margin | label | i_pk (A) | i_rms (A) | P_pan (W) | v_Ctank,pk (V) |
|---|---|---|---|---|---|---|---|---|
| 50 | 66.37 | 0.708 | 100.87% | **zvs_lost** | 38.87 | 27.07 | 1025 | 443 |
| 70 | 55.87 | 0.841 | 101.12% | **zvs_lost** | 58.74 | 40.13 | 3151 | 641 |
| 90 | 49.08 | 0.958 | 100.72% | **zvs_lost** | 79.24 | 54.96 | 7600 | 867 |
| 110 | 44.23 | 1.063 | 0.82% | zvs_held | 60.45 | 43.88 | 5921 | 710 |
| 130 | 40.52 | 1.160 | 0.93% | zvs_held | 39.68 | 29.02 | 3062 | 467 |
| **150** | 37.58 | 1.251 | **0.84%** | zvs_held | 28.71 | 20.70 | 1798 | 331 |
| 175 | 34.62 | 1.357 | 0.74% | zvs_held | 21.40 | 15.02 | 1103 | 238 |
| 200 | 32.23 | 1.458 | 0.67% | zvs_held | 17.21 | 11.72 | 768 | 185 |
| 225 | 30.24 | 1.554 | 0.62% | zvs_held | 14.46 | 9.59 | 579 | 151 |
| 250 | 28.56 | 1.646 | 0.58% | zvs_held | 12.45 | 8.11 | 460 | 128 |

Full JSON: `docs/evidence/2026-07-27-inductance-range-sweep-fixed-fsw.json`
(40/40 measured and converged).

### 2.2 Fine grid — locating the exact crossings (cast_iron, fixed 47kHz)

`docs/evidence/2026-07-27-inductance-range-sweep-fine-crossing.json` and
`...-fine-crossing2.json` (27 points, 85–148µH):

| Crossing | Between | Value |
|---|---|---|
| **ZVS-loss threshold** (margin flips from ~100% lost to <1% held; ratio crosses 1.0) | L=95µH (ratio 0.985, 100.42% lost) → L=98µH (ratio 1.001, 0.30% held) | **L_crit,ZVS ≈ 97 µH** |
| **OCP-01 peak-current trip** (50.1A, `main.ato`'s own committed assertion `i_ocp_trip_peak < 60A`, tripped at 50.1A per the live netlist) | L=118µH (50.66A) → L=119µH (49.57A) | **L_crit,OCP ≈ 118.5 µH** |
| **1800W power target** | L=148µH (1884W) → L=150µH (1798W) | **L ≈ 149 µH** (essentially pinned to the assumption — expected, since `ratio=1.25`/`47kHz` was chosen specifically to hit 1800W at L=150µH in the prior pass) |

### 2.3 What this means, per required output

1. **ZVS margin and its zero-crossing.** At fixed 47kHz, cast_iron/stainless
   ZVS collapses **completely** (not gradually — the transition is a sharp
   step from ~100.5–101.1% lost to <1% held, consistent with
   `TANK_COIL_SPECIFICATION.md`'s earlier finding that ZVS is a threshold
   phenomenon at ratio≈1.0, not a smoothly degrading margin) below **≈97
   µH**. The reported "0.84% margin" at L=150µH is not itself a fragile
   number in isolation — margin *stays* under 1% everywhere it holds at all
   (0.44–0.93% across the whole 98–250µH held region) — but that small
   number describes closeness to *ideal* ZVS, not distance from the
   *cliff*. The distance from the cliff is the **ratio**, and ratio falls
   below 1.0 (full loss) at ~35% lower L than the assumption. Aluminum and
   no_pan (low K, never load the tank much) hold ZVS across the entire
   50–250µH range tested — consistent with them being the presets *not*
   raised by the K correction.
2. **Delivered power vs. 1800W, per pan.** At fixed 47kHz, cast_iron/
   stainless power is **not flat with L** — it swings from 460W (L=250µH,
   74% short) through 1798W (L=150µH, on target) to a peak of **7834W at
   L=92µH (4.3× over target)** immediately before the ZVS cliff, then to
   1025W (L=50µH, 43% short) *while already hard-switching*. There is no
   region of this range that delivers close to 1800W except a narrow band
   within a few µH of the L=150µH assumption itself (§2.2, third row) — the
   frequency was tuned to that exact point, not derived from anything that
   would generalize. Aluminum stays far under target everywhere (max 97.5W
   at L=50µH; the model's known aluminum shortfall from
   `pan-preset-correction.md` is reconfirmed, not changed, by this sweep).
3. **Peak/RMS tank current vs. OCP-01's 50.1A trip.** Current is high
   exactly where power overshoots: L=90–119µH draws 49.6–79.2A peak,
   **exceeding OCP-01's 50.1A trip** for L≲118.5µH (§2.2) — meaning that
   band is not just off-power, it would trip the cooker's own overcurrent
   protection before reaching it. Below the ZVS-loss threshold (L<97µH),
   current is still substantial (38.9–79.2A peak) while *also*
   hard-switching — the two failure modes overlap, they do not trade off.
   Above L≈150µH, current falls comfortably under trip (28.7A peak at
   150µH, monotonically decreasing above that).
4. **`f_sw/f_res,loaded`.** Reported per row in §2.1/2.2 — the ratio that
   actually governs ZVS state (not the unloaded ratio, which the
   `pan-preset-correction.md` bug already showed is the wrong reference).
   It crosses 1.0 at L≈97µH, matching the ZVS-margin crossing exactly (as
   it must — margin and ratio-vs-1.0 are the same physical event viewed two
   ways).
5. **Tank capacitor peak voltage vs. rating.** `c_tank1`/`c_tank2`
   (`FKP1U021507E00JSSD`) are rated **1600V** (`modules.ato:448/455`), with
   a separate committed design floor `v_tank_peak=400V` /
   `assert voltage_rating >= v_tank_peak*1.43` (572V, `modules.ato:459-461`
   — already checked and passing in `make netlist`, unrelated to this
   sweep). Across the entire tested range (50–250µH, all pans, fixed 47kHz)
   peak tank-cap voltage is **128–867V**, comfortably inside the 1600V
   rating everywhere, including at the worst-case ZVS-lost points
   (867V at L=90µH). **This margin is NOT threatened anywhere in the tested
   range** — the tank cap is not the constraint; ZVS state and OCP-01
   current are. Caveat: this is the model's idealized switching-node
   voltage at the times sampled; real hard-switching ringing (parasitic
   inductance, diode reverse recovery) is not modeled here and could
   exceed this figure — flagged, not fabricated, in §6.

---

## 3. Ratio-tracking alternative (secondary scenario)

If the control system instead re-tunes `f_sw` in real time to hold
`ratio=1.25` against the **self-consistent loaded** resonance (rather than
running at a fixed nominal frequency), the picture changes substantially:

`docs/evidence/2026-07-27-inductance-range-sweep-ratio-track.json`
(38/40 measured — two `L=200µH cast_iron/stainless` points hit the same
knife-edge ngspice convergence issue already documented in
`pan-preset-correction.md` §4.3 for L=70µH; not re-derived here, flagged
UNMEASURED):

| L (µH) | required f_sw (kHz) | margin | P_pan cast_iron (W) | i_rms (A) |
|---|---|---|---|---|
| 50 | 82.96 | 1.32% held | 2246 | 39.76 |
| 70 | 69.84 | 1.13% held | 2141 | 32.86 |
| 90 | 61.35 | 1.04% held | 2045 | 28.37 |
| 110 | 55.28 | 0.95% held | 1958 | 25.15 |
| 130 | 50.65 | 0.88% held | 1877 | 22.69 |
| 150 | 46.97 | 0.84% held | 1804 | 20.74 |
| 175 | 43.28 | 0.78% held | 1720 | 18.79 |
| 225 | 37.81 | 0.70% held | 1574 | 15.92 |
| 250 | 35.69 | 0.68% held | 1511 | 14.83 |

**ZVS holds at every measured point across the entire 50–250µH range under
this control strategy**, and power stays within roughly ±25% of 1800W
(1511–2246W) rather than the fixed-frequency mode's 460–7834W swing.
Required frequency spans **35.7–83.0 kHz**, which fits inside the declared
`assert f_switching within 20kHz to 100kHz` (`main.ato:92`) with margin at
both ends of the tested range, though it approaches the top of that window
at the lowest tested L (83.0kHz at 50µH, leaving only 17kHz of headroom to
the 100kHz ceiling).

**This does not mean the design "actually" holds across the range** — it
means a *different, not-yet-confirmed-implemented* control strategy would
hold it, IF it can track the self-consistent loaded resonance in real time
without knowing `L` in advance (the simulation computes `ratio` from a
known `L`; a real PLL must find resonance from measured phase/current, a
harder problem this sweep does not model). See §6 for what
`docs/PLL_ZVS_INTEGRATION_GUIDE.md` already implements and what it does not
yet close.

---

## 4. Cross-check against the bus-capacitor ripple bound (task 3)

`docs/evidence/2026-07-26-bus-capacitor-ripple.md:98-107` used an
**externally-sourced tank-current bound of 35.4–40A RMS** (35.4A = OCP-01's
50.1A peak trip converted to RMS; 40A = a cited "typical 1.8kW hob" figure)
because `L_TANK` was undefined at the time, and found the bus caps already
fail their rated ripple current 2.8–4.2× on the low-frequency term alone,
independent of that bound.

**This sweep's own designed operating point (L=150µH, ~1800W, fixed
47kHz) predicts i_tank_rms ≈ 20.7A — well BELOW the bus-cap doc's 35.4–40A
band, not consistent with it.** Tracing why: implied `R_eff = P/i_rms² =
1798/20.70² ≈ 4.20 Ω` at this point, which lands squarely inside the
**literature-cited R_eff ≈ 2.0–4.5 Ω range** already assembled in
`docs/evidence/2026-07-27-coil-pan-coupling-prior-art.md` (Infineon-derived
~2.2Ω at 35kHz, IJCRT's 2Ω design assumption) — **not** the bus-cap doc's
implicit 1.12Ω (`=1800/40²`, back-calculated from its own "40A typical"
figure, which that same prior-art document already flagged as an
**uncited** assumption, §"OCP-01 vs. 1800W" there). In other words: this
disagreement is not new — it is the same inversion the prior-art document
already found ("literature leans toward *no conflict*... inverting the
project's own typical-40A assumption"), now independently reproduced by a
full L-sweep of the corrected pan-coupling model rather than by literature
alone.

**Where in this sweep does 35.4–40A RMS actually occur?** Only in a
narrow band around **L≈114–121µH** (i_rms 39.5A at 114µH down to 35.5A at
120µH, from §2.2's fine grid) — which is *also* the band that delivers
4200–5000W (2.3–2.8× over the 1800W target) and straddles the OCP-01
peak-current trip (§2.2). **The two analyses do not reconcile at a single
consistent (L, f_sw, 1800W) point within this sweep**: the bus-cap doc's
current bound matches this model only at an L/power combination the model
itself calls out-of-spec for an entirely different reason (OCP-01
overcurrent). This is a genuine, reportable disagreement between two
independently-conducted analyses, not a confirmation of either.

**What this changes and does not change:** if the real coil turns out to
sit anywhere near L=150µH and the fixed-47kHz operating point, the
bus-cap doc's 35.4–40A high-frequency term was likely an *overestimate*
(this model implies ~20.7A instead) — which would make the bus-cap FAILS
verdict *less* severe on the HF term specifically. It does **not** change
the bus-cap doc's overall FAILS verdict, because that verdict already fires
from the **low-frequency (mains-recharge) term alone**, 2.8–4.2× over
rated, entirely independent of the tank/HF term (`2026-07-26-bus-capacitor-
ripple.md` §8, "the falsifier does not hold"). Separately, if the real coil
instead sits near L≈97–119µH (inside the geometrically plausible range,
§1), tank current in that band is 35–55A RMS — **within or above** the
bus-cap doc's cited band — while simultaneously being ZVS-lost or
OCP-tripping. The two failure modes would then compound rather than
trade off.

---

## 5. What was declared in `elec/src/main.ato`

Per the task's instruction not to leave the L assumption invisible, and
without changing any existing committed value (`f_switching`,
`f_resonant_nominal`, `C_tank`, `K`, or any assertion bound already in the
file — this sweep changes nothing that would alter another analysis's
margins):

```
l_tank_assumed: inductance = 150uH
assert l_tank_assumed within 50uH to 250uH  # bounded estimate, NOT measured
```

placed immediately after `f_resonant_nominal`, with a comment block citing
this document, stating explicitly that `inductor_conn` remains an unplaced
placeholder (this is still not a specified coil), that the range is a
geometry-bounded *estimate* cross-checked against external references (not
a measurement), and — the load-bearing sentence — that **the sweep in this
document finds ZVS is completely lost below ≈97µH, a value inside, not
outside, this declared range**. `f_resonant_nominal`'s own comment block
was extended (its declared 25kHz value was **not** changed) to state
explicitly that it names the **UNLOADED** resonance, closing the
loaded-vs-unloaded ambiguity the task flagged as having already caused one
real bug (`run_tank_coil_sweep.py`'s unloaded-reference defect,
`pan-preset-correction.md` §3).

`l_tank_assumed: inductance = 150uH` **compiles and asserts successfully**
(confirmed via `make netlist`; `inductance` is a valid atopile physical
quantity type, not previously used elsewhere in this project's `.ato`
files but accepted without error) — the assertion appears in the live
assertions table as `150uH within 50 to 250 uH — PASSED`. This is a real,
checked declaration, not a comment.

---

## 6. Interaction with existing protections (relevant, not fixed here)

`docs/PLL_ZVS_INTEGRATION_GUIDE.md` (2025-12-17, "Implementation Complete,
Hardware Integration Required") documents a firmware-level ZVS monitor that
measures the actual switch-node voltage before turn-on
(`V_SW < 50V` = ZVS success) and responds with a graduated policy (1–3
consecutive hard switches → warning + increased dead time; >3 → 50% power
reduction; >10 → shutdown). **This check is L-agnostic** — it measures the
real switching voltage in hardware rather than depending on any assumed
`L`, so if the real coil falls into the ZVS-lost region this sweep
identifies, the firmware (if actually wired to real hardware per that
document's own "Hardware Integration Required" status) would in principle
detect and mitigate it rather than fail silently. Two caveats, not resolved
here because they are firmware/hardware-integration questions outside this
task's `simulation/`, `docs/`, `elec/src/` scope: (1) that document's own
example configuration hardcodes `pll_set_resonant_frequency(35800.0f)` —
the **pre-correction** 35kHz value already shown elsewhere in this
project's evidence to lose ZVS for ferromagnetic pans — and has not been
updated to reflect the 47kHz correction or any L-range finding here; (2)
"1–3 consecutive hard switches → warning only" means some non-zero number
of full hard-switching events (at up to 100%+ margin, i.e. turn-on near
full 340V bus) occur before any power reduction — for a 1200V-rated but
otherwise not over-specified device, whether that many hard-switch events
before mitigation is acceptable is a question this document does not
answer.

---

## 7. Verdict

**"Design holds only over a narrower sub-range."**

- **ZVS-holding range at the committed, fixed 47kHz: L ≳ 97 µH** (of the
  50–250µH plausible range derived in §1). Below that, ZVS is completely
  lost for ferromagnetic pans (cast_iron/stainless) — not degraded, fully
  hard-switching a 1200V half-bridge.
- **A materially narrower "everything OK" band: L ≈ 120–160 µH** — needed
  additionally to stay under OCP-01's 50.1A peak trip (crosses at
  ≈118.5µH) and to stay reasonably near the 1800W target (which is
  essentially pinned to L≈149–150µH by how `ratio=1.25`/`47kHz` was chosen
  in the prior pass, not derived independently here). Outside that ~40µH
  band, the design either hard-switches, trips its own overcurrent
  protection, or misses the power target by a large factor — usually more
  than one of these simultaneously.
- **This ~120–160µH "safe" band sits entirely on the high side of the
  already-cited, real, comparable-coil references (47–50µH, §1.3b).** If
  this project's actual coil ends up anywhere near those references without
  the (unverified) 3.2× frequency-scaling correction applied, **it lands
  well inside the ZVS-lost region.**
- **What would widen the range:** (a) an actual bench-measured coil `L`
  (closes the question directly — this remains the terminal fix, per
  `TANK_COIL_SPECIFICATION.md` and `2026-07-27-zvs-operating-point.md`);
  (b) a verified, hardware-validated real-time resonance-tracking PLL
  (§3/§6) that retunes `f_sw` to the *measured* loaded resonance rather
  than running at a fixed nominal frequency — the ratio-tracking sweep
  shows this would hold ZVS and keep power within ±25% of target across
  the whole 50–250µH range, at the cost of needing frequency agility up to
  ~83kHz at the low-L end (still inside the declared 20–100kHz window, but
  with reduced headroom); (c) a coil geometry specification (turn count,
  ID, wire gauge) that pins `L` to a narrower band than §1's ~10× spread
  before fabrication, rather than leaving it to be discovered at bench
  measurement.

**The falsifier fires.** The 0.84% margin at L=150µH is not a robust
operating point in the sense the task worried about — it sits inside a
range whose lower half, including values matching already-cited real
comparable coils, fully hard-switches at the committed operating frequency.

---

## UNVERIFIED

- **`L` itself** — still not specified or measured; `inductor_conn`
  remains an unplaced Litz footprint placeholder. `[50, 250] µH` is a
  bounded *estimate* (§1), not a measurement.
- **The `L ∝ 1/f` scaling argument (§1.3)** used to reconcile the 47–50µH
  external references with this project's 150µH assumption — a
  plausibility check, not a validated physical model for this specific
  coil/frequency combination.
- **Hard-switching voltage/current transients beyond this model's
  resolution** — the tank-cap peak-voltage figures (§2.3.5) and all
  current figures in the ZVS-lost region come from an idealized
  behavioral IGBT model with fixed capacitances (`calibrated: false`,
  carried forward from every prior evidence document in this chain); real
  hard-switching ringing from parasitic inductance and diode reverse
  recovery is not modeled and could exceed the reported peak values.
- **Whether the ratio-tracking control strategy (§3) is actually
  implementable** — it presumes a controller that finds the true loaded
  resonance from live measurement, which is a harder problem than the
  simulation's "compute ratio from a known L" and is not validated here.
  `docs/PLL_ZVS_INTEGRATION_GUIDE.md`'s ZVS monitor is a mitigation for
  *detecting* hard-switching once it happens, not a resonance-tracking PLL
  that prevents it by construction.
- **`docs/PLL_ZVS_INTEGRATION_GUIDE.md`'s hardware-integration status** —
  documented as "Hardware Integration Required" as of 2025-12-17; whether
  it is wired to real ADC/comparator hardware on the actual board, and
  whether its hardcoded 35.8kHz configuration has been updated since, was
  not checked here (out of this task's `simulation/`, `docs/`, `elec/src/`
  scope).
- **The bus-capacitor cross-check (§4) reconciliation** — the two analyses'
  disagreement at the L=150µH/1800W point is explained qualitatively
  (different implicit R_eff), not resolved by a bench measurement of
  either R_eff or tank current.
- **Aluminum/no_pan's OCP-01 crossing at low L** — noted qualitatively
  (crosses somewhere between L=50µH, 63.1A peak, over trip, and L=70µH,
  22.8A peak, under trip) but not finely bisected, since aluminum never
  approaches the 1800W target in this range regardless (max 97.5W) and is
  not the pan class this design's ZVS margin question turns on.

## Provenance

- Sweep evidence: `docs/evidence/2026-07-27-inductance-range-sweep-fixed-
  fsw.json`, `-fine-crossing.json`, `-fine-crossing2.json`,
  `-ratio-track.json` — all `"source": "measured-live"`,
  `commit=e87e8b90...` (dirty=true, this pass's own uncommitted-at-
  measurement-time changes), branch `inductance-range-sweep`.
- Geometry arithmetic: ad hoc script, current-sheet formula per §1.2,
  spot-checked by hand for one grid point (N=20, ID=60mm, OD=200mm →
  51.53µH) as shown in §1.2.
- All numbers in §2–§4 are simulated (ngspice, `zvs_margin_sweep.cir`) or
  derived arithmetically from simulated outputs (R_eff, crossing
  interpolations) — none are bench-measured. Simulation fidelity caveats
  (`calibrated: false`, behavioral IGBT model) carry forward unchanged from
  every prior document in this evidence chain.
