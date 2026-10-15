# temper-aux-load-r1: how much of the inlet aux allowance is real?

2026-10-15. Every number below comes from `aux_load.py` → `aux-load.json`
(`python3 aux_load.py`, about 2 s). Sources were read only: the power-stage
DECISIONS 16, 47 and 50, `ALT-BIAS.md`, `blower_aux.c`, the controller's
`verify.json` (controller-layout 300b8a934), and the MEAN WELL MPM-20 and MPM-65
datasheets (2024-10-30). Nothing in hardware, firmware or worktrees was edited.

## Answer

The firmware reserves **1.35 A** of the 13.5 A inlet target for auxiliaries
with the blower off, **1.93 A** at blower drive 0.5 and **2.57 A** at full
speed. Measured as the increase in total inlet RMS, the auxiliaries actually
add **0.10–0.33 A typically and 0.25–0.88 A at the worst corner.** That frees
**1.1–1.7 A of inlet current at the worst corner**: the power-stage hold rises
by 1.0–1.5 A, worth about **+120 to +184 W input at 120 V**, only where the
inlet limit binds.

| Case | Aux output W (PS2 / PS3) | Aux RMS | Linear sum of module RMS | **RMS increment** | Firmware allowance | Hold now → possible | ΔP at 120 V |
|---|---|---|---|---|---|---|---|
| typical, blower off | 7.7 / 2.0 | 0.38 A | 0.44 A | **0.10 A** | 1.35 A | 11.05 → 12.18 A | +136 W |
| typical, drive 0.5 | 7.7 / 10.3 | 0.60 A | 0.67 A | **0.19 A** | 1.93 A | 10.52 → 12.10 A | +190 W |
| typical, full | 7.7 / 22.9 | 0.95 A | 0.98 A | **0.33 A** | 2.57 A | 9.94 → 11.98 A | +245 W |
| worst, blower off | 11.6 / 4.8 | 0.59 A | 0.71 A | **0.25 A** | 1.35 A | 11.05 → 12.04 A | +120 W |
| worst, drive 0.5 | 11.6 / 20.6 | 1.04 A | 1.15 A | **0.50 A** | 1.93 A | 10.52 → 11.82 A | +156 W |
| worst, full | 11.6 / 44.6 | 1.68 A | 1.71 A | **0.88 A** | 2.57 A | 9.94 → 11.47 A | +184 W |

The corners are:

- **Typical:** 120 V; PS2 at the 40 kHz allocation; logic estimated from
  datasheet typical draws; blower at its typical power.
- **Worst:** 108 V; PS2 at the 80 kHz allocation; logic at datasheet maximum
  (4.83 W); blower at its maximum power (32.4 W at 12 V, fan law, 0.9 buck);
  efficiency 5 points under typical; power-stage current with 20 % in-phase
  3rd harmonic. The worst calibration variant is kept.

The worst/full case across line voltage gives increments of 0.88 / 0.80 /
0.73 A at 108 / 120 / 132 V.

## Why the allowance is so far off

1. **It adds RMS figures linearly.** The power stage draws a near-sinusoidal,
   in-phase current (PF ≈ 1 on the unsmoothed bus). The auxiliaries' peaky
   current adds to the total RMS mostly through its real-power part P_in/V.
   Its harmonics are orthogonal and add only (I_rms² − I₁²)/(2·I_ps), about
   0.05 A. The linear sum of RMS figures is a bound, not an estimate.
2. **It uses full-load datasheet currents.** The MPM figures (0.75 A and
   1.5 A typical at 115 V) imply PF 0.29 and 0.41 at rated load. A
   capacitor-input model sized from the datasheet hold-up time reaches only
   0.38–0.40 A and 1.02–1.16 A, so the figures are conservative even for
   module RMS. This study inflates each module's harmonic content to match
   the datasheet figure (×2.2–2.5 for PS2, ×1.4–1.8 for PS3) and still finds
   the increments above.
3. **It is stale.** `blower_aux.c` `base_a = 1.3 A` is "PS1 + PS2, both IRM-20
   at full load", but s38 deleted PS1. The logic now rides on PS3 through the
   J13 merge, which the PS3 model, written for the blower only, does not
   count. PS2 and PS3 are now MPM parts. Every one of these errors is in the
   conservative direction except the uncounted logic (≤ 4.8 W), and the
   1.3 A base covers that many times over.

## Caveats (read before claiming the gain)

- **The gain only exists where the inlet limit binds.** Pans held by the tank
  current ceiling (22 A shipped) gain nothing.
- **A higher hold raises bus current through R5 and C40.** The s41 still-air
  ceilings are laminate 22.3 A and laminate plus film 21.1 A (C40 limits),
  from power-stage DECISIONS 53. The B3 c22 cases must be shown to cover the
  higher inlet hold before it is adopted. This study does not check that.
- **The loads are allocations, not measurements.**
  - PS2's 7.45–11.1 W is the ALT-BIAS budget (740 nC edge allowance, 45 %
    module efficiency).
  - The typical logic figure (1.98 W) uses ESP32-S3 DS v2.2 Tables 5-7 and
    5-9 and the OLED at 30 % of its 310 mA typical. That is an estimate.
- **Some inputs are assumptions:**
  - MEAN WELL publishes no minimum efficiency or maximum input current, so
    the worst corner uses typical − 5 points.
  - The 20 % third harmonic in the power-stage current is an assumed bound;
    native-21's input current has not been measured.
- **Adopting this changes firmware constants only.** A bench check would
  prove it: true-RMS inlet current against I_ps,est·(1 + e) + I_aux,new at
  108 / 120 / 132 V over blower off / mid / full. That fits the existing
  e_est bench qualification. An AMC1301 on R5 (coil-driver-r1 item 2)
  measures I_ps only, not the auxiliaries, so on its own it does not remove
  the aux allowance.
