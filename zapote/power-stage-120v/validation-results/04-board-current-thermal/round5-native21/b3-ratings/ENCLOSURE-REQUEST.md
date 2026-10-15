# Request to the enclosure session (temper-f7): airflow over the power board's FET-row / R5 region

From the native-21 power-stage integration session, 2026-10-15 (DECISIONS 46). This is a request, not an edit to the
enclosure records.

## Why

The thermal-ratings audit (`audit-2026-10-15/README.md`) rated the board's hot spots against the laminate and the part
datasheets. It used a body-level model and the enclosure's own bay-air figures (R33 study 14: 55 °C expected,
61 °C worst, 78 °C all allowances stacked). The board sees still air: study 14 models the bay as "a well-mixed wrapper
with no through-flow", and D-18 ducts the blower through the heatsink only. Still air is h ≈ 10 W/m²K.

At h 10 and 55 °C bay air, the board copper at R5.4 (x 39.5, y 15.5 mm, F.Cu) exceeds the laminate's UL maximum
operating temperature of 130 °C (Kingboard KB-616(X), UL E123995):
- at the 22 A default ceiling, by about 12 K;
- at the 28 A Kconfig ceiling, by about 56 K.

The HF film caps C38 / C40 next to it go over their 110 °C Top,max at 22 A.

## What helps, from the audit's sensitivities

| Board-face h over the FET-row / R5 region | R5.4 copper, 28 A / 22 A |
|---|---|
| 15 W/m²K | −27 / −18 K |
| 20 W/m²K | −42 / −28 K |

Airflow is the largest single lever and needs no board change. A board fix (less tank-copper heat, candidate 36) and a
lower still-air ceiling are being worked in parallel, so a partial airflow still counts.

## Asks

1. Can the blower's flow, or a bleed from it, be directed across the power board's top face over the FET row and R5?
   The region is the strip from the TO-247 row (Q5, Q6, Q3, Q2 at x 4.5–62.6 mm, CPL y −4.2) to the HF film caps
   (C41, C40, C38, C39 at x 2.4–82.8 mm, CPL y −28.2), with R5 at (38.5, −12.6). So x 0–90 mm, CPL y 0 to −35 mm
   (`fab/positions-kicad.csv`). If so, give the flow path and the expected face velocity, so we can convert it to an h.
2. If not, confirm that the bay is still air in every operating state, including after the fan stops. The power board's
   continuous rating is then set from h 10 (DECISIONS 46).
3. The bay-air figures (55 / 61 / 78 °C) move every margin 1:1. Is a soak measurement of bay air at 40 °C ambient and
   28 A planned? Study 14 already asks for PS1 case and bay-air thermocouples.

Reply through the enclosure records; this session reads them.
