# Reference revision 09: fuse coordination boundary

**Status: selected parts, coordination open, hardware unverified.** This is a
source review bound to the retained passive Rev A topology and to
`5dde29ab3e2f1223c2d33c129ced2cf647238307`. It makes the fault loops and the
manufacturer data reviewable; it does not authorize an energized test and
does not claim that either fuse has cleared a Temper fault.

The canonical source places Schurter F1 (link `0034.3129` in holder
`0031.2510`) in AC_L before the common-mode choke. The proposed F2 is a
normally closed, off-board Mersen `A70QS50-14F` in an Mersen `US141`, item
`Z331153`, between diode-side `VD` and bank-side `VB`. F2 is not in the
canonical CAD/BOM. The operating-matrix campaign models a healthy closed F2
and an ideal scripted opening; it does not model a fuse element, arc, or
clearing law.

## What the manufacturer data actually binds

### F1: Schurter 0034.3129 and 0031.2510

The Schurter FST 5x20 primary datasheet identifies the family as a 250 Vac,
time-lag T, low-breaking-capacity glass fuse (PDF p. 1). The `0034.3129` row
(PDF p. 4) is **16 A, 250 Vac**, with breaking-capacity footnote `2` and a
typical **melting I²t of 1,638 A²s at 10×In**. Footnote `2` is explicitly
**10×In at 250 Vac** (PDF p. 4), so it is a 160 A AC test condition for this
link, not a DC interrupt rating and not a total-clearing bound for a mains
fault.

For the 8–20 A group (which includes 16 A), the pre-arcing table (PDF p. 3)
states: 1.5×In minimum 30 min; 2.1×In maximum 120 s; 2.75×In 600 ms
minimum/10 s maximum; 4×In 150 ms minimum/3 s maximum; 10×In 20 ms
minimum/300 ms maximum. These are **pre-arcing** limits. They do not include
the arc, current-zero behavior, or total clearing time.

The exact FUP `0031.2510` holder product page gives a PCB, solder-THT,
shock-safe holder for 5×20 mm links: 500 Vac VDE / 600 V UL-CSA, 16 A VDE /
30 A UL-CSA, and 4 W IEC power acceptance at 16 A and Ta 23 °C. It is an
installation/thermal constraint, not an interrupting capability. Ambient
derating, copper pattern, holder temperature, and source prospective current
remain to be established.

**F1 decision:** the part and holder are selected in the existing baseline,
but F1 line-fault coordination is **unmodeled and unverified**. No source
impedance or prospective fault-current measurement is retained, and the
Schurter document supplies no total-clearing I²t or DC data. Do not infer a
clearing time from 1,638 A²s or from the 20–300 ms pre-arcing band.

### F2: Mersen A70QS50-14F

Mersen’s 2024 *High Speed Fuses* catalogue, A70QS French Cylindrical section
(PDF **HS 20**, p. 20), states 14×51/22×58 A70QS links are 690 Vac IEC,
700 Vdc general-rated, with **100 kA dc interrupting at a 10 ms time
constant**, and additionally have an **890 Vdc capacitor-discharge rating up
to a 2.5 ms time constant**. The same page describes 700 Vdc general
protection as `L/R ≤ 10 ms`; it does **not** define the 2.5 ms
capacitor-discharge condition as `L/R`, nor publish its test circuit or
waveform definition. That definition remains a manufacturer question.

The A70QS ratings/application table (HS 21, p. 21) gives the exact
`A70QS50-14F` row: 50 A, 14×51 mm, **melting I²t 0.28×10³ = 280 A²s**,
**maximum clearing I²t 1.50×10³ = 1,500 A²s at 700 Vac**, and 11.6 W at
rated current. The 1,500 A²s value is an **AC 700 Vac** clearing number; it
cannot be substituted for 890 Vdc capacitor-discharge let-through.

The A70QS table has no minimum-breaking-current (MBC) column and no
capacitor-discharge-specific total-clearing I²t or let-through curve. The
100 kA dc figure is qualified by the general 700 Vdc test condition and
time constant, not by the 890 Vdc capacitor-discharge statement. The 2.5 ms
phrase does **not** establish that the capacitor waveform's time constant is
`L/R`; its test circuit and waveform definition are not published in the
retained sheet. Therefore
the following remain unknown for Temper’s bank loop:

* maximum peak current and arc-voltage behavior allowed for Temper's
  nominal 390 V bank and its still-unbounded fault waveform under the
  890 Vdc-rated application;
* minimum breaking current at that voltage/time-constant condition; and
* total clearing I²t or a let-through-current curve for the capacitor
  discharge.

### F2 holder: Mersen US141 / Z331153

The retained Mersen US14 datasheet identifies **US141 / Z331153** as a
single-pole 14×51 holder (PDF p. 2) and gives, for the US14 family, UL
ratings of 800 Vac, 50 A, 50 kA and 1000 Vdc, 50 A, 50 kA (PDF p. 3), with
50 A conventional free-air thermal current, 5 W dissipation at `Ith`, IP20,
8 kV impulse withstand, and AC20B/DC20B utilisation. The same sheet gives
temperature and side-by-side derating factors and says the holder is for
**no-load** operation. The US141 product record confirms the exact item
number and one-pole design.

Those are holder ratings and installation conditions. They do not establish
that the A70QS link interrupts the board’s capacitor energy, nor do they
bound terminal/cable inductance, contact heating, enclosure spacing, or
interconnect withstand.

## Fault-loop coverage

The table keeps source-fed, bank-fed, and local-reservoir paths separate. A
row marked “selected” is a part choice; “modeled” means only the retained
authored/ideal model state; “verified” requires a manufacturer application
bound or a controlled hardware result. No row below is coordination-closed.

| Named path | Device state / source | Fuse that can be in the path | Selected | Modeled in retained evidence | Verified / current boundary |
| --- | --- | --- | --- | --- | --- |
| `AC_L → F1 → CMC → bridge → Lboost → U9 → PFC_BUS_MINUS` | Source-fed failed MOS: U9 held failed-short (or conducting after gate-off); F2 may be healthy or open | **F1 only**. F2 is downstream of VD/VB and cannot interrupt the line-fed inductor path. K1 only bypasses the NTC. | F1 link + FUP holder existing baseline | Source/inductor traces and failed-switch diagnostics exist; the authored SPICE source includes an assumed 0.25 Ω source element, but no validated physical prospective-current measurement and no F1 element/arc law | **Not coordinated.** Missing physical source impedance/prospective current, F1 total-clearing I²t/arc data, and U9/bridge SOA. A gate-low command is not credited with interrupting a failed channel. |
| `Cbank+ → F2 → U10 → a1 → U9 → bank−` | Bank-fed diode + MOS short: U10 failed-short and U9 failed-short | **F2 only** in the intended topology; F1 and U12 are outside this loop | A70QS50-14F + US141/Z331153 candidate | Healthy closed F2 and ideal scripted F2-open state; stored-bank path identified in campaign report | **Not coordinated.** 890 Vdc/2.5 ms applicability, MBC, capacitor-discharge total-clearing I²t, peak/arc limits, and bank/copper/device withstand are missing. |
| `Cbank+ → F2 → U10 → a1 → U9 → bank−` | U10 failed-short, U9 healthy but conducting during detector/driver delay | F2 is backup; U9 may be commanded off, subject to detector/driver latency and U9 turn-off SOA | Same F2 selection | Detector timing is modeled (DIODE-SHORT is 3.121 ms after injection, outside the unchanged 2 ms window); F2 action itself is ideal | **Not verified.** Healthy-U9 gate-off timing/survival and F2 clearing are unbounded; do not turn detector timing into a fuse result. A gate-independent actuator is not claimed for this healthy-U9 state. |
| `Clocal(VD)+ → U10_failed_short/diode terminal → U9_conducting → HOT0` | Local diode-side capacitor outside F2; **both U10 is failed-short (or reverse conduction is separately proven) and U9 is conducting/failed-short** | **Neither F1 nor F2 is credited.** F2 is on the VD-to-VB boundary, while `Clocal` is upstream of it | No local treatment selected | Campaign identifies `Clocal` as a separate reservoir and observes VD; BYPASS-NEG demonstrates a local-VD overvoltage failure | **Uncovered.** Choose a bounded local-energy treatment (capacitor/semiconductor withstand, controlled discharge/clamp, or a qualified interrupter), with bounded capacitance/ESR/ESL and device/arc/SOA withstand. Opening F2 cannot clear energy already on VD. |
| `Clocal(VD)+ → healthy reverse-biased U10 → switch node` | U9 MOS short alone; U10 healthy boost diode | No fuse receives credit | No local treatment selected | Topology review says the healthy boost diode blocks VD-to-SW discharge | **Not a discharge path under this state.** Do not count MOS-short-alone as a bank/local-capacitor discharge; the diode short (or separately demonstrated reverse conduction) is a required state. |
| `Cbank` after F2 opens | Residual charged bank, discharged bank, or unequal VD/VB residual states | No fuse is a discharge path after opening | F2 open is a proposed state, not a safety state | Open-state and restart interlock are requirements; equality of VD/VB is not continuity proof | **Unverified.** A separate, rated discharge and residual-voltage interlock are required. |
| Reference D2/inrush bypass path (if adopted later) | D2 forward path can bypass Lboost/MOS-controlled conversion path | F1 may remain upstream, but old F1/F2 evidence does not transfer to the changed graph | Not selected in canonical Rev A | Explicitly absent from current `cold.cir`; reference deviation only | **Out of scope until redrawn.** Adoption requires a new fault graph and new line/bank/local path analysis. |

## Selection, model, verification status

| Item | Selected | Modeled | Verified |
| --- | --- | --- | --- |
| F1 `0034.3129` + `0031.2510` | Existing baseline identity | Resistance/NTC/source behavior only; no fuse law | No line-fault coordination or hardware interrupt result |
| F2 `A70QS50-14F` + `US141/Z331153` | Candidate location and exact parts | Healthy closed path and ideal opening witness only | No 890 Vdc capacitor-discharge application closure, clearing, or assembly withstand |
| Independent local-VD treatment | Not selected | Not modeled | Bounded withstand, discharge/clamp, or qualified interrupter remains open for `Clocal` coverage |
| Source prospective impedance and F1 arc | SPICE assumes 0.25 Ω source element | Not a physical prospective-current model | Physical source impedance, F1 arc and total-clearing data remain required |

## Smallest meaningful next check

The highest-value next step is a **manufacturer application-data closure**,
not a broad solver sweep: ask Mersen to state, for Temper's nominal 390 V
bank and a subsequently bounded fault waveform under the A70QS 890 Vdc
capacitor-discharge rating, the
applicable peak-current limit, MBC, and total
clearing I²t/let-through curve, including whether the capacitor-discharge
rating has a particular waveform, test circuit, or time-constant definition.
The bulk capacitors are rated 450 V; the authored 500 V simulation screen is
not a permitted bank operating point or an established maximum fault voltage.
In parallel, measure or
otherwise source-bound the AC line prospective impedance at the F1 location;
the Schurter pre-arcing table cannot supply it.

Once those values exist, the smallest useful model witness is a reduced
source-fed/bank-fed/local-reservoir matrix with U9 and U10 states held
explicitly, F2 represented first as healthy/open for topology separation, and
separate traces for line current, F2 current, VD, VB, `Clocal` and `Cbank`.
That witness can test whether the declared source and energy bounds cover all
three paths. It must not invent fuse clearing time, ideal disconnect behavior,
SOA, or arc energy. Coordination by analysis requires applicable manufacturer
limits and bounded fault/withstand envelopes; it remains open here. A controlled
hardware fault test on the exact holder, interconnect and capacitors is a
separate later step for `HardwareVerified`.

## Evidence boundary

The retained campaign reports support topology and model-state distinctions,
including that source-fed `Lboost` current is distinct from bank discharge,
that `Clocal` is a separate reservoir, and that F2 is an ideal scripted
opening. They do not supply manufacturer fuse physics or hardware survival.
The current honest disposition is therefore:

* F1: **selected, uncoordinated, unverified** (the 0.25 Ω SPICE source is an
  authored assumption, not a physical prospective-current bound);
* F2 and US141: **selected candidate, conditionally screened, uncoordinated,
  unverified**; and
* local VD and residual-bank handling: **open requirements**.

No coordination closure is claimed by this revision.
