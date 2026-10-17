# Tank-RMS estimator: half-cycle weighting, stuck-low check, bench shadow RMS

Branch `fw/rms-estimator`, cut from integration `93276ac80`. Implements the three firmware items of the
rms-alternatives study (`git show controller-layout:zapote/controller/evidence/rms-alternatives/README.md`,
finding 2 and the recommendation, DECISIONS C35 U14 bullet). No trip threshold, ceiling, guard or
loop constant was changed.

## 1. Half-cycle RMS estimator

### The defect (reproduced on the unmodified code first)

`n21_half_close()` handed 13 or 14 slot readings (625 us grid, half cycle 7833-8834 us) to
`input_limits_half_cycle()`, which took `sqrt(mean(r^2))` with equal weights. Which readings fall in the
window, and how far the end readings sit from the zero crossings, depends on the slot phase and the
half length, so the result scatters.

Host test `test/test_rms_estimator.c`: a closed half of length 7900 / 8333.3 / 8800 us, readings
`A*sqrt2*|sin(pi t/L)|` (true half RMS A), 25 slot phases x 3 amplitudes (4/16/28 A).

| | scatter of `est.tank_rms_a` vs true |
|---|---|
| pre-fix (`93276ac80`) | **-3.12 % .. +2.65 %** (test aborts on the +-0.5 % assertion) |
| fixed | **-0.03 % .. +0.27 %** (slot phase alone, 5 us steps: span 0.21 %) |

The same in the study's own model (`study_model_scatter.py`, 17 waveform windows x 25 slot phases,
AD8436 chain, quantised; output `scatter.txt`; the study quotes -2.95..+1.14 % for 5 phases plus trim):

| | estimator vs exact-window converter output | whole chain vs true half RMS |
|---|---|---|
| equal weights (pre-fix) | -2.29 .. +1.38 % | -3.31 .. +0.78 % |
| time weighted (fix) | **-0.15 .. +0.45 %** | -1.11 .. +0.09 % |

The remaining -1.1 % of the whole chain is the AD8436 55 kHz droop, which the Step 1 trim removes
(study: converter-only -0.69..+0.01 %). The scatter target (<= +-0.5 %) is met in both models.

### The fix

* `n21_half_add()` keeps the reading times (`n21_half_t.t_us`).
* `n21_half_close_aux()` (`n21_signal.c:131-136` (weights loop)) gives each reading the share of the half it stands for:
  mid-point rule between neighbouring readings, the first reaching back to the opening LINE_ZC and the
  last forward to the closing one (readings held to the zero crossings). It writes that into the new
  `input_sample_t.w`.
* `input_limits_half_cycle_aux()` (`input_limits.c:46-60`) uses `w` for both the power sum and the RMS
  (`sum w x / sum w`). All `w == 0` (every existing caller) is the old equal-weight mean, so nothing else
  changes; negative or non-finite weights are refused.
* A gap longer than `half_max_gap_us` still refuses the half, so a long hole cannot be weighted into it.

Side effect on an existing test: `test_freq_loop_live` asserted the fake pan's f_res fit within 600 Hz
of 30350. The fit is 1.9-2.0 % low whatever the estimator (29759 Hz at `93276ac80`, 29749 Hz now), so the
margin was 9 Hz and it fell 1 Hz outside; the bound is now 650 Hz with a comment saying so.

### Proof that the test fails before the fix

`run_against_prefix.sh` builds `test_rms_estimator.c` with plain `cc` against
`firmware/components/power` as of `93276ac80` (git archive) and against the working tree. Output,
`prefix-vs-fixed.txt`: pre-fix aborts with `Assertion failed: (lo >= -TOL_PCT && hi <= TOL_PCT)` after
printing `-3.12 % .. +2.65 %`, exit 134; fixed passes, exit 0. The test uses designated initialisers so
it compiles against both headers.

## 2. Stuck-low plausibility

Rule (margin raised from 1.05 to 1.20 by the design lead after review, see below; `tank_rms_implausible()`, `tank_freq.c:10-14`; constants `tank_freq.h:102-104`):

    implausible  <=>  max|CT_MON| over the half >= 6 A   and   half RMS x (2.17 x 1.20) < max|CT_MON|      (threshold ratio 2.604)

Latch `N21_FAULT_RMS_CHANNEL` (the fault a failed MCP3202 or LM4040 reference read already takes, so it
inhibits the bridge through the same path as a lost CT_MON channel) when 6 consecutive closed halves are
implausible and the pads were live at every sample of each (`n21_binding.c:153-165`, `half_live`).
A half that fails to close neither counts nor clears.

### Crest bound 2.17, from code

* `tank_freq.h:75` `TANK_PEAK_PER_RMS 2.17f`, "round 6 board-side-protection.csv, 22 A row":
  `zapote/power-stage-120v/validation-results/05-resonant-tank-envelope/round6-full-power/outputs/board-side-protection.csv`
  line 2, `pk_over_rms = 2.17` (largest of 13 configurations at 22 A; 2.151, 2.131, 2.113, 2.096 at
  24-30 A, so it falls with current).
* The firmware already uses it as the healthy peak/RMS ratio twice: the peak trip `min(2.17 x ceiling + 3, 62)`
  (`tank_freq.c:8`) and the peak estimate `2.17 x half RMS` that feeds the loop (`n21_binding.c:175`).
  The check asserts the same ratio from the other side.
* 1.20 margin (first cut was 1.05): at the ADC phase-lock frequencies (40 kHz, k x 8.889 kHz, e.g.
  53.33 kHz) the CT_MON samples land on the same tank phases every half; near the crest, max|CT_MON| equals
  the true crest in all 6 halves. The study's synthetic crest is 2.30 at 50-55 kHz, which 2.28 would
  nuisance-latch. The check only has to catch gross failures (stuck at 0, half-scale reading: ratio >= 4),
  and 2.60 catches those with a wide margin. `max|CT_MON|` is a sample of the carrier, so it can only be
  below the true peak.
* **Caveat.** The study's synthetic series-RLC waveforms (not measured data, no ZVS ringing)
  reach a true peak/RMS of 2.30 at 50-55 kHz (`scatter.txt`, list at the bottom: 2.303, 2.301, 2.273),
  now inside the 2.60 threshold. Round 6 (the committed simulation the 2.17 comes from) does not reach it. If the bench shows a real ratio above
  2.60 on some pan, or above 2.17, then `TANK_PEAK_PER_RMS` is also too low for the peak estimate and must be raised;
  the plausibility margin should follow it, not be loosened on its own (COMMISSIONING Step 6 item 4
  has the bench measurement). Even then a latch needs six consecutive halves each sampling within 1 % of
  the true crest, and 13 slot samples per half rarely do.

### Debounce and floor

* **6 halves = 50 ms.** Burst edges are single halves (the first ON half, where the converter is still
  settling, and a half where the bridge starts or stops), always neighbours of plausible or idle halves,
  so they reset the count. A dead channel with the bridge running latches in 54 ms in the host model
  (test asserts 40-75 ms), inside the 100 ms regulation-overrun latch (12 halves) and long before any
  thermal consequence; the hardware CT/shunt trips and the firmware peak trip protect the interval.
* **`half_live`:** counted only if the pads were live at every sample of the half, so the half in which
  the bridge starts or stops (RMS averaged over the idle part, CT peak from the live part) never counts.
* **6 A floor** on `max|CT_MON|`: above the CT_MON offset/noise floor (2 LSB noise, `cos_phi_min_current_a`
  is 2 A) so an idle or tiny-current bridge cannot judge. A stuck channel at < 6 A of real current is
  not caught by this rule (the 4 A no-pan evidence is the frequency loop's job).
* Sensitivity: with crest 2.0 a channel reading more than about 23 % low (ratio above 2.60) is caught;
  one 10 % low is not (tested), that remains the Step 6.1 current-probe gate.

## 3. Bench-only shadow RMS (option C2)

* `components/power/rms_shadow.{h,c}`: pure. `rms_shadow_lock_metric(f, fs)` is the study's figure of
  merit `|mean exp(j 2 pi k f t_k)|`, k = 2, 4, 6 (weights 1, 0.3, 0.1), over the real CT_MON sample
  instants (slots 1 and 3 of the 9-slot pattern) of one 1/120 s window. `rms_shadow_select_fs()` picks
  the minimum over 64 clocks 80.000 .. 72.125 kS/s (VBUS keeps >= 24 kS/s). `rms_shadow_hold_fs()` keeps
  the clock in use while its figure is <= 0.02 (about 1 % RMS), because changing it restarts the ADC.
* **One deviation from the study:** the samples are weighted by `sin^2(pi t / half)` (the energy they
  carry under the line envelope). The envelope shifts the beat by +-120 Hz, a full cycle over the window,
  so the unweighted figure misses some bins: in the 481-bin scan below, one bin (48.6 kHz) had a 4.57 %
  error with the unweighted figure and the weighted one gives a worst bin of 0.53 %.
* Kconfig `TEMPER_POWER_SHADOW_RMS` (default **n**, depends on the HW binding). Off: nothing of it is
  compiled into the hardware layer. On: `n21_hw_esp32.c` accumulates sum of squares of the CT_MON
  samples per ADC frame, `hw_shadow_half()` (op `shadow_half`, called once per closed line half) returns
  the half's RMS and requests the next clock, `shadow_apply_clock()` stops, reconfigures and restarts the
  stream, and the acquisition task logs `tank rms: ad8436 .. A, shadow .. A (valid, adc .. S/s), f .. Hz`
  once a second. Also in `n21_telemetry_t.shadow_valid / shadow_rms_a / shadow_fs_hz`.
* **Never feeds a limit or trip.** The binding only stores the result in `tm.shadow_*` (`n21_binding.c`,
  next to `n21_half_begin` in `n21_acquire_step`); nothing reads it. Test: the binding is run for 2.5 s
  with the shadow returning 0 A, 22 A and 900 A; fault, `halves_ok/bad`, half RMS, inlet bound, ceiling
  power, frequency and loop reason are identical to the run without the op.
* **Known cost of the bench build** (stated in the Kconfig help and COMMISSIONING Step 6.1a): a clock
  re-selection stops the ADC1 stream for about a frame; a stale VBUS/CT_MON snapshot fails safe
  (inhibit), so this build can nuisance-inhibit on the bench. Half boundaries are taken at the ADC frame
  containing the LINE_ZC edge (<= 0.8 ms smear, < 0.2 % in RMS). Not run on hardware; HIL items:
  restart time, no lost frames, the reconfigure while the bridge runs.

Lock case, from `new-tests-output.txt` (22 A under the |sin| envelope, 12 pattern phases x 8 carrier
phases; error of the half RMS against truth):

| f | as-built 80 kS/s: figure, error | selected clock: figure, error |
|---|---|---|
| 40000 Hz | 1.400, -100.0 .. +41.5 % | 73625 S/s, 0.0000, -0.24 .. +0.13 % |
| 35555.6 Hz | 0.868, -50.4 .. +32.5 % | 76500 S/s, 0.0000, -0.12 .. +0.24 % |
| 44444.4 Hz | 0.868, -50.4 .. +32.5 % | 74000 S/s, 0.0000, -0.35 .. +0.38 % |
| 53333.3 Hz | 0.750, -24.9 .. +19.8 % | 76250 S/s, 0.0000, -0.28 .. +0.43 % |
| 26666.7 Hz | 0.750, -24.9 .. +19.8 % | 77125 S/s, 0.0000, -0.41 .. +0.29 % |

Scan 31-55 kHz in 50 Hz steps (481 bins, selected clock): worst error 0.53 % at 34500 Hz, 0 bins over 2 %.
The as-built numbers reproduce the study's finding 4 (-98 .. +42 %).

## Tests

New or changed, all in the host suite (`cmake -S firmware/test -B <dir>`; `ctest`):

| executable (ctest name) | new content |
|---|---|
| `test_rms_estimator` (`rms_estimator_tests`, **new suite**) | `test_slot_phase_scatter` (+-0.5 % over 3 half lengths x 25 phases x 3 amplitudes), `test_slot_phase_invariance` (5 us steps) |
| `test_rms_shadow` (`rms_shadow_tests`, **new suite**) | `test_clock_table`, `test_lock_case` (40 kHz and k x 8.889 kHz: as-built clock locked, selection avoids it), `test_scan` (481 bins, hold/reselect), `test_accumulator`, `test_telemetry_only` (binding unchanged by 0/22/900 A shadow, invalid shadow) |
| `test_n21_binding` (`n21_binding_tests`) | `test_rms_plausibility`: rule table; healthy sine (crest 2.0, 3 s); worst healthy crest 2.17 with every sample on the crest; 2.24, 2.34 and 2.55 pass, 2.70 latches (margin 1.20); the study's 2.30 crest with every sample locked on the crest runs 250 ms (30 halves) without latching; stuck-at-0 latches `N21_FAULT_RMS_CHANNEL` in 54 ms (40-75 ms asserted), inhibits, no auto reset; half-scale reading latches; 10 % low does not; 4-half excursion does not latch; 8 halves does; bursts 4/4, 2/2, 12/6 with half-scale edge halves do not latch; stuck inside a 12-half ON run latches; near resonance on the series-RLC fake (loop at 1.05 f_res, 24 A) does not latch and a stuck channel there does |
| `test_input_limits` (`input_limits_tests`) | `test_time_weights`: weighted RMS and power, scale invariance, all-zero = equal, zero weights drop out, negative/NaN/inf refused |

The fake HAL gained CT_MON that follows the tank (carrier crest, lock to crest), AD8436-only faults
(stuck, gain), and burst gating. Pre-existing initialisers of `input_sample_t` got the new field.

Stuck-low test sanity: with the latch condition disabled (threshold raised to 1e6 halves) the suite
aborts at the 2.70-crest assertion, i.e. the plausibility cases are not vacuous; they cannot be run on
`93276ac80` at all (no `tank_rms_implausible`, no CT-following fake).

Host suite: `ctest-summary.txt`, **31/31 passed** (was 29/29; +2 suites, +1 binding test, +1 input_limits
test, 9 more test functions overall).

## ESP-IDF build

`idf-build.txt`. ESP-IDF v5.3.6, `build-evidence/esp-idf/build.sh` (strict, BUILD_DIR outside the tree):
**exit 0**, `induction_cooker.bin` **410800 bytes** (was 410000 at `93276ac80`; `esp-idf/bin-size.txt`
updated; the other generated files in `esp-idf/` were not refreshed). With
`CONFIG_TEMPER_POWER_SHADOW_RMS=y` added (scratch fragment, not committed): exit 0, 417952 bytes, so
the bench path compiles.

## Rerun

    cmake -S firmware/test -B /tmp/fwhost && cmake --build /tmp/fwhost -j8 && ctest --test-dir /tmp/fwhost
    firmware/build-evidence/rms-estimator/run_against_prefix.sh
    # study-model numbers: see the header of study_model_scatter.py
    BUILD_DIR=/tmp/fwidf firmware/build-evidence/esp-idf/build.sh   # rewrites tracked esp-idf/*.txt; git checkout them after
