# Functional equivalence of the 2026-10-09 BOM simplification

Base: stage 12 source `8496f67c6`. Change: `1121945d7` (25 MPN/value changes, PROPOSAL.md safe set).
Every claim below is reproduced by a committed script. The equivalence argument has four layers.

## 1. Nothing but the reviewed parts changed (`equivalence.py`, exit 0)

The script compares the frozen native-21 netlist and resolved part export at the base revision with
the current frozen build.
- **Connections:** 357 components and 218 nets. Every net has exactly the same (designator, pin)
  members, and the component set is the same.
- **Footprints:** identical for every designator, so the board copper cannot change.
- **Part numbers:** 124 placements changed, and every one is on the reviewed old → new list. No other
  part number changed.
- **Values:** the only `.value` edits in `elec/src` are the seven reviewed ones:
  - R1/R2;
  - R34/R35;
  - R92;
  - R93;
  - the shared `rtop` (R77/R95/R110).
- **Self-test:** a pin moved on R34 and a footprint changed on one resistor are both detected.

## 2. Every swapped part meets or beats the old one, or the gap is shown harmless (`spec_dominance.py`, exit 0)

The script compares the 25 old/new pairs across 147 JLC listing attributes. Ratings must be at least
the old value; tolerance, TCR, leakage and saturation must be no worse. 12 attributes come out worse,
and each has a recorded circuit reason:

| Part | Worse attribute | Why it does not matter here |
| --- | --- | --- |
| 1N4148W (D14–D16) | 150 mA / 75 V / 1 A surge (was 300 mA / 100 V / 2 A) | They sit in a 2.52 V TL431 domain carrying ≤ 1.9 mA |
| MMBT3904 (Q7–Q9) | Vce(sat) 0.3 V, Icbo 100 nA, Pd 200 mW | Ic ≤ 0.53 mA. The output low leaves > 1.2 V of margin to the ISO7710's 1.5 V VIL, and leakage costs 1 mV |
| 4.99 k, 18 k, 30 k at 1 % | Tolerance and TCR | The intended relaxations V1–V3; numbers below |

## 3. The changed values still meet every recorded requirement (recomputed)

| Change | Requirement | Before | After | Script |
| --- | --- | --- | --- | --- |
| R34/R35 12.4 k / 11.7 k | Shunt OCP band ≥ 44 A, inside the D-31 survival range | 49.73–97.98 A | **49.53–97.77 A** | `calc_protection_bands.py` (round-3 corner model, unchanged) |
| R34/R35 | LM4040 cathode current ≥ 80 µA at worst case | 121.4 µA | 139.2 µA | same; `audit.rs` |
| R77/R95/R110 6.2 k | −2 V rail inside the monitor window; F6 bound < −1.6 V | margins UV 0.099 / OV 0.081 V | UV 0.109 / OV 0.071 V | `calc_neg_rail.py` |
| R77/R95/R110 6.2 k | TLVH431 loop phase margin ≥ 45° | 51.62° | **51.62°** | `out-D33/rail_qualification.py --loop --rtop 6200` |
| R77/R95/R110 6.2 k | Periodic stress, 256 corners: negmax < −1.6 V, shunt 0–70 mA | 256/256, worst −1.888 V | **256/256, worst −1.898 V** | `--periodic --rtop 6200`, results in `out-D33/rail-qualified-6k2/` |
| R77/R95/R110 6.2 k | Hot load (+30 mA), 128 corners | — | **128/128**, worst −1.925 V, shunt 20.3–62.9 mA | `--hot-load --rtop 6200` |
| R1/R2 100 k | X-cap discharge from 198 V to < 34 V in ≤ 1 s | **1.025 s (a miss)** | 0.854 s | `calc_discharge.py` |
| R92 18 k 1 % | SN6507 clock in 500–700 kHz | ~600 kHz | ~607 kHz, ±1.9 % from the resistor | TI SLLSFM0A Table 8-1 |
| R93 30 k 1 % | SN6507 current limit | ~0.79 A | 0.784–0.800 A, inside TI's own 0.56–1.02 A spread | TI SLLSFM0A |
| 4.99 k 1 % | Bleed 3 mA; RSR within 4.8–21 k | — | worst case 4.88 k | PROPOSAL V1 |

Also checked:
- **Source audit:** `audit.rs` passes, and 74/74 mutation tests pass (identity, membership, reference bias).
- **Source export:** `verify_source.py` passes.

## 4. What this does not prove (bench or datasheet items)

- **Ceramic DC-bias derating** is not in the listings:
  - the 0402 HF bank (Samsung CL05B104KB54PNC) must still meet ECO.md's ≥ 320 nF effective at ~2 V. At that bias X7R loss is small, but the Samsung curve should be read;
  - the merged 1210 10 µF parts (UMK325AB7106KM-T) are the same type already used and characterised in the F6 reservoirs.
- **The edge-current corner campaign** (`rail_qualification.py --edges`) was not rerun. Its input waveforms (`edge-current/waveforms.npz`) are not in the checkout. The periodic and hot-load campaigns above apply the stronger 8 A / 740 nC stress on every corner.
- **The OCP threshold node filter** goes from 5.1 kΩ to 6.0 kΩ with 1 nF (5.1 µs → 6.0 µs). The threshold is a DC level, so this only filters noise slightly more; comparator response and trip timing are unchanged.
- **Manufacturer-to-manufacturer differences that no listing captures** (for example, pulse handling of the thick-film parts) are covered by keeping every changed part in a low-stress position. Bring-up confirms them.
