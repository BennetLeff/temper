# F2-open time-domain model

**Review correction (2026-09-19):** this is a plant/scheduled-gate screen,
not a simulation of the selected detector, latch, clamp and controller.
Package 2 remains incomplete. Startup bounds and the single-event claim
are withdrawn; see section 4 and `../../decisions/f2-open/PROTECTION-SELECTION.md`.
Historical CSVs are not overwritten. Corrected output is retained in
`../../evidence/protection-review-04/`.

Source: `f2_open_timed.rs` (build `rustc -O f2_open_timed.rs -o
/tmp/f2_open_timed`). Raw outputs: `raw/timed-sweep.csv`,
`raw/startup-bursts.csv`. Scope: **healthy U9 only**. Failed-short U9 is not
modeled (no gate command opens that path) and stays a separate qualification
case. All peaks are **illustrative model results**, not qualified predictions;
part ceilings used for comparison are authored values, not qualifications.

## 1. What changed vs the immediate-off screen

The retained screen (`f2_open.rs`, 674.7 V at the nominal crest case) assumes
the gate is already off while Vc = 389.6 V. That is the optimistic lower
latency case: with diode-side feedback the controller keeps switching until
the *filtered* sense crosses OVP, pumping line energy into 470 nF the whole
time. This model adds (i) the VSENSE filter + threshold-crossing detection,
(ii) continued switching for T_resp under the stated gate law below, and
(iii) sinusoidal mains inflow during the event. Result at the same nominal
case with *zero* post-trip delay: **751.4 V**, not 674.7 V. Every row below
exceeds the immediate-off figure; the 674.7 V number is superseded as a bound
but retained as the closed-form limit the integrator is checked against.

## 2. Controller-behavior representation

Primary source: retained `zapote/power-entry/shunt-repair/sources/
TI-UCC28180.pdf` Rev D (SHA-256 `e1e1588c…1b00be`). Pages are printed
datasheet pages (section numbers are exact; page spans approximate).

| # | Behavior | Datasheet basis | Treatment here |
|---|---|---|---|
| 1 | Soft-start ramp (1.5 V precharge, 40 uA into VCOMP network, EDR inhibited, end at 98% VSENSE) | §8.3.1 (p. 14), Fig. 23 | Detailed loop dynamics **NULL** (missing: large-signal comp-network response). The earlier first-trip-energy → cycle-upper-bound inference is withdrawn in §4. Capacitor charge inventory alone does not establish current at detection, transferred energy per cycle, cycle count or wall-clock time-to-trip. |
| 2 | OVP_L: 4 kΩ VCOMP discharge above 107% VREF | §8.3.4 (pp. 14–15), EC table (p. 6): 105/107/109% | **NULL** (missing: VCOMP/EDR state at event). Omission is conservative for peak (it can only reduce duty before OVP_H). |
| 3 | OVP_H: GATE disabled above threshold, re-enabled below 102% | §8.3.4 (pp. 14–15), EC table (p. 6): 107/109/111%, reset 100/102/104% | **Modeled** as threshold corners at the power node: early 403.0 V / typ 424.7 V / latest 454.3 V (VREF × OVP% ÷ divider ratio; latest uses over-temp VREF 4.87–5.15 V and assumed ±1% divider tolerance). Reset window modeled in burst analysis (typ 397.4 V). |
| 4 | OLP/standby below 16.5% VREF (15.6/17.6% corners); internal 100–325 nA VSENSE pull-down; ICC standby 1.8–3.47 mA | §8.3.5 (p. 15), EC table (p. 6) | Entry dynamics **NULL** (missing: external pull-down strength — set by the selected inhibit FET, see PROTECTION-SELECTION). Standby state modeled only as the *target* of the inhibit path. |
| 5 | SOC (−0.259/−0.285/−0.312 V pin): 4 kΩ VCOMP discharge, UVD disabled | §8.3.11 (p. 17), EC table (p. 6) | **NULL** (missing: VCOMP/average-current state). Omission conservative for peak (SOC only reduces duty). |
| 6 | PCL (−0.345/−0.40/−0.438 V pin): immediate cycle termination, 300 ns leading-edge blanking | §8.3.12 (p. 17), EC table (p. 6) | **Modeled** as early-OFF at sourced current corners 34.16/40.00/44.24 A (TI pin thresholds ÷ authored 10 mΩ Rsense ±1% per retained Stackpole HCSM doc + MPN `F` code). 300 ns blanking + 220 Ω/1 nF ISENSE filter **NULL**-unmodeled (0.22 µs ≪ event; omitting blanking can be optimistic when PCL engages; these are not bounded rows). PCL never engages in any nominal row (peak switch current ≈ 27 A); it binds only extreme-I0 corners. |
| 7 | VCC UVLO (on 10.8–12.1 V, off 9.1–10.3 V, 1.7 V typ hyst.); GATE held off below UVLO; VCOMP rapid-discharge on VCC loss (<1 V in 150 ms typ) | §8.3.3 (pp. 14–15), §8.3.15, EC table (p. 6) | Thresholds carried as the **loss-of-bias safe-state basis** (same-rail argument in PROTECTION-SELECTION). AUX_15V source behavior and VCC hold-up timing **NULL** (missing: bias-supply producer contract). |
| 8 | EDR (5× gm outside VSENSE 4.75–5.25 V, inhibited until soft-start complete) | §8.3.9 (pp. 15–16) | **NULL** (missing: large-signal comp response). Omission conservative for peak on overvoltage (EDR speeds VCOMP discharge). |
| 9 | VSENSE filter (authored 680 pF; Thevenin 12.835 kΩ → τ ≈ 8.73 µs nominal) | Authored source (not TI) | **Modeled** as first-order lag at nominal τ. Capacitor tolerance **NULL** (no retained doc for the 680 pF part) — τ corners not swept. |
| 10 | OVP comparator + logic + GATE fall propagation | TI (no number published) | **NULL in hardware, swept as requirement**: T_resp ∈ {0, 2, 5, 10, 20} µs. Never zero-by-default; every peak below is conditional on its T_resp row. |

Gate law while unaware (STATED SIMPLIFICATION): fixed period 1/129107 Hz,
D = clamp(1 − vin/v, 0, 0.965) evaluated at cycle start, ideal switch
(Ron = 0) and ideal diode (Vf = 0). Mains: |169.7056·sin(θ0 + ωt)|, 60 Hz
assumed. I0(θ) = 21.1710·sinθ + 2.0609 A (retained mean + ripple peak;
constant half-ripple across phase is a stated bounding simplification).
L = 180 µH nominal (+216 µH assumed sensitivity; saturation curve NULL).
C = 470 nF nominal (±10% assumed axis; 1.0/1.5 µF evaluated values assumed,
not selected). High-line (+10% Vpk) row is an assumed sensitivity, not a
tolerance bound. Diode-side start voltage 389.615 V nominal in all event rows.

## 3. Corner results (case b: F2 opens during operation)

`Vpk` vs the illustrative 630 V ceiling (U40 authored 630 VDC; see budget):

| Case | T_resp | Vpeak | Verdict vs 630 (illustrative) |
|---|---|---|---|
| Crest, 470 nF, typ OVP | 0 µs | 751.4 V | exceeds |
| Crest, 470 nF, typ OVP | 2 µs | 778.9 V | exceeds |
| Crest, 470 nF, typ OVP | 5 µs | 821.9 V | exceeds |
| Crest, 470 nF, typ OVP | 10 µs | 854.1 V | exceeds |
| Crest, 470 nF, typ OVP | 20 µs | 947.2 V | exceeds (abort limit 950 approached) |
| Crest, 1.0 µF | 5 µs | 645.9 V | exceeds |
| Crest, 1.5 µF | 5 µs | 598.0 V | closes (illustrative) |
| Crest, 470 nF, L=216 µH | 5 µs | 852.2 V | exceeds |
| Crest, 470 nF, C=423 nF | 5 µs | 849.4 V | exceeds |
| Crest, 470 nF, C=517 nF | 5 µs | 797.4 V | exceeds |
| Phase 45°, 470 nF | 5 µs | 659.6 V | exceeds |
| Phase 30°, 470 nF | 5 µs | 576.0 V | closes (illustrative) |
| Crest, OVP latest (454 V) | 5 µs | 824.9 V | exceeds |
| Crest, OVP early (403 V) | 5 µs | 800.6 V | exceeds |
| Crest, detector-latest (510 V) | 5 µs | 877.1 V | exceeds |
| Crest, I0 +10% assumed | 5 µs | 863.0 V | exceeds |
| Crest, PCL min (34.2 A) | 5 µs | 821.9 V | identical (PCL never trips) |
| Crest, 1.5 µF | 0 µs | 576.2 V | closes (illustrative) |
| Crest, 1.5 µF | 20 µs | 657.6 V | exceeds |
| Crest, 1.5 µF, det-latest | 10 µs | 677.5 V | exceeds |
| Crest, 470 nF, det-latest | 0 µs | 824.9 V | exceeds |
| Crest, 470 nF, det-latest | 2 µs | 840.3 V | exceeds |
| Crest, Vpk +10% assumed | 5 µs | 835.2 V | exceeds |

Mains inflow dominates every crest row: source work to peak is 48–182 mJ
against 48–59 mJ released inductor energy. The response axis is steep:
≈15 V/µs at 470 nF near trip (≈5 V/µs at 1.5 µF), so each microsecond of
detection delay costs roughly that many volts — the delay budget in
PROTECTION-SELECTION inverts this slope.

## 4. Startup and restart — bounds withdrawn

The historical `raw/startup-bursts.csv` used 470 nF while the proposed
integration uses 1.5 uF. At the same illustrative 424.68 V, stored energy
is 42.382979064 mJ and 135.2648268 mJ respectively. Neither is a bound on
source work, current at detection or time-to-trip.

`ceil(E / E_cycle_max)` cannot upper-bound the cycles required: a smaller
transfer per cycle takes longer. The assumed per-cycle maximum and the
residual current used for the 545.3 V result were also unestablished.
Both the cycle upper bound and startup overshoot bound are withdrawn.

The corrected `burst` output reports those quantities as null and computes
only charge inventory and ideal divider decay. Decay from the chosen trip
voltage to reset is not the time between real bursts: actual overshoot,
other loads, incoming source energy and controller state matter.

A controller OVP trip does not itself set the independent external latch;
the power node might never cross the independent detector threshold.
Single-event behavior is not established, with or without a clamp.
F2-open startup, complete gate-off latency and restart require the selected
combined circuit. Bank-ready must be measured bank-side; OVP is neither a
fuse-continuity proof nor a bank-ready signal.

## 5. Verification (three independent paths)

1. **Closed-form limit** (asserted on every run): gate-off-at-t=0 with
   constant Vin reproduces `f2_open.rs` algebra: 674.7309 V vs 674.7412 V
   (rel 1.5e-5). Burst-period log formula vs numeric bleed integration:
   rel < 3e-5 both corners.
2. **Per-run energy identity** `dEcap − dEL_rel − Wsrc + Ediv` to the peak,
   trapezoidal: residuals 0.000–0.002 µJ on 40–230 mJ events (last CSV
   column; assertion threshold 1 µJ in-code for the check runs).
3. **ngspice cross-check** (`../evidence/f2-open-timed-02/`): freewheel from
   (425 V, 20 A): 636.6334 V both step sizes vs Rust 636.9936 V / closed
   637.0029 V; prescribed switching pattern: 793.7040/793.7035 V vs Rust
   794.3178 V. Differences <0.1% with the expected sign (Rust loss-free;
   ngspice carries synthetic-diode/switch loss, same mechanism as
   oracle-01's 0.45 V).

## 6. What this model does not do (open inputs)

Saturation/temperature curve of the 180 µH inductor; capacitor tolerance and
DC-bias/temperature derating docs; VSENSE filter-capacitor tolerance;
AUX_15V/bias behavior and HOT_PERMIT source contract; VCOMP/EDR large-signal
response; actual comparator/gate delays (carried as T_resp requirement);
failed-short physics; fuse-opening arcing; any surge beyond mains inflow.
Each appears as NULL above or as a qualification requirement in
PROTECTION-SELECTION, never as zero.
