# LT4363-1 AUX surge-stopper prototype (round 15)

This is a concrete, bench-buildable candidate for the existing 15 V AUX
producer. It is not an electrical qualification and it is not integrated into
the 136-component circuit. The source contract used for the screen is:

* normal producer minimum 14.625 V and protected-load target 14.25 V;
* conditional protected load 114.473684 mA;
* a 35 V raw input fault is an engineering assumption, not an IRM guarantee;
* UCC27511A supply must remain below its 18 V recommended ceiling.

## Proposed path and pin connections

Use an LT4363-1 in the 12-pin DFN/MSOP pinout, with the exposed pad and both
ground pins returned to the HOT AUX return. The high-side path is:

| pin | net | connection |
|---:|---|---|
| 5 VCC | AUX_RAW | upstream of the sense resistor; 100 nF local bypass to GND |
| 3 SNS | AUX_SENSE | Q1 source through 0.33 ohm, 1%, Kelvin to pin |
| 2 OUT | AUX_PROTECTED | 0.33 ohm sense-resistor output, 47 uF minimum-effective downstream capacitor, load |
| 4 GATE | Q1 gate | 10 ohm gate stopper; no low-value gate pulldown |
| 1 FB | clamp sense | 58.3 kohm, 0.1% from OUT to FB; 4.99 kohm, 0.1% FB to GND |
| 12 TMR | timer | 10 nF, C0G or film, to GND; the data sheet minimum is 10 nF |
| 8 UV | startup enable | 91.0 kohm from AUX_RAW to UV and 10.0 kohm UV to GND |
| 6 SHDN | hardware inhibit | open-drain fault/reset latch pulls low; otherwise use the LT4363 internal pull-up |
| 10 FLT | fault status | buffer into the logic-domain fault input; do not wire directly to the existing 10 kohm/5 V reset net |
| 11 ENOUT | optional status | leave unused or buffer; it is not a safety input |
| 7,9,13 GND | HOT_AUX_RETURN | short, low-inductance return |

Q1 is an Infineon/International Rectifier IRLR2908TRPBF (80 V DPAK N-channel)
as the initial reference device. Drain is AUX_RAW and source is AUX_SENSE;
the 0.33 ohm resistor then runs from AUX_SENSE to AUX_PROTECTED/OUT. Add a
220 nF gate capacitor and the Figure 5 series-resistor/diode network with the
diode orientation copied exactly from the vendor schematic (cathode at the
capacitor node). This follows the LT4363 Figure 5
gate-compensation topology. The gate capacitor is deliberately provisional:
it reduces self-enhancement for input edges faster than 5 V/us, but slows
turn-off and must be measured.

SHDN is a hardware path. The reset/interlock/watchdog latch must pull it low
independently of a frozen command decoder. A separate slew-control buffer is
required if the measured internal-pull-up release edge does not meet the
10 V/ms minimum. The 100 us low-time requirement
applies after the timer/cool-down state is complete; it is not a substitute for
the required cool-down interval.

## Static corners and current limit

With VFB=1.25--1.30 V, IFB=+/-1 uA, and independent 0.1% resistor errors, the
58.3 kohm/4.99 kohm divider gives 15.766787--16.577142 V. The minimum is above
the 15.75 V normal high-side corner, avoiding continuous normal clamp
regulation; the upper corner is below 18 V with 1.423 V of static headroom.
This is not a bound on transient overshoot. The UV divider starts at about
12.9 V, so the 14.625 V normal minimum does not sit on the UV corner.

The 0.33 ohm sense resistor gives 135.014--168.350 mA from the specified
45--55 mV current-limit range. The data sheet also lists 58 mV maximum at
48 V; treating that value as applicable at 35 V would expand the conditional
upper limit to 177.7 mA, so it is not silently interpolated or called a
guarantee. The normal-load sense drop is 38.154 mV at
the high resistance corner, leaving 336.846 mV of the 375 mV normal drop
budget before switch, wiring, or connector losses. That budget is tight and
must be measured with the complete load.

The 220 nF gate capacitor is also a startup-load choice: using the data-sheet
worst listed 65 uA gate pull-up current as a screening value, the Figure 5
inrush relation gives about 13.9 mA into 47 uF. Added to 114.47 mA this is
about 128.4 mA, below the 135.0 mA conditional minimum current limit. This
does not cover buck startup foldback, isolation receiver inrush or capacitor
tolerance; those remain bench acceptance inputs. The bypass diode is needed
to avoid turning this startup-friendly capacitor into an unbounded fault
turn-off delay.

At the assumed 35 V fault, using the conservative high current-limit corner
and the high static clamp corner gives about 3.203 W in Q1 while the limiter
is active. A hard output short invokes the 25 mV severe-short limit, about
76.5 mA at the low resistance corner. These are arithmetic bounds from the
LT4363 sense specifications, not measured waveforms.

## Timer, charge and SOA screen

CTMR=10 nF is the data-sheet minimum loop-compensation value. The data sheet
specifies a voltage-dependent timer, not a single maximum turn-off time. For
reference only, 0.875 V of timer charge at the 35 uA typical 10 VDS current
would be 250 us; at the actual 35 V-to-~16 V event the current is higher and
the timer is shorter. This typical calculation cannot be used as a guarantee.

Choose a 47 uF capacitor downstream of the sense resistor with a documented assembled minimum
effective capacitance of at least 35 uF over tolerance, DC bias, temperature
and aging. At 168.35 mA, 250 us would add 1.203 V by charge alone, giving
17.177 V from the high static clamp. The 250 us value is illustrative; the
acceptance test must use the measured worst-case timer and source waveform.

The IRLR2908 primary data sheet specifies 80 V VDS, 28 mOhm maximum RDS(on) at
10 V, 33 nC maximum total gate charge, 30 A package-limited current, 120 W
maximum dissipation at case temperature, 1.3 C/W RthetaJC, and a plotted
maximum SOA (not a tabulated guaranteed 20 V/0.17 A pulse limit). At 35 V raw
and a 16.58 V clamp, Q1 sees about 18.42 VDS and 0.168 A, or 3.10 W. If the
limiter persisted 250 us, P2t is about 0.00240 W2s. A shorted output sees
approximately 35 VDS and 0.0765 A, or 2.68 W. These figures are screening
points only: the exact measured VDS/ID/time trajectory must be overlaid on the
vendor SOA graph at the starting case temperature, and the timer must be
selected only after that comparison. A MOSFET failure-short fault is also an
independent protection case and is not covered by this controller.

## Required acceptance tests before adoption

1. Measure the complete AUX load at 14.625 V, including the new limiter,
   isolation receiver and driver; verify OUT remains at least 14.25 V and the
   sense drop plus wiring remains within 375 mV.
2. Use a current-limited isolated source to apply measured 24.6 V and the
   explicitly assumed 35 V step, with both fast and slow rise times. Capture
   raw input, SNS, OUT at the UCC27511A pins, gate, SHDN, FLT and current with
   differential probes. Establish Qnet/Ceff and require Vpeak<18 V.
3. Verify LT4363 timer turn-off and the IRLR2908 VDS/ID trajectory over
   tolerance and temperature against the primary SOA plot; do not substitute
   integrated energy for SOA.
4. Verify hardware SHDN capture with a frozen decoder, an open-drain default
   low fault, and a fault that returns high before the timer expires. Verify
   reset low >=100 us only after cool-down and a >=10 V/ms release slew.
5. Inject Q1 drain-source short and gate-open faults. The architecture must
   expose these as unqualified failure modes or add a separate downstream
   overvoltage cutoff before any production claim.

Primary references: Analog Devices LT4363 Rev C, pp. 1--3, 7--15;
Infineon/International Rectifier IRLR2908PbF data sheet, pp. 1--4; and the
existing interface-physical-14 AUX report and load audit.
