# Buck Rev A — measurement definitions

Exact stimulus, capture, and calculation rules behind [BRINGUP.md](BRINGUP.md).
Source: `harness-lab/audits/buck-20260910-followup/requirements-proposal.md` as updated by
`harness-lab/engineering/scenarios/lmr51430-datasheet/` and
`harness-lab/audits/buck-final-20260910/full-scenario-readiness/README.md`,
against limits in `harness-lab/engineering/requirements.json`.
The current requirements/scenario definitions override older prose on startup load compliance.
All limits are adopted project targets, not measured hardware or manufacturer guarantees.

## Startup (formal comparison)

- Precondition: VIN and VOUT below 50 mV; EN tied to VIN.
- Apply a measured monotonic 0-to-selected-VIN ramp of **1 ms**.
- t0 = actual **13.5 V** crossing of VIN. Capture a pretrigger interval through **t0+20 ms**.
- Final VOUT = mean from **t0+15 ms to t0+20 ms**.
- Rise = t90−t10 relative to that final level. Target: **≤8 ms**.
- Settling: within **±1 % of final** by **t0+10 ms**, remaining there through t0+20 ms.
- Overshoot: **≤100 mV** above final and **never above 3.465 V** (absolute bound takes precedence).
- Lower regulation bound (3.135 V) applies after settling, not while starting from zero.
- Run at 15 V first, then 13.5/16.5 V, at **0 A and 0.5 A** specified load.
- 0.5 A-point load law (fixture stimulus, not an IC property):
  `Iload = 0.5 A × clamp(VOUT / 0.1 V, 0, 1)`, with 2 % rated-current tolerance.
  Ordinary loads often cannot draw 0.5 A at 0.1 V — check actual compliance and measured
  current before asserting protocol equivalence. Normal bench-supply turn-on and resistor
  loads are useful smoke tests but do not satisfy the formal ramp/compliance protocol.
- Do not build a new load instrument just to complete documentation; mark unmet
  protocol points NOT RUN/INDETERMINATE instead.

## Load steps and pulses

- Slew: **0.1 A/µs ±10 %**. Expected edge durations: **4.5 µs** for 0.05→0.50 A,
  **9.5 µs** for 0.05→1.00 A. Confirm current plateaus within **±2 %**.
- Pattern: hold low load ≥100 ms, rise, hold high **10 ms**, fall; three high pulses
  per operating point with starts **≥100 ms apart** (start-to-start) and ≥100 ms
  initial/final low holds. Evaluate rising **and** falling edges.
- Vpre = mean over the last 1 ms before each edge. Vfinal = mean over the stable late
  plateau (last 1 ms before the next edge, or last 1 ms of the ≥100 ms capture after the
  final falling edge). Record actual averaging windows; an unsettled window is INDETERMINATE.
- Per-edge targets: departure **≤100 mV from Vpre** AND absolute **3.135–3.465 V**;
  recovery to within **±1 % of Vfinal** within **1 ms after the edge ends**, remaining
  there for the applicable plateau.
- 0.05↔0.50 A steps: 15 V first, then input corners. 0.05↔1.00 A pulses: same order,
  three pulses per point.

## Ripple

- Probe **directly across C11 or C12 output-capacitor terminals** with a short return;
  identify the selected capacitor in the record. TP3/TP4 may substitute only if their
  placement gives the same local pickup without significant extra loop.
- **20 MHz bandwidth limit, ≥100 MS/s**, steady 100 ms record at light/DC load so
  burst-mode (PFM) envelopes are included — do not crop to a quiet switching cycle.
- Target: **≤50 mVpp** across the full steady window (max peak-to-peak, not a subwindow).
- Separate 1 A plateau ripple (using the available 10 ms plateau) from load-edge excursion.
- Report probe method, bandwidth, sample rate, window, and raw extrema. Distinguish
  input-supply ripple from output ripple. There is **no adopted 125 mV input-ripple
  closure threshold**.

## Temperature and efficiency

- At 0.5 A per VIN: observe until drift is **<1 °C over 10 minutes**, then record a
  further **10 s** window. Ending earlier yields a timed observation, not equilibrium.
- Measure **U3 case and L2 surface** with placement/emissivity documented. Case ≠ junction:
  no direct conversion without a defensible method. Full qualification targets U3 junction
  ≤125 °C and L2 hotspot ≤105 °C at 0.5 A through 70 °C ambient — a room-temperature
  screen cannot demonstrate this.
- Efficiency: measure input/output power **at the board terminals** (VIN×IIN, VOUT×IOUT)
  with synchronized or steady readings; document meter burden and uncertainty.
  The **≥80 % (0.1 A) / ≥85 % (0.5 A)** thresholds apply at the adopted **25 °C** condition
  — record measured ambient for every comparison, and mark the comparison NOT RUN or
  INDETERMINATE if 25 °C cannot be established (retain the observed efficiency).

## Uncertainty and status rules

- Upper-bound checks use measured value **plus** stated expanded uncertainty;
  lower-bound checks use measured value **minus** it. Time, voltage, current, efficiency,
  and temperature each need their own uncertainty budget.
- Missing bandwidth, timing resolution, calibration, or a stable final window makes the
  measurement **INDETERMINATE**, not a pass. The ±1 % settling band is in volts
  (0.01 × Vfinal), not an untyped percentage of a sample.
- Statuses: `PASS` / `FAIL` / `NOT RUN` / `INDETERMINATE`. Leave measured cells empty
  until measured. Do not fill templates with model outputs as though they were bench data.
