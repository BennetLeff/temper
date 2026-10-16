| Id | Change | Placements | BOM lines | $ at 500, JLC | $ at 500, card |
|---|---|---:|---:|---:|---:|
| A | G08: bus OVP onto U14's spare OV channel (INB), U14 TPS3700 -> TPS3701, NAND3 -> Schmitt NAND2 | -6 | -1 | -1.24 | -1.14 |
| A0 | G08 fallback if A's shared die is refused: U14 TPS3700 -> TPS3701 (+ R48 105k -> 102k) only, BOM-only | +0 | +0 | -0.46 | -0.01 |
| B | G07: each rail monitor's TL431A + LM339B + rref + halfref -> two TPS3701 (one per window), own dividers | -6 | -2 | +1.63 | +0.26 |
| C | G09 CT: U10 (CT_OC_POS) + U12 (CT_ZC) -> one TLV3202 dual; U11 (CT_OC_NEG) stays single | -2 | +1 | -0.64 | -0.31 |
| C-hot | (alternative, not recommended) G08: U6 (OCP) + U7 (OVP) -> one TLV3202 | -2 | +1 | -0.64 | -0.31 |
| D | G05: U1/U2 2EDR8259X (8 V UVLO) -> 2EDR9259X (15 V UVLO), monitor kept | +0 | +0 | +0.48 | +0.97 |
| E | G05 reservoirs: 2 x 10 uF 1210 -> 1 x 22 uF 1210 per VSS (src-n sits at ~2 V) | -4 | +1 | -0.63 | -0.63 |
| H | G06: delete C24 (V15_LS 10 uF in parallel with the TPS7A4700's C99/C100) | -1 | +0 | -0.16 | -0.16 |
| A+B+C | A + B + C | -14 | -3 | -0.26 | -1.21 |
| A+B+C+E+H | A + B + C + E + H | -19 | -2 | -1.05 | -2.00 |

Baseline s43: 351 placements, 93 lines, $210.72 (JLC basis) / $202.32 (card basis).
