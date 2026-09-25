# Conditional thermal model

The reference is a loaded three-resistor network, not an unloaded two-resistor divider. For each comparator output state:

```
Vref = (VCC/Rtop + Vout/Rhyst) / (1/Rtop + 1/Rbottom + 1/Rhyst)
Rntc = Rfixed * Vref / (VCC - Vref)
T_C = 1 / (1/298.15 + ln(Rntc/R25)/beta) - 273.15
```

The sense node is on IN−, reference on IN+. With ideal rail outputs, Vout=0 gives the heating trip; Vout=VCC gives the cooling release. Supply cancels in this ideal ratiometric model. It does not cancel comparator nonidealities, receiver loading or self-heating.

| Channel | Rfixed / Rtop / Rbottom / Rhyst | Nominal trip / release | Trip corner range | Release corner range |
|---|---|---|---|---|
| Heatsink | 10k / 9.09k / 11.5k / 34.8k | 84.96 / 69.79 °C | 82.40–87.62 °C | 67.65–72.01 °C |
| Coil | 10k / 20k / 8.06k / 42.2k | 119.65 / 99.96 °C | 116.02–123.44 °C | 96.96–103.10 °C |

Independent circuit audit supplied the rounded reference values above. Rust calculates nominal points from source values and enumerates all 64 combinations of four resistor ±1% limits, NTC R25 ±2%, and beta ±1.5% for each output state. These are conditional parameter bounds, not measured temperatures or a complete temperature-error budget.

The exact [Vishay NTCALUG01 family datasheet](https://www.vishay.com/doc/?29092), document 29092 revision 14 January 2026, supports NTCALUG01A104GA: 100 kΩ, ±2%, beta 4190 K ±1.5%, beta interval 25–85 °C. The sensor assembly without connector is rated to 150 °C. A beta value over 25–85 °C alone does not establish accuracy at the coil's 120 °C threshold. Mounting-specific response and dissipation data do not establish response on this cooker.

The [TI TLV3201 datasheet](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) establishes the DBV pin identities used here: OUT1, GND2, IN+3, IN−4, VCC5. Qualification still needs applicable common-mode, output swing, offset, internal hysteresis and power-off limits at the actual supply/load/temperature. Resistor temperature coefficients, capacitor/filter tolerance effects, sensor thermal coupling, self-heating and cable pickup are not included in the corner table.

The requirements come from `docs/FUNCTIONAL_TEST_CRITERIA.md` THM-01/02 and the existing thermal circuits in `elec/src/modules.ato`. Rev B preserves the hot targets while retuning the coil divider and adding open detection. The older THM-01 comment's 1.765 V high-state reference is inconsistent with the loaded network: it is approximately 2.029 V at 3.3 V. No legacy source was edited to imply whole-cooker integration.

## Open detection

R9=1.21kΩ and R10=100kΩ produce an unloaded OPEN_REF of 0.98804 VCC. TLV9031 IN+ sees SENSE and IN− sees OPEN_REF. Its output rises on an open circuit. SN74LVC1G32 ORs this with the independent hot output. Hot hysteresis remains connected to HOT, never to the combined FAULT output. No external open-comparator hysteresis is fitted; the downstream latch must tolerate threshold transitions without permitting restart.

The original 3.32kΩ coil divider put a valid 0 °C sensor too close to the rail. Changing it to 10kΩ creates room for the open threshold; 20k/8.06k/42.2k restore approximately 120/100 °C hot thresholds.

For every supply, resistor and NTC corner, the open model checks:

```
Rntc(T) = R25 * exp(beta * (1/(T+273.15) - 1/298.15))
Vsense_cold_max = VCC*Rntc/(Rfixed+Rntc) + I_sense*(Rfixed || Rntc)
Vref_min/max = VCC*Rbottom/(Rtop+Rbottom) ± I_reference*(Rtop || Rbottom)
Vopen_min = VCC - I_sense*Rfixed
cold_margin = Vref_min - Vsense_cold_max - comparator_error
open_margin = Vopen_min - Vref_max - comparator_error
```

The contract specifies 0 °C minimum valid temperature, 14 mV comparator-error allowance, aggregate ±1 µA sense loading and ±2 µA reference loading. These are explicit integration obligations. They are not claims of guaranteed device limits at every operating condition. The 14 mV allowance budgets offset plus rail-end common-mode and supply effects; actual applicability still requires qualification. The 0 °C calculation also extrapolates the sensor's published 25–85 °C beta interval.

The open-settling model starts at zero filter voltage and solves threshold crossing, not merely the RC time constant:

```
V(t) = Vopen_min * (1 - exp(-t/(Rfixed*Cfilter)))
t_detect = -Rfixed*Cfilter*ln(1 - (Vref_max+comparator_error)/Vopen_min)
```

Rust checks the worst corner against 10 ms using source filter tolerance. Extra cable capacitance, propagation delay, common-mode/logic behavior, power sequencing and the eventual shutdown path require physical timing verification. The model includes normal cold, hot, open on either lead, short to ground/supply and healthy reconnect cases. It does not model every component failure or certify the full protection chain.

Official pin identities: [TLV9031](https://www.ti.com/lit/ds/symlink/tlv9031.pdf) OUT1/GND2/IN+3/IN−4/VCC5; [SN74LVC1G32](https://www.ti.com/lit/ds/symlink/sn74lvc1g32.pdf) A1/B2/GND3/Y4/VCC5. Comparator outputs are never tied together.
