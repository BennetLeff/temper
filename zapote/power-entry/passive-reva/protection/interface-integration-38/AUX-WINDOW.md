# Rev38 AUX fast-dip and overvoltage candidate

Status: **compiled pin topology; thresholds and response acceptance OPEN**.
The [source decision](AUX-SOURCE-CANDIDATE.md) now joins the IRM-20-24 raw
source as the regulated-route digital candidate; protected AUX and HOT
logic5 producers remain open. The direct 15 V comparison's conditional
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
The AUX source itself is still an external port, and no native footprint or
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

The current joined source has exactly four direct AUX consumer classes:
the relay/known passive paths, UCC28180 VCC, UCC27624 VDD and the still
unjoined HOT logic5 converter input. `driver_stage.ato` also places 4.7 µF
and 0.1 µF nominal bypass on AUX; `pfc_controller.ato` adds 1 µF. Those
**5.8 µF nominal** capacitors exclude the converter input, cutoff-required
output bypass, wiring and effective-value tolerances. They are charge loads
during startup, not steady current. The source comparison is in
[AUX-SOURCE-CANDIDATE.md](AUX-SOURCE-CANDIDATE.md).

| Term in `I_AUX_run` | Current evidence | Required bound |
| --- | --- | --- |
| Relay plus named passive paths | About 41.50 mA at 15.75 V with nominal resistances and relay energized; zero relay current before pickup | Coil/resistor temperature and tolerance, switching state, and pickup/dropout waveform |
| UCC28180 VCC | [TI specifies 8 mA maximum](https://www.ti.com/lit/ds/symlink/ucc28180.pdf) at its 15 V/4.7 nF gate-load fixture | Reconcile its `GATE` driving this circuit's input rather than that fixture, and the selected 16.2 kΩ FREQ resistor's switching-frequency corners |
| UCC27624 VDD | [TI specifies 1.0 mA maximum static](https://www.ti.com/lit/ds/symlink/ucc27624.pdf) at the stated 12 V/no-output-load fixture; switching current includes `Qg × fSW` | Bound at actual 14.25–15.75 V VDD, actual STW gate charge versus voltage/current/temperature, selected `fSW`, and gate-loop loss. The STW sheet's 120 nC at 10 V is typical only. |
| HOT logic5 converter input | No converter is joined; old 75 mA logic5 allowance is historical | Sum every joined 5 V consumer at its qualified mode/temperature, converter quiescent current and worst-case efficiency, then measure startup and overlapping load steps |
| Cutoff and wiring | LTC4368/FET/shunt are only candidates | Controller bias, divider currents, path drop, output capacitance, current-limit and short/retry energy |

The selection equation is
`I_AUX_run = I_relay+passive + I_PFC + I_driver_static + Qg_max × fSW_max + I_5V_input + I_cutoff + I_other`.
Each term needs a compatible operating fixture and source-backed maximum;
the 41.50 mA and 8 mA entries cannot be promoted into a total maximum.
Separately integrate `I_start(t)` through the selected cutoff and all
effective capacitances, including simultaneous 5 V buck startup and relay
pickup. This determines the shunt/current-limit threshold and whether the
IRM overload mode, buck current limit, or cutoff retries during a valid
start. Current capacity alone cannot close either candidate's normal voltage
window or fast-fault driver-pin peak.

### HOT logic5 census from the joined netlist

The generated `build/integrated.net` with SHA-256
`f8cdba302168068d0f5da3283575a7833d4cfc488419bdc3d1e76cd3e0d666f4`
has 86 pin nodes on `hot_logic5`, belonging to 60 distinct components.
The count is a **connectivity inventory**, not a current measurement or a
guaranteed load bound. Re-run it whenever the joined source changes.

| Directly connected class | Count | What the source budget must include |
| --- | ---: | --- |
| AVR64DA32-E/PT | 1 | Active current at the programmed clock, enabled peripherals, I/O loads, temperature and actual 5 V rail |
| ISO7741FDWR and ISO7742FDWR HOT sides | 1 each | `VCC2` supply current at the actual 3.3 V/5 V split, input states and switching rates; both isolators' `VCC1` inputs belong to the separate SELV budget |
| SN74HCS21PWR / SN74HCS74PWR | 6 / 5 | Static and switching current plus loaded outputs, including retained logic during reset |
| TLV3202IDR / TPS389001DSER | 3 / 2 | Comparator/supervisor bias and output loading over the rail/fault sequence |
| Other logic and watchdog | 6: one each SN74LV221AQPWRQ1, SN74LVC1G08DBVR, SN74LVC1G06DBVR, TPS3431SDRBR, SN74HCS04PWR and SN74HCS00PWR | Static/switching current, output loading and watchdog service states |
| GRM188R71H104KA93D local bypass | 25 × 0.1 µF nominal | **2.5 µF nominal** is already tied from HOT_LOGIC5 to HOT0; add converter output capacitance and effective-value corners before an inrush calculation |
| RC0603FR-0710KL pull resistors | 9 × 10 kΩ nominal | Up to 4.5 mA in the artificial all-low, ideal-5 V/nominal-R state; determine mutually reachable states and resistor/rail corners |
| RC0603FR-07294KL | 1 × 294 kΩ nominal | Determine its other node and state; at most 17 µA in the same ideal-5 V/grounded-end arithmetic screen |

The 25 active ICs are `1 + 2 + 6 + 5 + 3 + 2 + 6`; the 25 capacitors and 10
resistors complete the 60 components. This inventory counts only pins
directly on the 5 V net; any load
reached through a resistor or output, and the converter's own losses, still
need a state-by-state tally.

[Microchip's AVR64DA power table](https://onlinedocs.microchip.com/oxy/GUID-A033CDA8-8724-46BD-B29F-D830FF21A623-en-US-12/GUID-FCC6C1C6-AACB-485E-AF93-582CB4F32BA1.html)
quotes 5.3 mA maximum at 24 MHz with peripherals disabled, I/O low and
**3.0 V VDD**. It is not a 5 V installed-load maximum.
[TI's ISO774x supply table](https://www.ti.com/lit/gpn/ISO7741) specifies
separate hot-side supply currents for 5 V on *both* sides and specific DC or
all-channel-switching fixtures. This design supplies the other side at
SELV3V3, so those figures cannot be added as a guaranteed split-rail bound.
The ESP adapter currently configures UART1 at 115200 baud, but the remaining
isolator channels have independent activity and static states. Determine the
mixed-voltage current bound or measure it in the relevant modes.

Before selecting the TPS54202 output network and LTC4368 sense resistor,
measure `I_5V(t)` with the complete receiver and isolation loads through
power-up, reset, run, disarm and fault. Separately capture the `AUX_PROTECTED`
input current while the converter charges the 2.5 µF nominal bypass plus
its required output capacitor. Integrate each startup waveform and compare
its overlapping peak with relay pickup, PFC/gate-driver startup, the cutoff
trip threshold and the source overload/retry behavior. The 5 V capacitor
charge is 12.5 µC at nominal values and exactly 5 V, before the converter
output capacitor; it is not an AUX-input charge or a peak-current bound.
