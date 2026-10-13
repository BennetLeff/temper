# F2: is shoot-through contained by mains fuse F1 alone? (stage 19b)

**Verdict: FAIL.** F1 (Littelfuse KLDR025.TXP) cannot protect BR1 or the narrow series copper. Recommend (b): put a DC fuse in the normal build.

Rerun: `python3 -I f1_containment.py` (about 12 s, needs shapely; rewrites `result.json`, which is byte-identical on rerun).
Board of record: stage 19b, sha256 `b19a4553...` (the script asserts it against `native-21/verification/native21s19b-all-copper.json.gz`).

## Containment actually present (script step 1)
- Grep of `elec/src/*.ato` for crowbar / catch / SCR / thyristor / FC1: **0 hits**. The only fuse instances are F1 (`MainsFuse25A`) and the blower-tap fuse (`BranchFuseT3A15`).
- J7-J10 are straps. ASSEMBLY.md "Normal and bring-up configurations": normal run has J7 (RECT_P to BUS_P) and J9 (RECT_N to HV_RET) fitted, no external DC input. No fuse is in the strap path.
- `tvs_bus` (2 x 30KPA150CA) is an over-voltage clamp, not a catch for a bus short.
- So DECISIONS D-31's "FC1 and the catch circuit as containment" refers to parts the normal build does not have.

## Numbers
**Bus-cap energy** (½CV²). C is C5/C6 (TDK B32676G1905K000, 9 uF x2, +/-10 %) plus four 100 nF B32652A0104K000 = 18.4 uF from the BOM; the plan's 18.8 uF +10 % = 20.68 uF is used as the bound.

| V | E (20.68 uF) | E (18.4 uF) |
|---|---|---|
| 197.6 V (127 V +10 % crest, √2 x 139.7 V) | 0.404 J | 0.359 J |
| 280 V (U7 OVP; the plan's figure) | 0.810 J | |
| 286 V (ALT-D3 bus corner, aoe_04) | **0.846 J** | |

The plan's "280 V peak at 127 V +10 %" is not the line crest (that is 197.6 V); 280/286 V is the regenerated-bus bound. The cap dump runs in the local bus/leg/shunt loop and never passes through F1 (or through FC1 in the J7-J10 strap), so no upstream fuse limits it. It is a loop-copper and FET survival question, not assessed here (FET SOA/avalanche was in the plan step but not in this brief; D-31 puts 495 A at about 55 ns).

**Follow-on current** (a persistent short on the bus, e.g. a failed-short FET pair, fed from the line through BR1). Model: crest fault, `L di/dt = |v| - 2 x 0.9 VF - R i`; loop R = source + 2 x L1 DCR (4.5 mohm each, parts.ato) + R5 (1 mohm); L = source + 18 uH L1 leakage (s19b EMI README). The **s19b EMI model contains no mains fault source**: its 50 uH / 50 ohm LISN is a measurement receiver, so it is not used as a short-circuit source (it would give a meaningless tens-of-amps case). Source impedances used (stated):

| Case | Source | Loop R | Unfused peak | F1 melting I²t reached at |
|---|---|---|---|---|
| nominal household | 15 m 14 AWG branch + 1.8 m cord + 20 mohm service, 3 uH | 308 mohm | 634 A | 674 us, 618 A |
| cord-limited | 4.7 kA at 140 V (F1-RECOMMENDATION s2, 1.8 m cord, stiff source), 1.8 uH | 40 mohm | 4,759 A | 211 us, 1,701 A |
| **low-impedance corner** | 8.4 kA at 140 V (1.0 m cord), 1.0 uH | 27 mohm | 6,863 A | 198 us, 1,784 A |
| zero-source bound | board only | 10 mohm | 15,039 A | 183 us, 1,896 A |

F1 reaches its melting I²t in 0.18-0.67 ms in every case, i.e. it is in its current-limiting region in all of them.

**I²t comparison** (criterion fixed by the plan: F1 clearing < 0.5 x BR1 AND < every series copper segment):

| Item | Value | Source |
|---|---|---|
| F1 KLDR025 melt / total clearing I²t | 226.0 / **1,710 A²s** | Littelfuse KLDR datasheet Rev 092821, p.5 table (row KLDR025). https://static.chipdip.ru/lib/254/DOC027254593.pdf (mirror of Littelfuse.com/KLDR); PDF read in scratchpad, not committed |
| BR1 GBJ2510-F I²t (t = 8.3 ms) | **510 A²s**; 0.5 x = **255 A²s** | Diodes DS21221 Rev.11-2, p.2. https://www.diodes.com/assets/Datasheets/ds21221.pdf. IFSM 350 A (8.3 ms), VF 1.05 V at 12.5 A. The rating is a 1-8.3 ms figure |
| Narrowest series copper | 355 A²s (R5 to J10 on HV_RET, 1.17 mm neck) | script |

BR1 condition: 1,710 vs 255, F1 is **6.7x over**. Copper condition: 1,710 vs 355 (R5 to J10) and 884 (J8 to Q2/Q5 drain), **fails on those two segments** (4.8x over on the narrowest). Next: Q3 source to R5 2,076; L1 to BR1 AC1 1,747 (passes by 2 %); all others 4,000-9,200.

Sensitivities (in `result.json`): using KLDR015's larger table value 2,248 only worsens it. Even an ideal fuse with zero arc energy (F1's *melting* I²t, 226) passes the BR1 half-limit by only 11 % (226 vs 255), so a 25 A time-delay part can never be a BR1 protector at these currents; the datasheet total-clearing value is what a real clearing event delivers.

**Controls** (in the script, must behave as shown): KLDR030 (1,990) FAIL, hypothetical 100 kA²s fuse FAIL, KLDR005 (84.04) meets the BR1 condition. The script's exit code is nonzero if a control misbehaves.

## Copper method and its limits
Onderdonk adiabatic fusing: `I²t = A² log10(1 + (Tm - Ta)/(234 + Ta)) / 33`, A in circular mils (1 cmil = 5.067e-4 mm²), Tm = 1083 C, Ta = 105 C governing (25 C also in `result.json`). Copper thickness from `native-21/stackup.json`: outer 0.070 mm, inner 0.061 mm (as-built 2 oz; the thinner inner value is used for the conservative area). Widths come from the s19b copper dump: for each series segment the largest erosion radius at which the two terminal pads stay connected (tracks, zones, pads, vias, layer hops through vias/through-hole pads), neck = 2 x radius. This is the **best single route**: it ignores parallel routes and via counts, and it includes pad-hole/anti-pad pinch points, so the J8-drain and R5-J10 figures are conservative. It does not change the verdict, because the BR1 condition alone fails by 6.7x. The L1 winding wire and the CSS2H R5 element are not assessed (no sourced I²t); R5 in particular is a 1 mohm 2512 resistor in this path and is expected to open far below 1,710 A²s.

## Recommendation
**(b): fit a DC fuse in the normal build.** F1-only containment is not defensible: F1 passes more than 6x the I²t BR1 can take, so the bridge is destroyed before F1 clears, and the R5 / drain-path copper is also over its fusing limit. Do not record F1-only in DECISIONS. Options: populate the J7-J10 loop with FC1 (a fuse in place of a strap) or add a board-mount DC fuse at the re-spin. Caveats that make this an owner/vendor question and not a closed fix: a fuse sized to protect BR1 must clear below 255 A²s (e.g. a fast 600 V-class DC part), and its DC clearing I²t and arc voltage at <= 286 V are the open Mersen question from D-31. A fuse in the strap also cannot reduce the 0.85 J local cap dump. Until the fuse is fitted, mains power on the normal strap configuration should rely on the already-open items (bench bus 30-60 V and the prevention-only controls).
