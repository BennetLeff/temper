# Rev38 protected AUX startup and cutoff corner ledger

Status: **digital feasibility screen; U4 electrical and physical acceptance OPEN**.
This ledger uses the joined `source-build-06` circuit: IRM-20-24 →
LMR36015BRNXT → `AUX15_PRECUT` → LTC4368HMS-2/FDS3992/50 mΩ →
`AUX_PROTECTED` → TPS54202DDCR → `HOT_LOGIC5`. The selected pin and
component connections are in [`elec/src/aux_cutoff.ato`](elec/src/aux_cutoff.ato),
[`elec/src/hot15_converter.ato`](elec/src/hot15_converter.ato), and
[`elec/src/hot_logic5_converter.ato`](elec/src/hot_logic5_converter.ato).
`AUX-CUTOFF-CANDIDATE.md` contains the static threshold screen. This
ledger adds startup conditions and the inputs that prevent those thresholds
from becoming accepted operating limits. The inspected
`source-build-06/build/default.net` SHA-256 is
`913a0bf51726cb756af2384aea3ac2c949c405f612b345aedbae7ef4c0d79796`.

## A conditional simultaneous-current test

The [LTC4368 Rev. C datasheet, electrical characteristics and inrush
guidance](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf)
specifies 30 mV minimum forward trip in its **VIN = 12 V, VOUT = 0 V**
fixture, 40 mV minimum at VOUT = 0.5 V or VOUT = VIN, and 20–60 µA
GATE pull-up current in its 12 V fixture. Its approximate capacitive-inrush
relation is `I_C ≈ C_OUT × I_GATE(UP) / C_GATE`; ADI explicitly requires
`I_inrush + I_load < I_forward_trip` during startup. The Rev38 fixture is
about 15 V and has a 22 kΩ resistor between GATE and its 10 nF capacitor;
the data-sheet relation is a sizing screen, not a guaranteed Rev38 waveform.

The selected [Vishay WSL sheet, technical specifications](https://www.vishay.com/docs/30100/wsl.pdf)
gives the WSL2512 50 mΩ value a ±75 ppm/°C **component** TCR, including
terminals. Combine the selected `F` code's ±1% initial tolerance with an
illustrative adverse **100 K shift from 25 °C**. This is a mathematical
hot-restart screen, not a measured shunt temperature or lifetime bound:

```text
R_sense,max = 50 mΩ × 1.01 × (1 + 75 ppm/K × 100 K) = 50.87875 mΩ
I_trip,min = 30 mV / R_sense,max = 0.58964 A  [12 V / 0 V fixture only]

C_gate,min,initial = 10 nF × 0.90 = 9 nF  [initial tolerance only]
I_direct_cap,screen = 30.6 µF × 60 µA / 9 nF = 0.204 A
I_other,remaining = 0.58964 − 0.204 = 0.38564 A
```

The **30.6 µF is nominal** direct protected-rail capacitance: 4.7 µF
cutoff VOUT, 20.1 µF logic5 buck VIN, 4.8 µF driver and 1.0 µF PFC.
The 9 nF floor includes only the gate-cap initial ±10% marking. The
effective minimum at actual gate voltage, temperature and age is unknown;
the direct-bank effective maximum and the current of active loads are
also unknown. Therefore **0.386 A is not a permissible load or accepted
startup margin**. It is a prompt to measure all terms simultaneously.

An equivalent design test, once compatible bounds exist, is:

```text
I_other,peak + (C_AUX,effective,max × I_GATE,max / C_GATE,effective,min)
    + I_measurement_margin < I_trip,applicable,min
```

For orientation only, with the *same incomplete 12 V/0 V fixture screen*,
9 nF gate cap and 60 µA gate current, `C_AUX` must be below 88.45 µF
even if `I_other=0`, or below 43.45 µF if `I_other=0.30 A`. Those
figures do not specify a capacitor allowance. Actual gate behavior,
capacitance, startup overlap, shunt temperature and the applicable LTC
comparator fixture must be settled first. The gate capacitor also slows
the FET's linear startup trajectory, so reducing inrush alone cannot
establish FDS3992 SOA.

The 50 mΩ shunt's full selected-part operating range is not captured by
the previous initial-tolerance calculation. Under the same illustrative
100 K opposite-sign TCR corner, its minimum resistance is 49.12875 mΩ;
the data-sheet's **70 mV maximum** 12 V/0 V fixture would correspond to
1.42483 A. This wide conditional trip interval is a circuit-breaker
screen, not upstream source protection. The [IRM-20 manufacturer
sheet](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF) rates
IRM-20-24 at 21.6 W/0.9 A under its conditions. Even an ideal 24-to-15 V
conversion would cap 15 V output at 1.44 A before installed derating or
other loss; `I_15V,max ≤ P_IRM,available × η_15 / 15 V`. The LMR36015's
1.5 A device rating and TPS54202's 2 A rating cannot be used as source
current allocations.

## Startup order and stored energy

The [LMR36015 sheet](https://www.ti.com/lit/ds/symlink/lmr36015.pdf)
specifies **3–6 ms internal soft-start** under its stated test conditions;
the [TPS54202 sheet](https://www.ti.com/lit/ds/symlink/tps54202.pdf)
lists **5 ms typical** soft-start, without a worst-case bound. The
LTC4368 turn-on delay is 22–45 ms in its 12 V fixture, before the
unbounded Rev38 output slew. These intervals cannot simply be added to
derive a guaranteed command-ready time. The IRM startup, 44 µF nominal
pre-cutoff bank, 30.6 µF nominal protected bank, 46.5 µF nominal 5 V bank,
active 15 V/5 V loads and rail-good thresholds interact. Starting with
the 5 V output prebiased, with a partly charged AUX bank, or immediately
after a mains dip changes the waveforms. Capture all three rails and shunt
current on one timebase.

The direct 30.6 µF protected bank stores `½ C V² = 3.4425 mJ` at 15 V
using nominal capacitance. This is *not* an FDS3992 SOA verdict: each
die's `V_DS(t) × I_D(t)` and repeated-pulse temperature depend on the
actual supply impedance, simultaneous active load, gate slew and board
thermal path. The [onsemi FDS3992 sheet, Figure 5 and thermal
characteristics](https://www.onsemi.com/download/data-sheet/pdf/fds3992-d.pdf)
provides a single-pulse, 25 °C case SOA plot and thermal values with a
specified 1 in² copper board. The provisional native article has neither
that measured case temperature nor a final copper thermal geometry.

## Fast OV, latch and reset are separate gates

The static selected-divider high rising threshold is **17.84409 V**;
18.0 V remains a *provisional screening value*, not an accepted UCC27624
VDD limit. The LTC4368's up-to-6 µs GATE turn-off entry uses a **2.2 nF
GATE fixture**, not Rev38's 10 nF plus 22 kΩ; the UV/OV propagation
entry uses 50 mV pin overdrive. Neither bounds the protected output pin
peak under an arbitrary pre-cutoff ramp or converter short. For a monotonic
fault ramp, a necessary reviewed inequality would include
`V_trip,max + S_pre,max × t_disconnect,max + V_local_overshoot,max ≤
V_driver,accepted,max`; every term after `V_trip,max` is still missing,
and stored charge must be analyzed independently. Measure the VDD pin,
not merely controller FAULT or GATE.

RETRY is grounded, so forward overcurrent **latches off**. The LTC4368
requires a low-then-high SHDN toggle; its data sheet specifies at least
15 µs low pulse in the 12 V latch-clear fixture. In Rev38, SHDN is tied
to `AUX15_PRECUT`, so a shallow mains dip can leave the latch uncleared,
while a deeper supply interruption can clear it and cause another FET
startup. The IRM's published typical hold-up and converter soft-start do
not establish either behavior. Capture VIN/SHDN below and above the
actual threshold, GATE and VOUT through short removal, brownout and
repeated recovery. Review the intended user-visible fault reset policy
before changing RETRY or SHDN wiring.

## Exact inputs and owners for the next joined test

| Input needed | Owner/artifact | Required evidence |
| --- | --- | --- |
| `C_AUX,effective,max`, `C_GATE,effective,min`, 5 V output capacitance and ESR/ESL over voltage/temperature/age | Component qualification and Rev38 BOM | Manufacturer part-specific data or bench impedance measurements, including bias at actual pins; reconcile with native fitted quantities. |
| Coincident `I_other(t)` and `I_5V_input(t)` during cold, warm, prebiased and repeated starts | Joined AUX/logic5 and receiver loads | Same-timebase shunt differential/current, both buck input currents, relay/driver/PFC enable states and rail voltages; compare with trip at the applicable fixture. |
| Shunt resistance, Kelvin error and thermal corner | WSL2512 part and final PCB | Selected-part tolerance/TCR/lifetime budget; Kelvin layout, lead/copper drop and operating temperature capture. |
| Each FDS3992 die's linear/repeated-pulse SOA | FET part and final PCB | Simultaneous `V_DS(t)` and `I_D(t)`, pulse interval, case/board temperatures and final copper area under start, short and OV faults. |
| `RAW_AUX24` and `AUX15_PRECUT` fault waveforms | IRM-20-24/LMR36015 plus AC branch | Input line, surge, feedback-open/short and converter-failure captures, including local VIN ringing and pre-cutoff slew/source impedance. |
| Driver VDD peak and loss-of-permission time | Integrated HOT detector/driver chain | Probe at UCC27624 VDD, GATE, `AUX_PROTECTED`, HOT clear and driver EN during every upstream fault and stored-charge discharge. Set an accepted pin limit before judging the 18 V screen. |
| Recovery after forward OC and UV/OV | LTC4368 and product reset contract | SHDN low width, GATE/VOUT restart, relay and PFC inhibit, nuisance-latch behavior and repeated-start thermal state. |

Use [`bench-capture.md`](bench-capture.md) for article identity, probe
bandwidth/grounding and raw waveform retention. **No row above has a
physical PASS.**
