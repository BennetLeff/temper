# AUX producer and independent cutoff review

The existing starting point is already documented in
`zapote/power-entry/passive-reva/protection/controller-integration-06/supply/README.md`:
**IRM-10-24 → TPS7A4701RGWR set to 15 V → TPS54202DDCR set to 5 V**.
Its return is HOT_GND/PFC_BUS_MINUS. It cannot be shared with a physical output
already bonded to SELV ground. Its prior reduced-order simulation is not proof
of regulator-fault containment or transient response.

The parent accepts Luna's corrected proposal to **evaluate TPS26601RHFT after
the 15 V regulator**, before the AUX consumer fanout and the 5 V buck input.
An optional upstream cutoff would serve a different function: protection of
the regulator input. It cannot replace downstream protection against the
regulator passing normal raw input through to AUX.

TPS26600/01 offer adjustable overvoltage cutoff. MODE selection governs
overload behavior and cannot be assumed to latch an OV event. The OVP timing
entry measures a specified OVP-pin excursion to FLT assertion, not a complete
bound on downstream peak voltage. A cutoff is not a voltage clamp.
[TI TPS2660 Rev G, §§7.5–7.6, 9.3.3, 9.4](https://www.ti.com/lit/ds/symlink/tps2660.pdf).

## Rejected threshold and provisional arithmetic

Luna suggested approximately 17.5 V with 137 kΩ over 10 kΩ. The parent rejected
that setting. The primary OVP rising-threshold range is 1.17–1.225 V, with
1.19 V nominal. A divider-only calculation gives:

| Divider | Resistance variation | Nominal trip | Calculated interval | Decision |
|---|---|---:|---:|---|
| 137 kΩ / 10 kΩ | Exact | 17.493 V | 17.199–18.0075 V | Reject; exceeds 18 V even without resistor tolerance |
| 137 kΩ / 10 kΩ | ±1% each | 17.493 V | 16.881594–18.346540 V | Reject |
| 130 kΩ / 10 kΩ | ±1% each | 16.660 V | 16.078812–17.471717 V | Preliminary headroom only; not selected or qualified |

These are parent calculations, reproduced by `ovp-screen.rs` and its CSV.
They deliberately exclude pin leakage, dynamic overshoot, parasitics and
temperature effects beyond the stated threshold and resistance assumptions.
The last row only shows that a lower setting merits a complete budget. It does
not prove that actual driver VDD stays below 18 V during a regulator fault.
The existing 16.5 V shutdown detector and proposed cutoff need coordinated
threshold/recovery behavior; their order cannot be assumed at all corners.

Reproduce from this directory:

```sh
rustc --edition=2021 ovp-screen.rs -o ovp-screen
./ovp-screen > ovp-screen.csv
```

## Loads and qualification boundaries

The historical supply artifact budgets 75 mA direct AUX load and 75 mA logic5
load. With its assumed 70% buck efficiency and LDO bias allowance, it uses a
115.74 mA supply-current screen. Those are design budgets, not established
maximum demand for revision 11 plus new isolation. The current load inventory
must include the relay, gate charge/frequency, pullups, 220 Ω logic bleed,
comparators, new isolator, capacitor charging and state-dependent loads.

The prior supply document calculates about 2.116 W LDO dissipation at a 32.4 V
raw-input example and 2.417 W at its assumed 35 V limit. Those thermal screens
have unqualified local ambient and board thermal resistance. Adding a cutoff
does not establish those thermal assumptions or a physical raw-voltage bound.

Normal AUX remains 14.25–15.75 V and logic5 remains 4.75–5.25 V. Include the
PFC controller's startup requirements and the relay coil through 91 Ω;
protecting the driver alone does not establish the entire rail's suitability.
Existing regulator candidates and their specifications are documented in the
[TPS7A47](https://www.ti.com/lit/ds/symlink/tps7a47.pdf) and
[TPS54202](https://www.ti.com/lit/ds/symlink/tps54202.pdf) datasheets.

Required evidence before adopting the cutoff:

1. A bounded source/regulator pass-through waveform, source impedance,
   effective output capacitance and resulting peak driver voltage during
   disconnect. A chosen 6 µs delay in a model is not this proof.
2. Current-limit, startup, reverse-current and thermal budgets for the actual
   loads, including any regulator/cutoff interactions and component faults in scope.
3. Coordinated recovery: cutoff recovery or source hiccup cannot manufacture
   an accepted ARM command. Overload latch configuration alone does not supply
   that guarantee for overvoltage.

No new source module was compiled and no limiter parts were added. Package,
passive ratings, procurement and a complete added-component count are pending.
