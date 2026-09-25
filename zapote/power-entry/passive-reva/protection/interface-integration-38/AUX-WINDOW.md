# Rev38 AUX fast-dip and overvoltage candidate

Status: **compiled pin topology; thresholds and response acceptance OPEN**.
The [source decision](AUX-SOURCE-CANDIDATE.md) now joins the IRM-20-24 raw
source, its 15 V pre-cutoff converter, the [AUX cutoff](AUX-CUTOFF-CANDIDATE.md)
and the [HOT logic5 converter](HOT-LOGIC5-CONVERTER.md) as a regulated-route
digital candidate. All supply electrical and physical acceptance remains
open. The direct 15 V comparison's conditional
50 °C screen leaves only 62.5 mV on each side of Rev38's assumed
14.25–15.75 V normal window before protection-path loss. Its 25 °C
nominal voltage is insufficient to choose it as the joined source.
The independent [TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf)
monitors AUX undervoltage with a 100 pF CT capacitor. This module uses a
[TLV3202](https://www.ti.com/lit/ds/symlink/tlv3202.pdf) powered from HOT
logic5 to detect an AUX dip without that CT delay, and its spare channel to
detect AUX overvoltage. Both outputs feed a
[SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf). Its high
output is a necessary condition at the second HCS21 gate in the VD/VB
detector. That gate's output drives receiver `HOT_FAULT_N` and the retained
trip fan-in. A local 10 kΩ pull-down at `AUX_WINDOW_OK` holds the condition
low if its producer is absent. The LM4040 reference is shared by physical
pin with the VD/VB detector, and the AUX divider input is joined to the
protected driver supply.

| Channel | Divider, input isolation | Comparator polarity | Nominal crossing |
| --- | --- | --- | --- |
| Fast dip | 430 kΩ / 100 kΩ, then 22 kΩ to IN1_P | IN1_P against REF25 at IN1_N; high when AUX is above threshold | 2.5 × (1 + 430/100) = 13.25 V |
| Overvoltage | 560 kΩ / 100 kΩ, then 22 kΩ to IN2_N; 22 kΩ between REF25 and IN2_P | High when AUX is below threshold | 2.5 × (1 + 560/100) = 16.50 V |

### Static detector fixture screen

The exact [Yageo 430 kΩ](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-07430KL),
[560 kΩ](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-07560KL),
[100 kΩ](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-07100KL)
and [22 kΩ](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-0722KL)
parts specify ±1% initial tolerance and ±100 ppm/°C temperature
coefficient. The shared [LM4040A25I reference](https://www.ti.com/lit/ds/symlink/lm4040.pdf)
specifies ±19 mV at −40 to 85 °C with 100 µA cathode current, requires
80 µA minimum cathode current over that temperature range, and specifies up to 1 mV
additional change between its minimum operating current and 1 mA. The
[TLV3202](https://www.ti.com/lit/ds/symlink/tlv3202.pdf) specifies ±6 mV
input offset and up to 5 nA input bias at its 5 V, `VCM = VCC/2` fixture
over −40 to 125 °C; its 1.2 mV internal hysteresis is typical, not a
guaranteed crossing bound.

With independently adverse resistor drift of ±0.65% for a 65 K excursion
from 25 °C, use ±1.65% for each resistor in an illustrative full-temperature
ratio screen. Taking `REF25 = 2.480–2.520 V` (the ±19 mV reference limit
plus 1 mV current effect), ±6 mV comparator offset, and nominal input-bias
errors of ±0.53 mV on the fast-dip input and ±0.66 mV across the OV input
pair yields:

| Crossing | Algebraic input-rail range | Remaining nominal-window separation |
| --- | ---: | ---: |
| Fast dip | **12.764–13.755 V** | 14.25 V normal low is only **0.495 V** above the highest crossing |
| Overvoltage | **15.874–17.151 V** | lowest crossing is only **0.124 V** above 15.75 V normal high |

These are **fixture screens, not accepted trip limits**. The comparator
offset and bias limits are stated for 5 V and `VCM = VCC/2`, whereas the
actual HOT logic5 rail and its threshold common mode can differ. The
reference's ±19 mV value is at 100 µA, and the real 10 kΩ bias resistor,
PCB leakage, aging and output loading require their own review. The input
bias corrections use nominal 22 kΩ and divider Thevenin resistances and
are not full resistor-corner bounds. The static OV separation is small
enough that these omitted terms and rail ripple matter before declaring
the 14.25–15.75 V operating window compatible.

At the selected [10 kΩ bias resistor's](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-0710KL)
adverse ±1.65% high corner, the *feedback-only* 4.919 V logic5 lower
screen and 2.520 V reference upper screen would still supply about
**236 µA**, before comparator input and board leakage, above the LM4040's
80 µA operating minimum. The same algebra says HOT logic5 must exceed
**3.333 V plus those extra loads** before reference regulation is assured;
the comparator's 2.7 V minimum supply specification does not make the
reference valid throughout a rail ramp. Verify default-low fault and
driver-inhibit behavior over that interval physically.

The selected Yageo 430 kΩ and 560 kΩ parts are 1% 0603 candidates. Their
nominal crossings do not establish an allowed AUX operating window. Verify
the protected AUX source's low/high/ripple/overshoot envelope, both resistor
corners, LM4040 reference current and tolerance, comparator input offset and
hysteresis, common-mode range, 22 kΩ input-injection current, LVC and HCS
logic levels, supply collapse, and fault pulse width. A fast comparator is
not proof of sub-microsecond fault-to-retained-clear timing. The VD/VB
detector, rail supervisors, retained clear, ENA shunt, loaded gate and switch
current must be included in a worst-case physical response bound.

The standalone and joined Atopile builds pass. `audit.rs` checks both
dividers, comparator polarity, reference join, AUX supply join, separate
push-pull outputs and the HCS21 fan-in; deliberate opens and swaps fail.
The protected AUX source is joined in Atopile but no native footprint or
powered result is approved.

## Load budget required before selecting the AUX producer

The historical `IRM-10-24 → TPS7A4701 → TPS54202` supply budget allowed
75 mA of direct 15 V load and 75 mA of logic5 load. Those were design
allowances for an earlier circuit, not measured Rev38 consumption. The
joined [`RT33K012` relay](https://www.te.com/en/product-2-1393240-3.html)
alone has 360 Ω **nominal** coil resistance and a 91 Ω series resistor.
Ignoring switch drop and resistance tolerance, its steady current is
`14.25/(360+91) = 31.60 mA` to `15.75/(360+91) = 34.92 mA` across the
Rev38 normal AUX window. At the same ideal endpoints its coil sees
11.37–12.57 V and the resistor dissipates 0.091–0.111 W. These are
nominal-resistance screens, not pickup or hot-coil guarantees.

The joined `integrated.net` also shows six direct passive branches from
`AUX_PROTECTED`. At 15.75 V and nominal resistance, their simple
`V/R` ceilings are 4.77 mA through the 3.3 kΩ ENA-shunt base feed,
1.575 mA through the 10 kΩ ENA pull-up, 0.158 mA through the 100 kΩ
PFC-inhibit pull-up when its node is grounded, and 0.068 mA combined
through the three AUX-sense
dividers. Together with the relay, these named passive paths screen at
about **41.50 mA**. This is neither a load maximum nor a measured operating
point: transistor drops, resistor tolerances, dynamic loads and several
ICs remain outside that sum.

If the old 75 mA direct-load allowance did not include this new relay,
only 40.08–43.40 mA remains for *all* other direct AUX loads before that
allowance is exceeded. [UCC28180](https://www.ti.com/lit/ds/symlink/ucc28180.pdf)
alone has a published 8 mA maximum operating current at its stated 15 V,
4.7 nF gate-load test condition. The UCC27624 gate driver, switching gate
charge at the selected frequency, and other direct
loads must be added under their actual conditions. LOGIC5 still needs a
separate worst-case tally including AVR64DA32, isolation, comparators,
latches and bleeds, followed by buck efficiency and startup-capacitor
current. No 75 mA number is carried forward as a Rev38 limit by default.
[TI's UCC27624 guide](https://www.ti.com/lit/ds/symlink/ucc27624.pdf)
explicitly adds `Qg × fSW` to its quiescent supply current. The selected
[STW65N65DM2AG sheet](https://www.st.com/resource/en/datasheet/stw65n65dm2ag.pdf)
publishes 120 nC **typical** at 10 V gate drive and its stated drain/current
fixture, with no maximum in that row. It cannot be used as a guaranteed
15 V gate-charge or source-current bound.

The historical LDO's 2.417 W dissipation screen at its assumed 35 V raw
input already required a conditional 35.2 °C/W board-level thermal path at
40 °C local ambient. Extra load raises that dissipation. The IRM raw-source
35 V maximum was itself an assumption, not a measured transient bound.
Select the AUX producer and protection only after the joined steady-state,
startup and fault-current tally and a real local-ambient/thermal design are
available; the 40 °C inlet requirement does not imply a 40 °C device ambient.

## Joined-load worksheet for the source decision

The current joined source has four direct AUX consumer classes:
the relay/known passive paths, UCC28180 VCC, UCC27624 VDD and the
joined HOT logic5 converter input. `driver_stage.ato` also places 4.7 µF
and 0.1 µF nominal bypass on AUX; `pfc_controller.ato` adds 1 µF. Those
**5.8 µF nominal** capacitors plus the converter's **20.1 µF nominal** input
and cutoff's **4.7 µF nominal** output capacitor total **30.6 µF nominal**
directly downstream of the cutoff. Wiring and effective-value tolerances
remain additional. These capacitors are charge loads
during startup, not steady current. The source comparison is in
[AUX-SOURCE-CANDIDATE.md](AUX-SOURCE-CANDIDATE.md).

| Term in `I_AUX_run` | Current evidence | Required bound |
| --- | --- | --- |
| Relay plus named passive paths | About 41.50 mA at 15.75 V with nominal resistances and relay energized; zero relay current before pickup | Coil/resistor temperature and tolerance, switching state, and pickup/dropout waveform |
| UCC28180 VCC | [TI specifies 8 mA maximum](https://www.ti.com/lit/ds/symlink/ucc28180.pdf) at its 15 V/4.7 nF gate-load fixture | Reconcile its `GATE` driving this circuit's input rather than that fixture, and the selected 16.2 kΩ FREQ resistor's switching-frequency corners |
| UCC27624 VDD | [TI specifies 1.0 mA maximum static](https://www.ti.com/lit/ds/symlink/ucc27624.pdf) at the stated 12 V/no-output-load fixture; switching current includes `Qg × fSW` | Bound at actual 14.25–15.75 V VDD, actual STW gate charge versus voltage/current/temperature, selected `fSW`, and gate-loop loss. The STW sheet's 120 nC at 10 V is typical only. |
| HOT logic5 converter input | TPS54202 candidate is joined; old 75 mA logic5 allowance is historical | Sum every joined 5 V consumer at its qualified mode/temperature, converter quiescent current and worst-case efficiency, then measure startup and overlapping load steps |
| Cutoff and wiring | LTC4368/FDS3992/50 mΩ shunt candidate is joined | Keep its pre-cutoff VIN/UV/OV current in the source budget, and its protected VOUT/SENSE current and capacitive load in the shunt budget; bound path drop, current-limit and short/latch energy |

Use two current budgets. At the LTC shunt,
`I_shunt,run = I_relay+passive + I_PFC + I_driver_static + Qg_max × fSW_max + I_5V_input + I_LTC_post + I_other_post`.
At the 15 V buck output, add the pre-cutoff LTC VIN/SHDN and UV/OV
divider currents to `I_shunt,run`; the two dividers alone draw 1.449 mA
at nominal 20 kΩ/806 Ω and 20 kΩ/590 Ω values with 15 V input. The
shunt does **not** sense those divider currents. Each term needs a
compatible operating fixture and source-backed maximum; the 41.50 mA
and 8 mA entries cannot be promoted into a total maximum. During startup,
include the 44 µF nominal pre-cutoff bank at the 15 V producer and the
30.6 µF nominal post-cutoff bank at the shunt. The separate 46.5 µF
logic5 output bank appears upstream through the TPS54202 input-current
waveform. Integrate the measured currents with simultaneous converter
startup, relay pickup and PFC activity. This determines whether the shunt
trips or the IRM/LMR hiccups during a valid start. Current capacity alone
cannot close either candidate's normal voltage window or fast-fault
driver-pin peak. See the [separate-port worksheet](AUX-SOURCE-CANDIDATE.md#source-current-versus-cutoff-current).

### HOT logic5 census from the joined netlist

The frozen `source-build-05/build/default.net` with SHA-256
`c221b3048527eccbb3c9574ff35124f071c96d2b5031c19d81752c4159db13ea`
has 91 pin nodes on `hot_logic5`, belonging to 65 distinct components.
The count is a **connectivity inventory**, not a current measurement or a
guaranteed load bound. Re-run it whenever the joined source changes.

| Directly connected class | Count | What the source budget must include |
| --- | ---: | --- |
| AVR64DA32-E/PT | 1 | Active current at the programmed clock, enabled peripherals, I/O loads, temperature and actual 5 V rail |
| ISO7741FQDWWRQ1 and ISO6742FQDWWRQ1 HOT sides | 1 each | `VCC2` supply current at the actual 3.3 V/5 V split, input states and switching rates; both isolators' `VCC1` inputs belong to the separate SELV budget |
| SN74HCS21PWR / SN74HCS74PWR | 6 / 5 | Static and switching current plus loaded outputs, including retained logic during reset |
| TLV3202IDR / TPS389001DSER | 3 / 2 | Comparator/supervisor bias and output loading over the rail/fault sequence |
| Other logic and watchdog | 6: one each SN74LV221AQPWRQ1, SN74LVC1G08DBVR, SN74LVC1G06DBVR, TPS3431SDRBR, SN74HCS04PWR and SN74HCS00PWR | Static/switching current, output loading and watchdog service states |
| GRM188R71H104KA93D local bypass | 25 × 0.1 µF nominal | **2.5 µF nominal** is already tied from HOT_LOGIC5 to HOT0; add converter output capacitance and effective-value corners before an inrush calculation |
| TPS54202 output network | 2 × 22 µF output capacitors, 1 × 15 µH inductor, 1 feedback resistor and 1 feedforward capacitor on HOT_LOGIC5 | 46.5 µF nominal rail bank including the 2.5 µF local bypass; actual effective capacitance, 5 V load and upstream charge profile OPEN |
| RC0603FR-0710KL pull resistors | 9 × 10 kΩ nominal | Up to 4.5 mA in the artificial all-low, ideal-5 V/nominal-R state; determine mutually reachable states and resistor/rail corners |
| RC0603FR-07294KL | 1 × 294 kΩ nominal | Determine its other node and state; at most 17 µA in the same ideal-5 V/grounded-end arithmetic screen |

The 25 active ICs are `1 + 2 + 6 + 5 + 3 + 2 + 6`; the original 25 local
capacitors and 10 resistors plus the five new converter-output components
complete the 65 components. This inventory counts only pins
directly on the 5 V net; any load
reached through a resistor or output, and the converter's own losses, still
need a state-by-state tally.

[Microchip's AVR64DA power table](https://onlinedocs.microchip.com/oxy/GUID-A033CDA8-8724-46BD-B29F-D830FF21A623-en-US-12/GUID-FCC6C1C6-AACB-485E-AF93-582CB4F32BA1.html)
quotes 5.3 mA maximum at 24 MHz with peripherals disabled, I/O low and
**3.0 V VDD**. It is not a 5 V installed-load maximum.
[TI's ISO774x-Q1](https://www.ti.com/lit/gpn/ISO7742-Q1) and
[ISO6742-Q1](https://www.ti.com/lit/gpn/iso6742-q1) supply tables use
specified rail combinations and input-switching fixtures. The actual
3.3 V SELV / 5 V HOT split and channel activity need a matching bound or
measurement; figures from unmatched fixtures cannot be summed as a
guaranteed installed-load maximum.
The ESP adapter currently configures UART1 at 115200 baud, but the remaining
isolator channels have independent activity and static states. Determine the
mixed-voltage current bound or measure it in the relevant modes.

Before qualifying the TPS54202 output network and LTC4368 sense resistor,
measure `I_5V(t)` with the complete receiver and isolation loads through
power-up, reset, run, disarm and fault. Separately capture the `AUX_PROTECTED`
input current while the converter charges the 46.5 µF nominal 5 V bank.
Integrate each startup waveform and compare
its overlapping peak with relay pickup, PFC/gate-driver startup, the cutoff
trip threshold and the source overload/retry behavior. The 5 V capacitor
charge is 232.5 µC at nominal values and exactly 5 V; it is not an AUX-input
charge or a peak-current bound.
