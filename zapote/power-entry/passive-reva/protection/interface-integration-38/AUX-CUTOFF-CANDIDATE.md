# Rev38 protected AUX cutoff candidate

Status: **joined, compiled and exact-pin audited engineering candidate; electrical acceptance OPEN**. [`AuxCutoff38`](elec/src/aux_cutoff.ato) is the sole joined route from `AUX15_PRECUT` to `AUX_PROTECTED`. Its output feeds the driver, PFC control, detectors, relay, and [`HotLogic5Converter38`](elec/src/hot_logic5_converter.ato). This file records the component and static screens; it does not certify a protected 15 V output, MOSFET SOA, or a fault-response time.

The [startup and cutoff corner ledger](AUX-STARTUP-CORNER.md) adds a
selected-shunt TCR screen, simultaneous-current feasibility inequality,
and exact missing input owners. Its illustrative 0.386 A residual is not a
qualified startup load allowance.

## Selected circuit and reset behavior

The candidate uses [ADI LTC4368HMS-2#PBF](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf), the 10-pin MSOP `-2` reverse-current variant. VIN pin 1 and SHDN pin 6 receive `AUX15_PRECUT`. GND pin 5 and RETRY pin 4 return to `HOT0`. UV pin 2 and OV pin 3 each have an independent divider. GATE pin 10 drives the common gates of [onsemi FDS3992](https://www.onsemi.com/download/data-sheet/pdf/fds3992-d.pdf): pins 7/8 form upstream D1, pins 2/4 are the common sources, and pins 5/6 form downstream D2. The sense resistor lies between SENSE pin 9 and VOUT pin 8. FDS3992's two 100 V N-channel devices are in one SOIC-8; the cited pin assignment is from its package drawing. FAULT pin 7 is unconnected in this candidate; the separate protected-output window detector owns the HOT fault input.

The [ADI application circuit and guidance](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf) use a 22 kΩ resistor between GATE and the inrush capacitor. Rev38 uses 22 kΩ and 10 nF from the resistor's far side to `HOT0`, while both FET gates join GATE directly. The capacitor is active [Murata GRM188R72A103KA01D](https://www.murata.com/en-us/products/productdetail?partno=GRM188R72A103KA01D), 10 nF ±10%, 100 V X7R, 0603. The former 50 V `GRM188R71H103KA01D` was marked obsolete by a distributor and has been removed from this candidate. The 4.7 µF nominal VOUT capacitor is `GCM31CC71H475KA03L`; ADI requires at least 1 µF *effective* at VOUT, so its DC-bias and hot/cold effective value still need verification.

RETRY tied to GND selects **latch-off after forward overcurrent**. ADI says SHDN must be driven low then high to clear that latch. SHDN is tied to VIN here, so no separate reset command exists. A source power-cycle reset must be verified with the chosen converter's discharge and brownout waveforms; no automatic retry is assumed. UV/OV faults instead recover after their thresholds and the controller's 32 ms turn-on delay. A current fault during valid startup must not be treated as a successful start.

| Component | Exact MPN | Function and unresolved check |
| --- | --- | --- |
| Controller | `LTC4368HMS-2#PBF` | OV/UV, reverse and forward-current controller; authorized stock and actual MSOP land pattern to verify |
| Back-to-back FETs | `FDS3992` | 100 V dual N-MOS; hot linear SOA, gate voltage, turn-off and package thermal path OPEN |
| Shunt | `WSL2512R0500FTA` | 50 mΩ ±1% nominal selection; Kelvin routing and temperature/lifetime tolerance OPEN |
| UV top/bottom | `TNPU060320K0AWEN00` / `TNPU0603806RAZEN00` | 20 kΩ / 806 Ω; exact-part procurement for 806 Ω OPEN |
| OV top/bottom | `TNPU060320K0AWEN00` / `TNPU0603590RAZEN00` | 20 kΩ / 590 Ω; exact-part procurement for 590 Ω OPEN |
| GATE resistor/capacitor | `RC0603FR-0722KL` / `GRM188R72A103KA01D` | 22 kΩ / 10 nF; gate-cap effective value and fault turn-off OPEN |
| VOUT ceramic | `GCM31CC71H475KA03L` | 4.7 µF nominal; at least 1 µF effective at VOUT OPEN |

## Static window and current screens

The [LTC4368 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf) gives OV rising 492.5–507.5 mV, OV hysteresis 20–32 mV, UV falling 492.5–507.5 mV, UV hysteresis 20–32 mV, and ±10 nA threshold-input leakage at its stated fixture. The [Vishay TNPU sheet](https://www.vishay.com/docs/28779/tnpue3.pdf) supplies the candidate precision grades and a ±0.3% rated-power resistance-change limit after 225,000 h. This screen adds initial tolerance, an illustrative 100 K change from the 25 °C reference, and that entire life limit independently and adversely: 20 kΩ top `t=0.05% + 2 ppm/K × 100 K + 0.30% = 0.37%`; 590 Ω or 806 Ω bottom `t=0.05% + 5 ppm/K × 100 K + 0.30% = 0.40%`. Treating the opposite drift signs as possible is conservative; the service temperature and power conditions have not yet been qualified.

For each threshold, evaluate `V = Vpin × (1 + Rtop/Rbottom) ± 10 nA × Rtop` at the independently adverse resistor endpoints. The resulting **algebraic** values are:

| Event | Computed endpoint | Relation to current review window |
| --- | ---: | --- |
| OV lowest falling recovery | 15.95075 V | 200.75 mV above 15.75 V normal high |
| OV highest rising trip | 17.84409 V | 155.91 mV below provisional 18.0 V screen |
| UV lowest falling trip | 12.61942 V | 1.631 V below 14.25 V normal low |
| UV highest falling trip | 13.19811 V | 1.052 V below 14.25 V normal low |
| UV highest rising recovery | 14.03029 V | 219.71 mV below 14.25 V normal low |

These values do not include PCB leakage, divider self-heating, noise, actual source ripple, FET drop, fast fault overshoot, or detector limits. The 18.0 V upper bound is a *provisional screening value*, not a qualified UCC27624 VDD peak limit. The minimum 15 V buck feedback-only screen is 14.6378 V *before* the cutoff path. At 1.0 A, two FETs at the FDS3992's 0.123 Ω maximum specified at its 150 °C test condition, plus a nominal 50.5 mΩ high-corner shunt, imply about 0.297 V drop and only 14.341 V at the protected output. This is a conditional arithmetic screen, not a bounded board drop or a proven 1 A operating point; source ripple, PCB loss and actual gate drive can consume the remaining 91 mV. The full load and path-temperature budget must set the usable current.

ADI specifies 40–60 mV forward sense threshold at `VOUT = VIN` and 30–70 mV in its `VIN = 12 V`, `VOUT = 0 V` fixture. With only the ±1% initial 50 mΩ shunt tolerance, those become **0.792–1.212 A** and **0.594–1.414 A**, respectively. Shunt TCR, self-heating, age, parasitic sense voltage and comparator response are not included. The `-2` designation changes the reverse-current threshold, not these forward thresholds. Neither screen qualifies the 21.6 W IRM-20-24 or the 15 V buck as overload-protected.

The joined protected rail has **30.6 µF nominal direct capacitance**: driver 4.8 µF, PFC control 1.0 µF, logic5 buck VIN 20.1 µF, and cutoff VOUT 4.7 µF. The [ADI inrush relation](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf) `Iinrush = COUT × IGATE(UP) / CGATE` gives 183.6 mA using 30.6 µF, 60 µA maximum gate-up current and *nominal* 10 nF. This is **not a maximum**, because CGATE effective minimum, capacitance maxima, active load, source ramp and FET gate dynamics are missing. At nominal values the direct-bank charge to 15 V is 459 µC, and the ideal half-`C V²` charge loss is 3.44 mJ, mainly in the series pass path. Actual FET energy and peak power depend on the waveform and on other starting loads. The HOT logic5 buck output adds a separate 46.5 µF nominal 5 V bank, whose charging current appears upstream through the buck with an efficiency- and timing-dependent profile.

The most restrictive published forward-trip fixture is 30 mV minimum with
`VIN = 12 V, VOUT = 0 V`. With the selected shunt's 1% initial high corner,
that is the conditional **0.594 A** threshold above. Subtracting the
**nominal** 0.184 A direct-bank inrush screen leaves only **0.410 A** for
simultaneous active startup before this fixture's minimum threshold. That
subtraction is a feasibility question, not a guaranteed margin: the source
is 15 V, the two capacitance corners are unknown, and the 5 V buck, relay,
PFC and driver startup currents may overlap. ADI's own reference Figure 7
uses FDS3992 with different 24 V/100 µF/20 mΩ conditions; it supports this
as a candidate device pairing, not the Rev38 FET's linear SOA at its actual
waveforms.

## Decision worksheet for the joined load

For each intended cold, warm, partially charged and repeated-start state,
record the maximum *simultaneous* upstream current through the shunt. The
candidate can proceed to a native review only if an evidence-backed lower
trip threshold exceeds the highest valid-start current with a stated margin.
The relevant test is the complete waveform, not separate peaks added from
incompatible operating states.

| Gate | Quantities to record on the joined article | Review condition |
| --- | --- | --- |
| Valid startup | Effective `C_AUX` maximum, effective `C_GATE` minimum, 5 V buck input current during its output-bank charge, relay/PFC/driver overlap, shunt tolerance and temperature | `I_valid_start_peak + margin < I_OC_forward_min` at the applicable LTC4368 fixture, with no nuisance latch, supply hiccup or rail-good chatter. |
| Steady run | State-by-state direct AUX and 5 V loads, buck input power/efficiency, cutoff controller current and path drop at the hot part temperature | Protected VDD and logic5 stay in their accepted windows while each converter and shunt remain inside their qualified current/thermal limits. |
| Cold cutoff FET | Simultaneous `VDS(t)` and `ID(t)` on each FDS3992 die during every startup, fault and restart; pulse spacing, case/board temperatures and copper area | Compare each trajectory and accumulated heating with manufacturer SOA/transient thermal data for the *actual* board. The 3.44 mJ ideal charge loss is not this trajectory. |
| Fast overvoltage | Pre-cutoff VIN, both FET terminals/gates, `AUX_PROTECTED`, UCC27624 VDD, HOT logic5 and retained-clear/driver EN | Derive the highest protected pin voltage, response time and stored-energy path. Compare with the separately accepted driver and rail limits; the 18 V screen alone is not that limit. |
| Overcurrent and restart | Shunt Kelvin differential, gate discharge, FET current, VIN/SHDN and VOUT through short, overload, source dip and recovery | Show latch-off on forward overcurrent and a controlled reset policy; tying SHDN to VIN makes converter discharge/brownout part of reset behavior. |

[ADI's LTC4368 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf)
requires at least 1 µF at VOUT and states that valid-start inrush plus output
load must stay below the forward threshold. Its 8 µs fault example and the
TPS54202's 5 ms *typical* soft start are not worst-case board response
limits. Record source, scope/probe uncertainty, raw traces and article identity
using [`bench-capture.md`](bench-capture.md); all worksheet rows are **NOT RUN**.

## Required physical evidence before acceptance

1. Measure `AUX15_PRECUT`, `AUX_PROTECTED`, FET GATE/source/drain, shunt differential voltage and current, and UCC27624 VDD during cold/warm/partially discharged starts, relay pickup, PFC startup, logic5 load steps and mains dips. Derive the combined valid-start current and no-chatter margin at voltage and temperature corners.
2. Establish a real maximum `AUX15_PRECUT` waveform under buck-feedback open/short, raw-source overshoot, regulator failure and surge. Measure the highest driver VDD peak and time to disconnect. Include FET gate discharge with the installed 10 nF network; ADI's fast-turnoff limit uses a different test capacitor and is not a bound for this board.
3. Inject downstream short, overload and reverse-current faults. Measure current peak, FET turn-off, shunt temperature, latch behavior, VIN cycling and partial-power reset. Check FDS3992's time-dependent linear SOA and the PCB thermal path against every start/restart/fault energy.
4. Verify effective capacitance versus DC bias, temperature and aging, exact FET/shunt/divider procurement, footprint land patterns, Kelvin sense routing, and source-to-native netlist parity. Review the actual assembled board before promoting this circuit to U4/U7 PASS.

The standalone and joined Atopile netlists compile. `audit.rs` checks exact part identity from the generated CSV BOM, each controller/FET/shunt/divider/gate pin, preservation of internal nets, the sole pre-cutoff-to-protected join, and logic5 input downstream of cutoff. Deliberate sense bypass, gate open, UV/OV swap, cutoff bypass and logic5 pre-cutoff feed mutations fail. All physical captures are **NOT RUN**.
