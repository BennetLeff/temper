# Independently supplied F6: preferred circuit development proposal

This implements the separate positive/negative supply arrangement in TI
SLUSE89C §8.2.2.9, Figs.8-2/8-3, pp.34–35. It preserves approximately +15 V
at turn-on and establishes negative voltage without prior switching. It is
an engineering proposal with explicit startup protection, **not a qualified
replacement for D6's ideal sources**. Both variants still need circuit
transients, startup/fault testing and extraction after routing.

## Supply and channel connections

Use four **R15C2T25/R-R** modules, one per MOSFET, programmed to approximately
+15/−6 V. Post-regulate the negative rail with **TPS7A3001DGNR** to −2 V or
−4 V. This avoids the insufficient corner headroom of an unregulated −5 V
module feeding a −4 V LDO. Separate low-side modules share `leg_ret` as their
source reference; their output rails are never paralleled. Four modules
keep the 80 kHz sizing case below each module's continuous power limit;
a single common low-side module would serve twice the calculated load.

Replace **PS2 IRM-05-15** with **IRM-20-15** in its correct larger footprint.
Retain its input connections `n_filt`/`tco_l` and output `leg_ret`/`v15_ls`;
do not move the supply to PS1, which bypasses the existing TCO power cut.
PS1 and all other existing PS2 loads remain connected. Remove bootstrap
**D1/D2 UF4007**. Do not fit the passive Zener or series blocking capacitor.

For channel Q2/Q3/Q5/Q6, define `P_Q`, `NRAW_Q`, `N_Q`, and `SRC_Q`:

| Channel | SRC_Q | Driver VDD → P_Q | Driver VSS → N_Q | Existing OUT/Rg |
|---|---|---|---|---|
| Q2 | sw_a | U1.16 | U1.14 | U1.15/R10.1 |
| Q3 | leg_ret | U1.11 | U1.9 | U1.10/R12.1 |
| Q5 | sw_b | U2.16 | U2.14 | U2.15/R18.1 |
| Q6 | leg_ret | U2.11 | U2.9 | U2.10/R20.1 |

Disconnect only these driver supply pins and their local bypass returns
from the previous supply/source nets. Keep MOSFET source pins, existing
10 kΩ gate-source resistors and power-current copper on SRC_Q. Reconnect
existing C8/C9, C10/C11, C15/C16, C17/C18 across their channel's P_Q/N_Q.
These capacitors now span about 17/19 V, within their 50 V rating. Preserve
OUT-to-3.9 Ω-to-gate. Add 1 nF Cgs at each MOSFET; for −2 V only, add the
same PMEG6030EP,115/1 Ω fast-discharge branch described in README, but its
resistor terminates at **OUT**, not a passive Shift net.

For each RECOM module (datasheet pin table p.13): pins 6/7 connect to
`v15_ls`; primary PGND pins connect to `leg_ret`; CTRL pin 4 connects to
existing `hot5` (U3.1), not SELV `v3v3`. PG pin 3 receives a 10 kΩ pullup to
`hot5` and a diagnostic test point only. Its low-when-good output is **not**
wired across the isolation barrier. Pins 28/29 form P_Q; all VOUT− pins
form NRAW_Q. FBCOM pin 35 is the quiet NRAW_Q feedback return. Pin 32 COM
connects through 261 Ω to SRC_Q; pin 33 senses the SRC_Q divider separately.

Program total voltage using P_Q → 49.9 kΩ → 31.6 kΩ → pin 34 → 11 kΩ →
NRAW_Q. Program the negative magnitude with SRC_Q → 69.8 kΩ → pin 33 →
49.9 kΩ → NRAW_Q. All are Yageo RT0603BRD07…L, 0.1%, 25 ppm/°C. The
worksheet gives 21.022727 V total, −5.996994 V raw and +15.025733 V positive.
Put 330 pF at each feedback input to FBCOM and at AVIN to PGND.

Add, per module, three parallel 10 µF capacitors at its primary input;
10 µF plus 100 nF across P_Q/NRAW_Q; 10 µF across P_Q/SRC_Q; five parallel
10 µF across SRC_Q/NRAW_Q; and 100 nF primary bypass. All 10 µF additions
use the sourced UMK325AB7106KM-T. The 5:1 split-capacitor ratio gives 3.024
under independent tolerance/X7R extremes before DC-bias effects, versus the
calculated minimum 2.756. Actual biased capacitance must meet that ratio,
input minimum and LDO stability minimum; nominal capacitance is not proof.
The 261 Ω COM resistor is below the approximately 337 Ω result of RECOM's
p.7 dual-output formula at 50 µF (including its 30 Ω internal term).

TPS7A3001 pins: IN8/EN5 to NRAW_Q, OUT1 to N_Q, GND4/thermal pad to SRC_Q,
FB2 between OUT and SRC_Q dividers; leave DNC7, NC3 and NR/SS6 open. Use
10 kΩ FB-to-SRC_Q and 6.98 kΩ OUT-to-FB for −1.996848 V, or 23.7 kΩ for
−3.963120 V. Add 10 µF from N_Q to SRC_Q and 1 kΩ preload across it. The
−4 V variant is **−3.963 V nominal**, not an exact −4.000 V source. Re-run
its actual tolerance corners. Even with a −1.5% raw-rail scenario and
+2.7% regulated magnitude, both variants retain more than 1 V headroom.
TI's ±2.5% accuracy excludes external-divider errors; 2.7% is only a sizing
allowance. The driver spans are 17.0226/18.9889 V, below 25 V.

## Bias-ready hardware, including the isolation crossing

Per channel, use **LM339BIDR** powered between P_Q and N_Q and
**TL431AIDBZR** with anode N_Q and REF tied to cathode `REF_Q`. Bias REF_Q
from P_Q through 2.2 kΩ 1206. Divide REF_Q by two equal 10 kΩ resistors to
`HALFREF_Q` (nominal 1.2475 V above N_Q). Four comparator outputs join at
`GOOD_Q`; they sink whenever any of four rail-window tests fails. Two tests
sense SRC_Q−N_Q (bias magnitude); two sense P_Q−N_Q (driver span).

Each sense divider has 10 kΩ bottom to N_Q. Its top value, and resulting
nominal thresholds, are in the worksheet. UV comparators have sense at +,
HALFREF at −; OV comparators reverse those inputs.

| Variant | Bias UV/OV top resistors | Span UV/OV top resistors |
|---|---|---|
| −2 V | 4.42 kΩ / 7.62 kΩ | 120 kΩ / 133 kΩ |
| −4 V | 18.7 kΩ / 25.3 kΩ | 137 kΩ / 147 kΩ |

Pull GOOD_Q toward REF_Q through 1 kΩ. From GOOD_Q connect a 1N4148W-7-F
(anode GOOD_Q) to the base of MMBT3904-7-F; add 10 kΩ base-emitter and tie
emitter to N_Q. Its collector sinks the cathode of a VO617A-3X017T LED;
LED anode connects through 2.7 kΩ 1206 to P_Q. The series silicon diode
prevents the comparator's possible 0.55 V low output from directly driving
the NPN. LED current is approximately 5–6 mA when all windows pass. There
is no deliberate capacitor across TL431; its capacitive-stability region
must be respected if filtering is added later.

On the **SELV** side, each optocoupler emitter connects to `selv_gnd` and
collector `BAD_Q` has a 10 kΩ pullup to `v3v3`. Dark/unpowered bias therefore
requests disable. Two SN74LVC32APWR packages (v3v3/selv_gnd, each with
100 nF bypass) provide the OR tree:

```
BAD_ALL = BAD_Q2 OR BAD_Q3 OR BAD_Q5 OR BAD_Q6
D12_DIS_A = existing leg_a-dis OR BAD_ALL
D12_DIS_B = existing leg_b-dis OR BAD_ALL
```

Disconnect only U1.5 and U2.5 from the old DIS nets; connect to D12_DIS_A/B,
each with its own 10 kΩ pullup. R8/Q1 and R16/Q4 stay on the original nets,
which now drive OR inputs. Tie unused logic inputs to selv_gnd and leave
unused outputs open. No push-pull output is wire-ANDed with another output.
This retains existing disable requests and adds a hardware bias prerequisite.
It does not use the converter's primary PG signal as a post-LDO rail-good
claim and does not directly connect HOT ground to SELV.

**Qualification still required:** tolerance/temperature window trip points,
reference/logic brownout sequencing, optocoupler CTR and dv/dt immunity,
startup with every supply order, no false GOOD pulse, brownout detection
before bias leaves the allowed range, and disable response with a charged
bus. LM339BIDR/TL431AI limit this prototype monitor to −40…85 °C ambient.
MOSFET junction at 150 °C does not permit these parts to operate at 150 °C.
The nominal thresholds specify a circuit to test; they do not establish a
safety-certified or single-fault-tolerant interlock.

## Supply power, duty and startup

No bootstrap is retained, so neither rail needs a low-side refresh pulse or
minimum switching duty. Negative bias can exist before PWM and during a
long disabled interval. The actual first permitted pulse is gated by the
local window monitors, rather than a delay guessed from a typical startup
time. A device can still fail to start if its capacitor ratio or load is
wrong; that must leave DIS asserted in qualification.

`isolated_bias.py` uses 400 nC Qg (a scenario, not a bound), actual 1 nF
swing, 4.4 mA driver allowance, 15 mA monitor allowance, full positive Rgs
current, negative preload and 1 mA regulator allowance. It conservatively
charges these loads against the full raw module span. At 36 kHz it gives
7.27/7.65 W from the primary supply at assumed 45% efficiency, or
9.35/9.84 W at a 35% sensitivity case. At 80 kHz these rise to
10.70/11.10 W or 13.76/14.27 W. Module outputs remain 1.204/1.248 W or less
in these scenarios. The 21 W replacement PS2 leaves 6.73 W for other
loads even in the larger 35% case **before temperature/input derating**.
Existing PS2's 5 W is inadequate for these modeled loads.

RECOM's +100 mA main output and −12 mA COM-path rating must not be confused:
the gate-charge cycle transfers charge between main rails with reservoir
capacitors; its full Qg×f is not a net DC load on the midpoint. The estimated
DC midpoint imbalance includes the 2/4 mA output preload, regulator ground
current, divider currents and Rgs duty imbalance; require its magnitude
below 12 mA, and verify burst/startup behavior against the manufacturer's
COM-control model. No blanket 12 mA gate-current pass is asserted. Two
low-side channels on one module exceed 1.5 W in the 80 kHz scenario, so
this proposal uses four modules despite only three source-reference domains.

The negative LDO heat estimate peaks at 0.235 W (−2 V) or 0.127 W (−4 V)
at 80 kHz. Module dissipation and monitor heat need copper/airflow design;
45% is a typical efficiency, not a lower bound. At the larger 80 kHz
load, module heat is about 1.53 W at 45% and 2.32 W at 35% efficiency.
The latter exceeds the datasheet’s 1.7 W power-dissipation characteristic;
output-power sizing alone does not establish thermal feasibility at 80 kHz. IRM-20-15 is 15 V ±2.5%,
1.4 A/21 W before derating, within RECOM's 13.5–18 V input range in normal
operation. Its 17.25–20.25 V OVP range does not guarantee remaining below
RECOM's 18 V operating maximum during a supply fault. Its longer hold-up
and input inrush also require rechecking the existing TCO/permit response.

## Parts, estimate, geometry and source locations

[isolated_bias.json](isolated_bias.json) contains the complete per-variant
MPN/quantity list and calculations; [isolated_prices.csv](isolated_prices.csv)
records the dated price basis. Material purchase is approximately **$119 for
−2 V** and **$115 for −4 V**, including the replacement PS2 and interlock,
before credit for removed PS2/D1/D2, PCB/assembly and qualification. This is
an unoptimized prototype, about 215/207 purchased parts. Precision/power
resistors use explicitly marked family-price estimates, not fabricated
individual quotes. The 10 µF price uses the conservative quantity-one
observation despite a larger purchase. The NRND/non-preferred capacitor
and backordered TPS7A3001 are sourcing risks; no immediate complete kit is
claimed. Optimize only after the rail/startup model is established.

New return rails, bypass capacitors, discharge branch and Cgs change each
leg's extracted geometry. Rerun both leg FEMs after routing. A planning
allowance of 10–25 mm added local gate-return/supply copper per channel at
0.5 mm width gives 20–50 mm² for four channels, excluding pads/planes;
this is not measured inductance. The four modules also need about
4×12.83×7.5 = 385 mm² body area, before monitor circuits and clearance.
PS2's larger 52.4×27.2×24 mm body changes primary-side placement/creepage.
Board-wide DRC, primary isolation and thermal review accompany that change;
a value-only FEM exemption does not apply to F6.

Manufacturer sources (accessed 2026-10-02):

- [RECOM R15C2T25/R Rev.1-2024](https://recom-power.com/pdf/Econoline/R15C2T25_R.pdf): pp.1–3 ratings/continuous derating/regulation; pp.4–7 equations, startup capacitance and PG/COM; pp.12–13 footprint/pins. 36-SSOP, 13.5–18 V input, 15–25 V total output, 1.5 W continuous to 90 °C under its specified thermal conditions; 2.5 W only for 5 seconds. 1.4 kVDC working isolation, 150 kV/µs CMTI. Ratings are not proof of the proposed layout.
- [TI TPS7A30 SBVS125D](https://www.ti.com/lit/ds/symlink/tps7a30.pdf): pp.4–7 pins, −35…−3 V operating input, 200 mA, ±2.5% accuracy with at least 1 V input headroom, 0.6 V maximum dropout at 200 mA, 2.2 µF minimum output; pp.17–19 feedback/thermal guidance. DGN 8-HVSSOP, junction −40…125 °C.
- [Mean Well IRM-20 specification, 2025-11-21](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF): pp.1–2 ratings, protections, derating and footprint. IRM-20-15 is 21 W despite the family name.
- [TI LM339 Rev.Z](https://www.ti.com/lit/ds/symlink/lm339.pdf): pp.3–7 pins/electrical limits; 2–36 V supply, SOIC-14, LM339BI ambient −40…85 °C. Inputs are near 1.25 V above its negative rail, within common-mode range once powered.
- [TI TL431 Rev.S](https://www.ti.com/lit/ds/symlink/tl431.pdf): pin configuration and electrical tables for TL431AI, SOT23 DBZ; 2.495 V nominal/1% reference, up to 36 V, −40…85 °C; stability plots govern optional cathode capacitance.
- [Vishay VO617A](https://www.vishay.com/docs/83430/vo617a.pdf): pp.1–4 ordering/limits/CTR/switching and pp.7–9 package. Group 3 CTR 100–200% at 5 mA, 80 V transistor, SMD-4. Its 5.3 kVrms test rating is not the PCB working-voltage rating or a guaranteed CMTI figure.
- [TI SN74LVC32A Rev.U](https://www.ti.com/lit/ds/symlink/sn74lvc32a.pdf): pp.3–7 pins/electrical limits; TSSOP-14, 1.65–3.6 V supply. Operates from existing SELV 3.3 V.
- [Diodes MMBT3904 data](https://www.diodes.com/datasheet/download/MMBT3904.pdf) and [1N4148W data](https://www.diodes.com/datasheet/download/1N4148W.pdf): DS30036 Rev.27-2 pp.1–3 and DS30086 Rev.31-2 pp.1–2 respectively; SOT23 NPN and SOD123 series diode. Neither is in the gate-discharge power path; PMEG6030EP remains the separately rated power diode.
- Capacitor and RT/RC resistor family ratings are in [SOURCES.md](SOURCES.md); 330 pF uses the same C0G family (50 V, ±5%, 0603), and 100 nF uses existing C0603C104K5RACTU ([Kemet X7R family, pp.1–4](https://content.kemet.com/datasheets/KEM_C1002_X7R_SMD.pdf)) (50 V, ±10%, X7R, 0603). RT dividers are 0.1%/25 ppm/°C/0.1 W; 1206 load/LED resistors are 1%/0.25 W with power derating.
