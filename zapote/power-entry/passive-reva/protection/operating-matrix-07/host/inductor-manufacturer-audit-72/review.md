# Manufacturer audit: Würth 760800301

The retained source `../f2-open-01/source-01/elec/src/power_entry_passive_reva.ato` names Würth part `760800301`, with `inductance = 180uH`, `current_rating = 24.5A`, `voltage_rating = 1000V`, and the Würth datasheet URL. The official Würth product catalog identifies order code 760800301 as a WE-TORPFC T75 choke and lists 180 µH, 24.5 A rated current, 43 A saturation current, and 20 mΩ DCR. The declared 180 µH therefore matches the manufacturer nominal.

The directly linked official datasheet is [760800301.pdf](https://www.we-online.com/components/products/datasheet/760800301.pdf), revision 001.001 dated 2023-12-11, status Valid. Its electrical-properties table gives:

| Property | Manufacturer value and condition | Status |
|---|---|---|
| Inductance | 180 µH, measured at 100 kHz / 100 mV, ±20% | specified tolerance |
| Rated current `I_R` | 24.5 A maximum at ΔT = 40 K | conditional maximum |
| Rated current `I_R2` | 48 A maximum at ΔT = 40 K with 4 m/s fan | conditional maximum |
| Saturation current `I_SAT` | 43 A typical at `|ΔL/L| < 30%` | typical, not a guaranteed limit |
| DC resistance | 20 mΩ maximum at 20 °C | maximum at stated temperature |
| Operating voltage | 1000 V DC maximum | specified maximum |

The datasheet states an operating temperature range of −40 °C to +155 °C. It states that unspecified electrical-property tests use +20 °C and 33% RH. Its temperature-rise plots are marked typical; airflow testing used a 115 mm diameter fan with velocity measured directly in front of the part. No guaranteed saturation-current temperature derating curve or complete thermal derating model was found in the reviewed official material.

This audit confirms the part identity and the 180 µH nominal. The retained model currently carries only nominal inductance; it does not encode the ±20% tolerance, 20 mΩ DCR, the conditional 24.5 A/48 A thermal ratings, or the 43 A typical saturation criterion. Those are model gaps, especially because saturation is typical rather than a guaranteed bound. No circuit or model files were changed.

Sources (official Würth only):

- Product catalog: <https://www.we-online.com/en/components/products/WE-TORPFC>
- Datasheet revision 001.001, 2023-12-11: <https://www.we-online.com/components/products/datasheet/760800301.pdf>
