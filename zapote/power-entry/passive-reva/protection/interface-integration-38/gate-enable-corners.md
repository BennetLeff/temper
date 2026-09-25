# UCC27624 ENA corner review — OPEN

This is a selection constraint for the joined U4 circuit, not a passing
electrical analysis. `elec/src/driver_stage.ato` now contains a pin-level
candidate joined to the receiver in `power_entry_integrated_38.ato`. The
proposed driver is a production
`UCC27624DDAR` (DDA 8-pin PowerPAD); its pin 1 ENA, pin 2 INA, pin 3 GND,
pin 6 VDD, pin 7 OUTA, pin 8 ENB, and pin 4 INB follow the
[TI UCC27624 data sheet](https://www.ti.com/lit/ds/symlink/ucc27624.pdf).
The [replacement bakeoff](DRIVER-TOPOLOGY-BAKEOFF.md) is complete with an
unresolved selection; it does not release this driver or U7 routing.
The inactive channel's ENB and INB require local low connections, while
OUTB remains unconnected. The DDA thermal pad requires its own GND land
review.

TI specifies an ENA output-low threshold range of 0.8–1.2 V and an
output-high threshold range of 1.8–2.3 V. Design against **ENA ≤0.8 V**
for guaranteed disable and **ENA ≥2.3 V** for guaranteed enable, at the
applicable operating corners. TI gives the internal EN pull-up as
**200 kΩ typical only**, without a minimum resistance in the electrical
table. A floating ENA enables the channel. A passive 10 kΩ or 1 kΩ
pull-down on an unpowered logic-gate output is therefore not, on its own,
a source-backed worst-case OFF proof. The nominal divider estimate cannot
be promoted to a guarantee:

```text
V_ENA(max) = V_AUX(max) * R_PD(max) / (R_PD(max) + R_EN_internal(min))
```

`R_EN_internal(min)` is not specified. The joined design needs a separate
source-backed low clamp or verified bounded current over the actual AUX
range, including HOT logic5 absent or between guaranteed operating levels.
This is a **driver-selection blocker before U7 routing**, rather than a
resistor value that can be finalized from a typical curve. TI's March 2026
Rev. E electrical table still has only a typical 200 kΩ `RENx` entry and
explicitly says a floating ENx enables the output. In a [TI support exchange
about the UCC27524 and UCC27624](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1168261/ucc27524-input-voltage-specifications),
a TI engineer first described UCC27624 characterization, then clarified that
TI could not provide the requested guaranteed EN sink-current statement. The
characterization and suggested 100 µA estimate are not a minimum resistance
or maximum input current for the selected orderable part. Do not use them as
`I_EN,internal,max` in the inequality below.

The installed candidate uses a [Nexperia PMBT3904](https://assets.nexperia.com/documents/data-sheet/PMBT3904.pdf)
NPN shunt (collector to ENA, emitter to HOT0) biased from `AUX_PROTECTED`
through a 3.3 kΩ, 1 W 2512 resistor. An [SN74LVC1G06](https://www.ti.com/lit/ds/symlink/sn74lvc1g06.pdf)
open-drain inverter on HOT_LOGIC5 sinks that base only when the retained
hardware permission AND is high. At HOT_LOGIC5 = 0 V, TI's Ioff specification
puts the inverter output in high impedance with ±10 µA maximum leakage at
an output voltage up to 5.5 V, so the AUX base bias is intended to keep
the shunt on. ENA also has a 10 kΩ AUX pull-up and a 100 kΩ local pull-down;
the latter is a no-AUX default, **not** the powered-AUX disable proof. The
inactive ENB and INB are grounded, and INA has a separate local pull-down.

The following inequalities must be evaluated at the **actual qualified AUX
minimum and maximum**, rail slew, ambient and part temperature, and resistor
tolerance before calling the OFF state proven:

```text
I_B,min = (V_AUX,min - V_BE,max) / R_B,max
          - V_BE,max / R_BPD,min - I_LVC,off,max
I_C,max = (V_AUX,max - V_ENA,off) / R_ENPU,min
          + I_EN,internal,max - V_ENA,off / R_ENPD,max
V_CE,sat,max(I_C,max, I_B,min, T) + V_return,max <= 0.8 V
```

The UCC27624 data sheet gives its internal EN pull-up resistance as 200 kΩ
**typical only**; `I_EN,internal,max` remains unknown. The PMBT3904 maximum
200 mV saturation point is stated only at 25 °C, 10 mA collector and 1 mA
base. Its cold/hot curves are typical, so they cannot close the last
inequality. The external AUX supply transient range, shunt switching delay,
NPN off leakage, 2512/1206 temperature derating, and actual 4.7 µF bypass
capacitance under DC bias also remain unbounded. The LVC output has a 5.5 V
recommended maximum; an open base connection could expose it to the AUX
pull-up above that limit. That single-fault case needs a clamp or a revised
topology, not an assumption that the intact B-E junction is always present.

For the enabled state, verify `ENA >= 2.3 V` with the 10 kΩ/100 kΩ divider
at the minimum AUX that can enable the UCC27624, including transistor
leakage. Verify the LVC sink's VOL against the base-off condition at maximum
AUX and HOT_LOGIC5 minimum. A collapse through **intermediate** HOT_LOGIC5
voltages is not covered by the LVC's VCC=0 Ioff condition: its output could
still sink the base after upstream logic leaves its guaranteed region. A
rail supervisor, hold-up proof, or revised release path must close this
crossover. Powered-AUX/unpowered-HOT-logic is a schematic hypothesis only;
low-voltage captures of every rail order are mandatory.

For an actively driven high state, check the preceding gate's VOH at the
worst pull-down and EN input load against 2.3 V. For the low state, check
its VOL and leakage against 0.8 V, and check that an unpowered gate cannot
back-power HOT logic5. The UCC27624's listed 17–27 ns enable/disable
propagation assumes its data-sheet fixture and is only one term in the
detector-to-sustained-current-cessation path. Loaded STW gate discharge,
commutation, and the independent hazard-derived allowable time remain OPEN.

The gate's compiled netlist now has explicit clamp parts; the Rust audit
rejects a floating ENA, missing shunt bias, missing receiver-abort fan-in,
logic-power backfeed, and a gate short to AUX. These are connectivity tests,
not analog OFF proof. Native board approval needs the exact pin and
footprint implementation, then low-voltage captures with AUX present and
HOT logic absent, present, falling, and recovering.

**Disposition to close U4:** obtain a written, applicable guaranteed ENA
current/voltage limit from TI and qualified shunt limits across the installed
temperature and AUX range, or select a driver/inhibit topology with published
guaranteed off-state limits and re-run the joined source, pin audit, native
parity and rail-order analysis. Either route must also address the
base-open 5.5 V exposure and intermediate HOT_LOGIC5 crossover above. A
bench sample showing ENA low is required physical evidence, but cannot by
itself replace the missing worst-case component limit.
