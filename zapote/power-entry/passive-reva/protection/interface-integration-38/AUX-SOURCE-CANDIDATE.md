# Rev38 protected AUX source decision record

Status: **regulated 24 V route selected and joined for a digital candidate;
protected-output and U4 acceptance OPEN**. The IRM-20-24 raw source, 15 V
pre-cutoff buck, LTC4368-2 cutoff and TPS54202 5 V converter are joined.
This is a construction choice for the digital/native candidate, not electrical
qualification. No AC/DC overvoltage trigger or controller static threshold
is credited as a bound on the driver pin during a fault.

## Evaluation architecture and exact interface

Build the engineering candidate around [Mean Well IRM-20-24](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF)
raw 24 V, an adjustable 15 V buck, [ADI LTC4368-2](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf)
with back-to-back N-channel MOSFETs and a current-sense resistor, then a
[TI TPS54202](https://www.ti.com/lit/ds/symlink/tps54202.pdf) from the
protected rail to HOT logic5. The direct IRM-20-15 path below remains a
bench comparison; its conditional 50 °C voltage screen leaves only 62.5 mV
before disconnect and wiring losses, versus 388/411 mV low/high in the
joined regulator's illustrative feedback-only temperature screen. The
comparison does not establish a guaranteed
normal window or fault peak for either path. The [selected LTC4368 candidate](AUX-CUTOFF-CANDIDATE.md)
has exact FET, shunt, divider and gate parts but remains a **static-window
candidate only** until startup, SOA and dynamic behavior are tested. The historical IRM-10-24/LDO chain is a reference,
not a parallel or fallback power path.

| Proposed source boundary | Destination | Status |
| --- | --- | --- |
| `ac_input.CMC_L_OUT` → off-board AUX fuse → `AUX_FUSED_L`; `ac_input.AC_RECT_N` → IRM AC/N (after CMC, before main-path NTC) | IRM-20 `AC/L`, `AC/N` | **Joined source candidate** at the two-conductor branch-loop terminal; the off-board cartridge and block remain assembly nominations. Inrush, fault energy and segregation remain open. |
| IRM-20-24 pad 4 `+V`, pad 3 `-V` | `RAW_AUX24`, `HOT0` | **Compiled pin candidate**; physical orientation remains unverified. Bonding its isolated DC return to the bridge/HOT return makes this rail HOT, never SELV. |
| `RAW_AUX24`, `HOT0` | LMR36015BRNXT adjustable buck | **Joined candidate** to `AUX15_PRECUT`; exact pins and input/output passives audited, electrical window and loop stability unqualified. |
| `AUX15_PRECUT`, `HOT0` | LTC4368 `VIN`/SHDN, FDS3992 upstream drain, UV/OV dividers | **Joined candidate**; exact pins audited, no alternate feed around cutoff. Fault peak and startup OPEN. |
| FDS3992 downstream drain → 50 mΩ shunt, `HOT0` | `AUX_PROTECTED`, `HOT0` | **Joined candidate** feeding Rev38 driver, relay, PFC and window. Current/thermal acceptance OPEN. |
| `AUX_PROTECTED`, `HOT0` | TPS54202 input; 15 µH and 44 µF nominal output network to `HOT_LOGIC5` | **Joined candidate**; exact pins audited. Load, effective capacitance, startup and output window OPEN. |

The `IRM-20` data sheet's bottom-view mechanical drawing labels AC/L,
AC/N, +V and −V but does not give a numbered pin table. The installed
KiCad 10 `Converter_ACDC` library provides a **candidate** THT mapping for
both `IRM-20-15` and `IRM-20-24`. Its 45 mm left-to-right, 20.8 mm left-pair
and 8 mm right-pair hole spacing matches the manufacturer's drawing:

| KiCad pad | Library symbol function | Footprint pad center, mm |
| ---: | --- | --- |
| 1 | AC/L | (0, 0), rectangular orientation marker |
| 2 | AC/N | (0, 20.8) |
| 3 | −V | (45, 20.8) |
| 4 | +V | (45, 12.8) |

This is a source/native **mapping candidate**, not a verified physical
pin-number statement from Mean Well. The footprint is
`Converter_ACDC:Converter_ACDC_MeanWell_IRM-20-xx_THT` (installed file
SHA-256 `f5312e0c533a4a0edb84fb0a8affe6a1a6e6109c9689eedb472d169ca3d38e58`).
Before native release, overlay the actual module's terminal positions and
markings against the manufacturer bottom view and a 1:1 footprint print;
check that a bottom-view mirror has not swapped AC/L with AC/N or +V with
−V. Its 52.4 × 27.2 × 24 mm envelope, manufacturer installation
clearances, mains separation, local heat and branch routing also need native
review. The proposed AC tap precedes the precharge NTC and relay, so AUX
can start while the relay is open. It adds the module's own inrush to the
F1/CMC path; F1's 20 A nomination does not establish safe protection of the
smaller AUX branch.

### AUX AC branch protection candidate

Use a second off-board Class CC branch loop so the small IRM feed does not
depend on the 20 A main F1 to clear its faults. The proposed PCB boundary is
[Phoenix Contact `1714971`](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-5-2-95-1714971),
the two-position member of the main terminal's MKDS 5 family. Position 1
would send `CMC_L_OUT` to the off-board fuse block; position 2 would return
`AUX_FUSED_L` only to IRM AC/L. IRM AC/N would connect to `AC_RECT_N` on the
PCB. This retains the existing CMC and MOV upstream of the AUX branch, and
keeps the tap before the main NTC/relay. There is no direct copper short
between the terminal's two L positions.

Nominate a separate [Eaton `LP-CC-2`](https://www.eaton.com/us/en-us/skuPage.LP-CC-2.html)
in a second [`BCM603-1P`](https://www.eaton.com/us/en-us/skuPage.BCM603-1P.html)
block with `CVR-CCM` cover for review. Eaton lists the 2 A time-delay
cartridge at 600 Vac and 200 kA AC interruption, and the same block family
as the main F1. The [IRM-20 sheet](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF)
lists 0.6 A AC input at 115 Vac and a **20 A cold-start inrush** at 115 Vac.
The input-current entry is not a branch-wire thermal limit; the inrush peak
alone lacks duration and I²t, so it does not prove the 2 A fuse survives
cold or warm starts. Nor do component interrupt ratings establish a 10 kA
whole-assembly SCCR or coordination with 20 A F1. Record the cartridge,
block, cover, branch conductor, 1714971 solder joints and two L pads in
the native BOM; qualify inrush, clearing, terminal temperature, fuse bypass
faults and access before mains assembly. The `1714971` terminal and
IRM-20-24 pins now compile in the joined Atopile candidate; the off-board
fuse and wiring are separate assembly parts and have not been constructed
or qualified. The exact-pin audit rejects a copper bypass, direct module
feed before the fuse, broken HOT return and reversed raw output.

## Direct 15 V comparison arithmetic

Mean Well lists 15 V, 1.4 A, 21 W, ±2.5% voltage tolerance (including setup, line and load regulation), and 200 mV peak-to-peak ripple/noise for IRM-20-15. The specified AC range 85–305 Vac and 47–440 Hz includes Rev38's proposed 108–132 Vac, 60 Hz input. It gives a 1000 ms setup and 20 ms rise at 115 Vac/full load, **typical** 8 ms hold-up at 115 Vac/full load, overload hiccup at 115–160% of rated power, and 17.25–20.25 V overvoltage protection **trigger** range. None is a peak-output clamp or a guaranteed time-to-control waveform. The manufacturer's ripple test uses a 20 MHz bandwidth and 0.1 µF/47 µF termination; board transients may differ.

The ±2.5% static range at the manufacturer's stated test conditions is `14.625–15.375 V`. If the full 200 mV peak-to-peak ripple is conservatively treated as a possible excursion to either side of that range, a *25 °C screen*, not a guaranteed terminal waveform, is `14.425–15.575 V`. Rev38's 14.25–15.75 V normal AUX window then has only **175 mV at each end** for cutoff-path drop, wiring, ripple uncertainty and transients. The sheet also lists a ±0.03%/°C temperature coefficient **over 0–50 °C**. Treating that as an additional adverse 0.75% (`112.5 mV`) from 25 to 50 °C yields `14.3125–15.6875 V` at 50 °C local: only **62.5 mV each side**, before the protection path. At 40 °C local the analogous screen leaves 107.5 mV. The 40 °C inlet is not a local module temperature, and the published coefficient does not support extrapolation above 50 °C. Consequently this source cannot yet be shown to produce the allowed protected range across the product's thermal envelope. For the lower rail, the necessary steady-state condition at 50 °C local is `I_LOAD × (R_sense + R_FET1 + R_FET2 + R_copper) + other drops < 62.5 mV` **even under this conditional arithmetic**. Higher current capacity does not widen the voltage window.

The 1.4 A rating is a module output rating at the manufacturer's conditions, not a Rev38 current budget. The existing compiled relay plus named passive branch screen is about **41.50 mA** at 15.75 V nominal resistances while the relay is energized; the UCC28180 adds up to 8 mA at its stated 15 V/4.7 nF gate-load fixture. That **49.50 mA subtotal is not a maximum**. Add driver quiescent current and `Qg × fSW` at actual gate voltage/frequency, buck input current for a cornered LOGIC5 load and efficiency, all comparator/reference/supervisor currents, resistor tolerances, capacitor recharge, startup and relay pickup before setting a sense threshold or claiming 1.4 A margin. The old 75 mA direct AUX and 75 mA logic5 allowances cannot be reused as measured Rev38 loads.

## Cutoff and startup constraints

The [earlier LTC4368 static calculation](AUX-OVP-WINDOW.md) rejected the
339 kΩ/10 kΩ OV illustration as a part-selection basis: its 339 kΩ top
resistor falls outside the cited TNPU ±2 ppm/K grade. A mathematical-only
17 kΩ/500 Ω divider fits that published resistance range. With the stated
±0.34% per-resistor lifetime/temperature screen and ±10 nA input leakage,
its minimum recovery is **16.0112 V** and maximum rising trip is
**17.8804 V**. Against the conditional `15.575 V` 25 °C source screen,
static recovery margin is **436.2 mV**; against its `15.6875 V` 50 °C screen,
the margin is **323.7 mV**. Against the provisional 18.0 V cutoff target,
static rising margin is **119.6 mV**. Those 17 kΩ/500 Ω calculations did not
select a stock-verified ratio network. The joined
[20 kΩ/590 Ω divider and cutoff candidate](AUX-CUTOFF-CANDIDATE.md)
supersede them for Rev38. Neither calculation accounts for board leakage,
source output fault slew, MOSFET charge and SOA, or downstream stored charge. The
17.25–20.25 V IRM OVP figure is an internal trigger, and may occur before
or after the LTC threshold; it is never credited as a bound on
`AUX_PROTECTED`.

The LTC4368 uses external back-to-back MOSFETs, a sense resistor and a 32 ms **typical** reconnection delay after a UV/OV fault (22–45 ms at the specified fixture). Its published fast GATE discharge is fixture-dependent; the output can remain high while its downstream capacitors hold charge. The selected RETRY-to-GND latch, SHDN-to-VIN control, UV threshold, gate network and sense shunt now have exact circuit parts, but short/restart energy and the power-cycle reset waveform remain unverified. The required `VOUT` bypass is at least 1 µF effective per the data sheet; the joined 30.6 µF nominal protected-rail capacitance and 5 V buck add inrush. A sense threshold must exceed the worst startup and run current but protect the selected FETs and branch. No such mutually valid range is established yet.

The direct AC/DC source's listed 1000 ms setup at 115 Vac/full load and typical 8 ms hold-up cannot be used as a 1 s command timeout or an 8 ms safety hold-up guarantee. During startup `HOT_RUN_Q` and the relay must remain low until both HOT rails and receiver health are proven; on source collapse the driver EN shunt and retained trip must remove gate permission before their own control limits are lost. Test that rail order with the AVR reset and ESP isolation states, including brownout, repeated mains dips, IRM overload hiccup, cutoff recovery, and an output short.

## Selected regulated 24 V digital route

Build the digital route as the same fused, post-CMC AC tap → joined
IRM-20-24 raw 24 V → joined [LMR36015BRNXT](https://www.ti.com/lit/ds/symlink/lmr36015.pdf)
adjustable 15 V buck → LTC4368 disconnect → `AUX_PROTECTED` → HOT logic5
buck. The IRM-20-24 is rated 24 V, 0.9 A, 21.6 W at the manufacturer's
conditions. The TI converter is a 4.2–60 V, 1.5 A device; the nominated
BRNXT variant uses 1 MHz auto PWM/PFM. TI's `FBRNXT` has the same adjustable
output and 1 MHz nominal frequency but forces PWM at light load and permits
limited reverse inductor current from output to input. Before relay pickup,
this circuit can be lightly loaded; avoid that reverse-current behavior in
the first candidate. Auto mode's burst ripple and possible effect on the
15 V normal window and cutoff recovery still need measurement. The **raw
module and converter pins are joined**; the cutoff and 5 V stages are also
joined as circuit candidates, with no qualified output current allowance. The 24 V rail is `RAW_AUX24`, stays HOT, and must have no
feed around either buck or cutoff. The buck's `PG` pin has an 18 V
recommended ceiling and cannot be pulled up to `RAW_AUX24`.

The [IRM-20-24 manufacturer sheet](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF)
lists ±2.5% output tolerance, 200 mV peak-to-peak ripple/noise under its
specified 20 MHz/termination fixture, and ±0.03%/°C coefficient over
0–50 °C. Treating the *entire* ripple allowance as an adverse excursion
on either side gives a conditional 25 °C arithmetic screen of
**23.20–24.80 V**; adding a separately adverse 0.75% temperature term
from 25 to 50 °C gives **23.02–24.98 V**. This is useful for normal-input
review of the LMR36015 but is not a waveform guarantee at the PCB, and
the 40 °C inlet requirement does not identify the module's local ambient.
Mean Well's 27.6–32.4 V IRM-20-24 overvoltage entry describes its
internal protection trigger, not a hard peak clamp. The LMR36015's
[60 V recommended and 66 V absolute VIN limits](https://www.ti.com/lit/ds/symlink/lmr36015.pdf)
still require a measured or otherwise qualified `RAW_AUX24` fault/surge
envelope, including the VIN-pin ringing of the final layout.

The joined feedback pair is [Panasonic `ERA3AEB104V`](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3AEB104V)
100 kΩ top and [`ERA3AEB7151V`](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3AEB7151V)
7.15 kΩ bottom, each ±0.1%, ±25 ppm/K. Its nominal feedback-only output is
`1 × (1 + 100/7.15) = 14.9860 V`. With TI's `VFB = 0.985–1.015 V` and
independently adverse tolerance alone, the mathematical endpoints are
14.7337–15.2392 V. Adding independently adverse ±0.25% temperature movement
over a 100 K resistor excursion from 25 °C makes an illustrative
14.6378–15.3391 V screen. The latter leaves only 388 mV below and 411 mV
above the assumed 14.25–15.75 V *normal* window before feedback leakage,
aging, line/load error, ripple, load steps, startup overshoot and cutoff-path
drop. It is not a guaranteed terminal voltage: resistor environments, the
module's raw waveform and buck dynamics are not yet bounded. The calculation
does **not** establish a protected-rail range or fast-fault output peak.

The two bench paths use the same downstream cutoff concept and must be compared at the same measured local temperatures and load waveforms. The regulated path adds converter loss, EMI, startup sequencing and a high-side-switch failure mode; its extra static margin is meaningful only if the complete source, buck and cutoff pass the normal-window and fault captures. The IRM's published overvoltage trigger is not a bound on `RAW_AUX24` peak or the buck's output under a fault. Qualify `RAW_AUX24` against the buck's input ratings at line surges, and capture buck output and protected output separately during forced high-output, buck short, loss of feedback, mains dips and cutoff recovery. Compare the measured worst-case driver-VDD peak and turn-off delay, not just nominal rail accuracy.

### Source-build-05 load and startup worksheet

The frozen [source-build-05 receipt](source-build-05/build-receipt.json) has 296
resolved components; its `build/default.net` SHA-256 is
`c221b3048527eccbb3c9574ff35124f071c96d2b5031c19d81752c4159db13ea`.
This is the digital candidate for the worksheet below. The earlier
41.50 mA relay/passive screen and 75 mA historical allowances are not
accepted maximums. Fill each `UNKNOWN` with compatible worst-case
conditions before setting source capacity, the 50 mΩ cutoff threshold, or
FET SOA limits.

| Term | Current source-build-05 input | Missing bound or capture |
| --- | --- | --- |
| `I_5V_run(t)` at `HOT_LOGIC5` | AVR, both HOT isolator sides, 22 other active logic/detector devices, pull loads and 46.5 µF nominal output bank | **UNKNOWN** maximum at actual clock, mixed-voltage isolator activity, output states, temperature and 5 V corners; capture receiver startup, run, disarm and fault. |
| `I_5V_input(t)` at `AUX_PROTECTED` | TPS54202 and 20.1 µF nominal direct input bank | **UNKNOWN** efficiency, input peak and startup waveform while the 46.5 µF output bank charges; measure input current and 5 V voltage together. |
| `I_AUX_direct(t)` | Relay plus named passive paths screen at about 41.50 mA at 15.75 V and nominal resistances; UCC28180 and UCC27624 add active load | **UNKNOWN** coil pickup/hot resistance, gate charge at maximum switching rate and actual voltage, IC bias and all output states; capture relay pickup and PFC/gate-driver startup. |
| `I_cutoff_start(t)` and FET energy | 30.6 µF nominal direct `AUX_PROTECTED` bank, including the 20.1 µF buck input; LTC4368 gate network is 22 kΩ/10 nF | **UNKNOWN** effective capacitance maxima/minima, gate slew, shunt peak, FET voltage/current overlap and repeated-start temperature; capture GATE, both FET drains, shunt differential and `AUX_PROTECTED`. |
| `I_15V_source(t)` | 44 µF nominal `AUX15_PRECUT` output bank and the downstream cutoff load | **UNKNOWN** simultaneous startup peak, buck input demand, raw-module hiccup and thermal/line derating; capture `RAW_AUX24`, `AUX15_PRECUT` and converter input current during cold/warm starts, mains dips and faults. |

Use one synchronized capture for the credible overlap of cutoff ramp,
5 V charging, relay pickup and PFC switching. Integrate current and
voltage through startup and each fault; report peak and duration as well
as settled load. The nominal capacitance figures are connectivity inputs,
not effective capacitance or inrush bounds. [AUX-WINDOW.md](AUX-WINDOW.md)
has the detailed HOT logic5 census and measurement terms.

### Source current versus cutoff current

The frozen circuit places the LTC4368 VIN/SHDN and both UV/OV dividers on
`AUX15_PRECUT`; only the FDS3992/shunt route feeds `AUX_PROTECTED`. Thus the
15 V converter's output current and the LTC4368's forward-trip current are
different quantities. At nominal resistor values, the two always-connected
divider branches draw `V_PRE/(20 kΩ + 806 Ω)` and
`V_PRE/(20 kΩ + 590 Ω)`: **1.449 mA total at 15 V**, or 1.414–1.482 mA
over the *illustrative feedback-only* 14.6378–15.3391 V range. This is a
nominal-resistance calculation, not a maximum over resistor corners,
leakage or temperature. It is **upstream of the shunt** and therefore must
enter the IRM/LMR load budget but not the LTC forward-trip comparison.

For a waveform review, use `I_15(t) = I_pre_div(t) + I_LTC_VIN(t) +
I_shunt(t) + C_pre,eff × dV_PRE/dt + I_other_pre(t)` and
`I_shunt(t) = I_direct_post(t) + I_5V_input(t) +
C_post,eff × dV_POST/dt`. The 44 µF *nominal* LMR output bank is `C_pre`;
the 30.6 µF *nominal* direct protected bank is `C_post`. The HOT logic5
46.5 µF bank charges through the TPS54202 and appears in
`I_5V_input(t)`, not as another 46.5 µF across the cutoff. These equations
are bookkeeping identities only when the effective capacitors and all
current directions are defined at the measurement ports; they do not
predict the waveforms.

The [ADI LTC4368 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf)
specifies a 30 mV minimum forward-trip threshold in its
`VIN = 12 V, VOUT = 0 V` start fixture and 40 mV minimum at `VOUT = VIN`.
With only the selected shunt's ±1% initial tolerance, those correspond to
**0.594 A start** and **0.792 A settled** lower-trip screens. A valid start
must remain below the former after measurement uncertainty and a chosen
margin; settled load must remain below the latter. Neither threshold is an
allowed continuous current or a guarantee at the circuit's other fixtures.
The selected 1.5 A LMR and 0.9 A/21.6 W IRM ratings cannot replace this
post-cutoff comparison. In particular, an apparent 1 A operating point in
the path-drop illustration above can already exceed the LTC's minimum
settled trip threshold.

The idealized nominal direct-bank calculation gives 0.1836 A capacitive
inrush from ADI's `COUT × IGATE(UP)/CGATE` relation when `COUT = 30.6 µF`,
`IGATE(UP) = 60 µA` and `CGATE = 10 nF`. A linear 0→15 V ramp at that
constant current would last 2.50 ms and dissipate **3.44 mJ in the *pair***
of pass FETs, with initial combined `V × I = 2.75 W`. This does not assign
half the energy to either die and does not bound their peak power. The
[onsemi FDS3992 data sheet](https://www.onsemi.com/download/data-sheet/pdf/fds3992-d.pdf)
plots forward-bias SOA at a **25 °C case** and transient thermal impedance
using a specified board/temperature setup; its 2.5 W package power rating
is not a pulse SOA approval. The actual ramp can overlap 5 V conversion,
relay pickup and a partially charged output, and the installed copper and
case temperature are unknown. Capture each die's `VDS(t)` and the common
`ID(t)` through those events, then assess the trajectory and repeated-pulse
temperature against manufacturer data. The controller's fast-turnoff and
fault-propagation specifications use a 2.2 nF GATE fixture, whereas Rev38
uses 10 nF through 22 kΩ; they do not bound this board's turn-off time.

The [LMR36015 data sheet](https://www.ti.com/lit/ds/symlink/lmr36015.pdf)
specifies a 3–6 ms *internal soft-start time* at its stated fixture. The
44 µF nominal pre-cutoff bank needs 660 µC to reach 15 V, which would
average 110–220 mA if a full 0→15 V charge actually occupied 6–3 ms.
That interval is not a guaranteed output-ramp duration under the joined
load, and the source's input peak, startup limit/hiccup and capacitor
effective values remain open. Similarly, the 5 V bank stores 0.581 mJ
nominal at 5 V; its 232.5 µC *output* charge cannot be added to the
15 V shunt charge without a measured conversion efficiency and waveform.

### 15 V converter circuit entry conditions

The [TI LMR36015 data sheet](https://www.ti.com/lit/ds/symlink/lmr36015.pdf)
gives the exact RNX pin functions: PGND 1/11, VIN 2/10, NC 3 externally
joined to SW 12, BOOT 4, VCC 5, AGND 6, FB 7, PG 8, EN 9 and SW 12.
VIN needs at least 4.7 µF **effective** ceramic capacitance and a nearby
220 nF bypass at each VIN/PGND pair. BOOT requires 100 nF to SW; VCC
requires 1 µF to ground and cannot power another load. The candidate ties
EN to RAW_AUX24 and unused PG to HOT0, as permitted by TI. The installed
KiCad RNX footprint has numbered pads 1–12 and one unnumbered pad; verify
its geometry and thermal connection against TI's RNX drawing before native
release. Layout still needs paired short VIN/PGND capacitor loops, a small
SW area and distinct AGND routing before joining at HOT0.

The selected [Coilcraft `XGL6060-183MEC`](https://www.coilcraft.com/en-us/products/power/shielded-inductors/molded-inductor/xgl/xgl6060/xgl6060-183/)
is 18 µH ±20%, with 4.2 A at 20% inductance loss and 37.3 mΩ maximum DCR
at 25 °C. In an ideal 24 V→15 V, 1 MHz calculation, ripple is 0.313 A
peak-to-peak at nominal inductance and 0.391 A at its −20% tolerance edge.
At a hypothetical 35 V raw input those become 0.476/0.595 A; 35 V is a
screening point, **not** a proved source-fault ceiling. TI says to size ripple
against the converter's 1.5 A rating even for a smaller actual load. Check
temperature-dependent saturation, DCR heat, the device's 2.8 A maximum
high-side limit, and TI's minimum-inductance condition on the actual layout.

The populated candidate has two [TDK `C3225X7R2A106K250AC`](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C3225X7R2A106K250AC)
10 µF/100 V input capacitors, two [`C3216X7R2A224K115AA`](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C3216X7R2A224K115AA)
220 nF/100 V high-frequency bypasses, one Murata 100 nF/50 V BOOT cap,
one TDK 1 µF/16 V VCC cap, and two [TDK `C5750X7R1H226M250KB`](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C5750X7R1H226M250KB)
22 µF/50 V output caps. The 44 µF nominal output bank alone needs 660 µC
to reach 15 V, before downstream cutoff and 5 V startup. Effective
capacitance after bias, temperature, tolerance and aging, output ripple,
load-step recovery, inrush, and loop gain remain unverified. TI requires
load-transient and loop-gain validation before production. The inductor
footprint remains a native-review placeholder. The audit uses generated BOM
MPNs because Atopile's netlist can alias different MPNs sharing one footprint.

## Decision gates before physical acceptance

1. Measure or bound actual worst Rev38 AUX and logic5 steady, pulsed and startup currents, including gate-charge at the selected switching frequency, relay pickup and all capacitor effective values. Set an explicit supply current ceiling and compare both IRM thermal derating and voltage-window closure at **measured local** ambient, not the 40 °C inlet assumption. The direct source's 62.5 mV 50 °C screen may require the regulated path or a revised rail contract.
2. Verify the candidate KiCad pin/footprint mapping against the physical
   module and manufacturer's bottom view; finish the proposed
   1714971/LP-CC-2 off-board branch assembly, then resolve conductor ampacity,
   creepage/clearance, installation spacing and F1/IRM inrush coordination
   on a native layout. The module's independent safety approvals do not
   certify the joined appliance.
3. Resolve authorized procurement and physical footprints for the joined LTC4368 variant, FETs, shunt, precision OV and UV networks, RETRY/SHDN behavior and capacitors. Prove startup without overcurrent latch/hiccup, with the source's slew and the actual load. Verify the [selected static divider screen](AUX-CUTOFF-CANDIDATE.md) against measured source, PCB and temperature effects.
4. Capture the selected raw source (`AUX15_SOURCE` or `RAW_AUX24`), the 15 V buck output if fitted, `AUX_PROTECTED`, UCC27624 `VDD`, `HOT_LOGIC5`, ENA, gate voltage and MOSFET current for slow OV ramps and fast source faults, UV/brownout, overload, cold/warm repeated starts and loss of HOT logic. Bound peak voltage, time to gate disable and recovery. Include FET SOA and capacitor energy.

**Integration decision:** `RAW_AUX24`, `AUX15_PRECUT`, `AUX_PROTECTED` and
`HOT_LOGIC5` now have one joined source-chain candidate with exact-pin audit.
Keep U4/U7 supply and fault-response acceptance OPEN until the gates above
are measured on joined hardware. The direct 15 V path remains a bench
comparison, not the selected digital route.
