---
title: "NTC thermistor MPN encodes 10kΩ but circuit designed for 100kΩ — thermal trip threshold off by 10×"
date: 2026-07-16
category: logic-errors
module: elec-schematic
problem_type: logic_error
component: tooling
symptoms:
  - "Thermal comparator trip threshold diverges 10× from design intent — protects at wrong temperature"
  - "V_sense at 25°C = 0.30V instead of designed 1.65V with 100kΩ NTC"
  - "NTC MPN string '103' encodes R25=10kΩ but ato code declares ntc.value=100kohm"
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [atopile, ntc, mpn, thermal, part-number, b25, r25]
---

# NTC thermistor MPN encodes 10kΩ but circuit designed for 100kΩ

## Problem

The Vishay NTCALUG part number `NTCALUG103A103GCA` encodes R25=10kΩ (the `103` segment means 10 × 10³ = 10,000Ω). But the atopile code declared `ntc.value = 100kohm`, and the reference/trip divider was designed for a 100kΩ NTC. The thermal trip threshold would activate at the wrong temperature — a 10× shift in the NTC divider curve.

## Symptoms

- V_sense @ 25°C with 10kΩ NTC: 3.3V × 10k/(100k+10k) = **0.30V** (designed: 1.65V)
- Trip threshold with 150k/10k reference divider: V_INP = 0.206V — but NTC reaches 0.206V at a much different temperature with 10kΩ vs 100kΩ
- The comparator would trip at the wrong heatsink temperature — either never tripping or tripping at room temperature depending on the actual resistance curve

## Solution

Change the MPN from the 10kΩ variant to the 100kΩ variant, keeping all circuit values unchanged:

```
# Before:
ntc.mpn = "NTCALUG103A103GCA"  # R25 = 10kΩ ("103")

# After:
ntc.mpn = "NTCALUG103A104GCA"  # R25 = 100kΩ ("104")
```

The Vishay NTCALUG series part number encodes R25 in a 3-digit segment:
- `103` = 10 × 10³ = 10kΩ
- `104` = 10 × 10⁴ = 100kΩ

## Why This Works

The 100kΩ variant (`104`) matches the code's declared `ntc.value = 100kohm`. The divider (100k fixed resistor + 100k NTC) produces V_sense = 1.65V at 25°C. The reference divider (150k + 10k) produces V_INP = 0.206V. At ~100°C, NTC resistance drops to ~6.8kΩ, V_sense ≈ 3.3 × 6.8k/(100k+6.8k) ≈ 0.21V, crossing the 0.206V reference threshold.

## Prevention

- MPN human-readable strings encode physical parameters. Always verify the encoded value against the declared attribute. For resistors and thermistors, the 3-digit code follows a `[digits][exponent]` convention (e.g., `103` = 10k, `104` = 100k, `222` = 2.2k).
- Add an atopile assertion that validates the MPN against the declared value: `assert ntc.mpn contains expected_pn_name`. Or better: put the expected nominal resistance in a comment next to the MPN and verify with a manual BOM review.
- When selecting an NTC, the R25 value determines the entire divider curve. Changing the R25 by 10× without adjusting the fixed resistor and reference divider breaks the trip threshold completely.
