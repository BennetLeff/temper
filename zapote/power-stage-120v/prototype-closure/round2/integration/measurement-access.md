# Round 2 measurement access on native19

Read-only `pcbnew` inventory of board SHA-256
`3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.
Coordinates are board coordinates in millimetres. These are **candidate electrical
contacts**, not a checked probe fixture or permission to energize a board. The
current [probe study](../../../native-19/verification/probe-access.json) records
19 signals but does not check full tip/copper containment, mask aperture,
nearby hardware, fixture tolerance, or actual probe ratings.

| Measurement | Native19 connection and coordinate | What this exposes | Additional acceptance before use |
| --- | --- | --- | --- |
| Input current and voltage | J1.1 `AC_L_IN` (6.70,150.455); J1.2 `AC_N_IN` (6.70,155.535), both through-hole | Input terminals. Measure current on a selected, enclosed upstream single-conductor route rather than treating a two-conductor cord clamp as line current. | Selected inlet/cord/strain relief and current sensor; instrument isolation, category/range and protection reviewed for the actual station. Connector pin identity checked on purchased part. |
| Raw local DC bus at C5 | C5.1/.2 `BUS_P` (13.0,43.95)/(13.0,64.25); C5.3/.4 `HV_RET` (50.5,43.95)/(50.5,64.25), through-hole | Rectified-bus transient near one film capacitor, including passive charging while gates are disabled. | Rated fixed differential fixture and guarded attachment; tip/copper/mask containment, discharge, lead inductance and enclosure clearance checked. This pair is **not** the shunt's `LEG_RET`/Kelvin pair. |
| Raw local DC bus at C6 | C6.1/.2 `BUS_P` (174.35,50.75)/(194.65,50.75); C6.3/.4 `HV_RET` (174.35,13.25)/(194.65,13.25), through-hole | Second local capacitor position for comparing distributed bus voltage. | Same as C5; cooling, insulation and protective tray must leave deliberate fixture access or nominate another real pair. |
| Isolated controller bus feedback | J4.11 `VBUS_P` (118.5,67.08), J4.12 `VBUS_N` (121.5,67.08), both SELV connector pins | The isolated sense channel the controller sees. | Verify channel gain/bandwidth/phase and common-mode validity against selected AMC1311 circuit and calibration; **do not substitute** this for a raw high-frequency bus capture without that evidence. |
| Protection outputs and inhibit | J4.10 `BUS_FAULT` (115.5,67.08), J4.9 `PERMIT` (112.5,67.08), J4.2 `SELV_GND` (115.5,64.08) | Compare fault signaling, interlock command and resulting turn-off with separate gate/bus/tank records. | Mating breakout and controller-side latch revision pinned; output polarity, rail-loss state, timestamp alignment and connector loading verified. |
| Current sense | R5.2 `OCP_KELVIN_P` (125.23,9.17); R5.3 `OCP_KELVIN_N` (127.77,16.03) | Loaded four-terminal shunt differential. | Dedicated differential measurement; no probe ground tie across terminals. Quantify measurement loading and Kelvin reference error against actual current. |

The names, pad nets and locations above came directly from the saved board's
footprints/pads, not from the historical netlist alias field. `pcbnew` reports
mask-layer membership for these pads; that is weaker than proving the intended
contact disc lies inside real copper and the actual mask opening after the
installed fixture is modeled. The joined cooling CAD must preserve a workable
service state for the selected contacts. If the successor board changes any
pad, route, mask, connector or enclosure feature, rerun this inventory on its
saved hash and retire this table as historical.

For D22, record line current, raw bus, controller bus feedback, command power,
and input phase on a common clock. For D17, include `PERMIT`, `BUS_FAULT`,
actual gate voltage at device pins, shunt current and raw bus/tank waveforms.
A passive line/rectifier charging transient can occur with every gate disabled;
the turn-off experiment therefore cannot equate gate-disable with removal of
stored bus energy. The qualified station owner sets probe and fixture ratings,
guards, energy limits, power sequence and discharge verification before use.
