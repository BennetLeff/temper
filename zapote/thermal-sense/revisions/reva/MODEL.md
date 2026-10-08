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
| Coil | 3.32k / 3.16k / 4.42k / 11.5k | 119.96 / 100.08 °C | 116.33–123.77 °C | 97.07–103.22 °C |

Independent circuit audit supplied the rounded reference values above. Rust calculates nominal points from source values and enumerates all 64 combinations of four resistor ±1% limits, NTC R25 ±2%, and beta ±1.5% for each output state. These are conditional parameter bounds, not measured temperatures or a complete temperature-error budget.

The exact [Vishay NTCALUG01 family datasheet](https://www.vishay.com/doc/?29092), document 29092 revision 14 January 2026, supports NTCALUG01A104GA: 100 kΩ, ±2%, beta 4190 K ±1.5%, beta interval 25–85 °C. The sensor assembly without connector is rated to 150 °C. A beta value over 25–85 °C alone does not establish accuracy at the coil's 120 °C threshold. Mounting-specific response and dissipation data do not establish response on this cooker.

The [TI TLV3201 datasheet](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) establishes the DBV pin identities used here: OUT1, GND2, IN+3, IN−4, VCC5. Qualification still needs applicable common-mode, output swing, offset, internal hysteresis and power-off limits at the actual supply/load/temperature. Resistor temperature coefficients, capacitor/filter tolerance effects, sensor thermal coupling, self-heating and cable pickup are not included in the corner table.

The requirements come from `docs/FUNCTIONAL_TEST_CRITERIA.md` THM-01/02 and the existing thermal circuits in `elec/src/modules.ato`. This unit preserves their intended topology. The older THM-01 comment's 1.765 V high-state reference is inconsistent with the loaded network: it is approximately 2.029 V at 3.3 V. No legacy source was edited to imply whole-cooker integration.

Sensor open/short-to-supply produces a cold indication. This limitation is intentionally visible in qualification findings. Resolving it requires an explicit system diagnostic strategy, not a PASS label on a circuit with no such diagnostic.
