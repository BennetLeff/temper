# Buck Rev A — first-power and operating-point runbook

**Status: procedure only. No board has been powered; no test has passed.**
Verify every connector pin and test point against the final assembly drawing
before energizing. Figures (`images/connector-probe-map-provisional.svg`,
`images/bench-wiring-provisional.svg`) are **PROVISIONAL** until bound to the
board freeze (`pcb/prototypes/buck-reva/verification/board-freeze.md`).

Board at planning: standalone 15 V-to-3.3 V buck (LMR51430, U3), inductor L2,
output capacitors C11/C12. Operating connection: **J1.1 VIN / J1.2 GND** input,
**J2.1 3V3 / J2.2 GND** output. Board VIN at **TP1/TP2**, VOUT at **TP3/TP4**.
See [equipment.md](equipment.md) for the bench setup and [measurement-definitions.md](measurement-definitions.md)
for exact stimulus/capture math. Record everything in [results-template.csv](results-template.csv)
and [run-record-template.md](run-record-template.md).

## 1. Pre-power inspection (supply disconnected)

1. Inspect populated MPNs, U3 orientation, solder bridges, inductor seating,
   connector polarity, and test points against the assembly drawing.
2. Check ground continuity and input/output-to-ground resistance. Capacitors make
   resistance change with time — a continuity beep alone is not a short test.
3. Discharge all rails before reconnecting anything.
4. Place the board on a stable insulating support. Attach the (disabled) load and
   scope probes with power off.
5. Set the temperature stop threshold **before** power: stop at **80 °C measured
   U3 case or L2 surface**, or sooner on rapid unexplained heating. This is a
   protective bench threshold, not a manufacturer rating and not evidence the
   junction is safe. Confirm sensor placement and uncertainty; room-temperature
   observation cannot close the 70 °C-ambient requirement.

## 2. First power — no load

1. Set the supply to **15 V** with an initial input current limit of **0.10 A**.
   This is a conservative diagnostic setting, not an IC specification.
2. Energize with no output load.
3. Confirm VOUT settles within **3.135–3.465 V**, the supply stays in voltage
   regulation, and nothing heats abnormally.
4. If the supply current-limits: disconnect, investigate wiring/shorts/startup
   charging first. **Do not keep raising the limit until a suspect board appears
   to work.** A supply in current limit invalidates any converter-performance result.

## 3. Staged DC loads at 15 V

1. Set a recorded input limit of initially **0.30 A**.
2. Step the output load through **0.05 → 0.10 → 0.25 → 0.50 A**. At each step record
   actual board VIN, VOUT, IIN, IOUT.
3. Repeat the stable checks at **13.5 V** and **16.5 V** input.
4. Resistors can cover these staged DC loads but **cannot** reproduce the specified
   constant-current startup/pulse protocol — do not claim protocol equivalence.

## 4. Ripple and temperature at stable 0.5 A

1. With stable 0.5 A operation established, measure output ripple per
   [measurement-definitions.md](measurement-definitions.md) (C11/C12 terminals,
   20 MHz, ≥100 MS/s, 100 ms window so the PFM envelope is retained).
2. Observe U3 case and L2 surface temperature over time at each VIN.
   Report a timed observation unless drift is <1 °C over 10 minutes followed by a
   10 s measurement window. Do not convert case temperature to junction temperature
   without a defensible method.

## 5. 1 A / 10 ms pulses (only after §4 passes)

1. An initial **0.50 A** input current limit is a practical test-setup allowance,
   not a guaranteed consumption or output rating. Record actual settings and supply behavior.
2. Run the 0.05↔1.00 A pulse protocol (three 10 ms pulses per point, slew 0.1 A/µs).
   Verify **measured load current** achieves the commanded slew and plateau —
   a front-panel setting alone is not evidence.
3. Evaluate ripple on the 1 A plateau separately from the load-edge excursion.

## 6. Shutdown and rework rule

1. Disable the supply, discharge and verify rails, photograph/record any assembly changes.
2. A component rework creates a **new assembly identity**: repeat all affected tests.

## Stop immediately — remove power — on any of:

Reversed polarity · persistent short · smoke/odor · unexpected current limiting ·
output above 3.465 V · rail collapse · sustained instability · abnormal heating.
Preserve captures/settings, diagnose before retrying. **A failed test never justifies
changing the acceptance limit.**

## Operating-point matrix (targets; all NOT RUN until measured)

| Check | Points | Target |
|---|---|---|
| DC regulation | 13.5/15/16.5 V × 0/0.05/0.10/0.25/0.50 A | 3.135–3.465 V; record current + board VIN |
| Startup | 15 V, then 13.5/16.5 V, at 0 and 0.5 A | Rise ≤8 ms; overshoot ≤100 mV and never >3.465 V; settled by 10 ms |
| Load step | 0.05↔0.50 A, 15 V then corners | Departure ≤100 mV from pre-edge; absolute band; recovery ≤1 ms |
| Pulse | 0.05↔1.00 A, 10 ms plateau, 15 V then corners | Same voltage/recovery targets; 3 pulses per point |
| Ripple | 0/0.05/0.50 A per VIN; 1 A plateau separately | ≤50 mVpp at 20 MHz, PFM envelope retained |
| Thermal screen | 0.50 A per VIN | Timed observation; protective stop per §1 |
| Efficiency | 0.10 and 0.50 A per VIN | Record VIN×IIN, VOUT×IOUT; ≥80%/≥85% only at 25 °C |

If an instrument cannot reproduce a required stimulus or capture, run a clearly labeled
exploratory check where useful and mark the exact target **NOT RUN** or **INDETERMINATE**.
Documentation can be complete while physical verification is incomplete — never call
verification complete with mandatory points missing.
