# Candidate 31: BOM-only isolator and 1210 swap (stage 31, DECISIONS 34)

After stage 30, the queue's layout candidates were blocked on this floor plan:
- **30a (HS-B → LS ISO6721FB):** `spot_scan.py` still finds the second legal cluster (x 17–18.5, y 76.5–77) on the
  stage-30 board. Its LS-side nets would have to reach the LS domain through the same y 47–60 band that closed
  cluster 1, and the SELV spine (x 28–36, all four layers) bars any route east. No pass was spent.
- **30b (C161):** its n_ls pad sits in a column that `vsense_in` (In1), `ocp_kelvin_p` (In2) and `bus_fault_hot`
  (B.Cu) all occupy at x ≈ 100.3. It moves with the next LS-cluster change.

So stage 31 took the largest remaining BOM-only gains with no copper change. The bus TVS (the largest line) is a
sourcing matter, not a design stage: [`BUS-TVS.md`](BUS-TVS.md).

## 1. U9 / U32 / U44: TI ISO7710DWR / ISO7710FDWR → Chipanalog CA-IS3720HW / CA-IS3720LW

Why: ISO7710DWR had zero stock at every source checked (JLC, LCSC, DigiKey: `sourcing/STOCK-2026-10-13.csv`), and
ISO7710FDWR had 29 at JLC. JLC on 2026-10-14 (`scripts/jlc-raw/`): CA-IS3720HW 1,640 and CA-IS3720LW 2,542, both
$0.5188 at 500+.

Source: Chipanalog CA-IS3720/3721/3722 datasheet v1.05 (2023-09-01, Chinese,
https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2404091718_Chipanalog-CA-IS3720LW_C2890049.pdf). It is not in the
repo, and the section numbers below refer to it.

| | ISO7710DW (TI SLLSER9E) | CA-IS3720xW |
|---|---|---|
| Pins used | 1/7 GND1, 3 VCC1, 4 IN, 9/16 GND2, 13 OUT, 14 VCC2 | same (Table 6-2) |
| Other pins | NC | 5 = spare A-side input, 12 = spare B-side output, rest NC (may float) |
| Default output, input side unpowered or input open | H (ISO7710), L (F) | H (H suffix), L (L suffix), both stated (Table 9-1) |
| CMTI min | 85 kV/µs at 1200 V | **100** kV/µs at 1200 V (s.7.8) |
| Insulation | reinforced, VIORM 2121 Vpk | reinforced (VDE 0884-17, cert 40057278), VIORM 1414 Vpk, VIOSM 7070 Vpk (s.7.6–7.7) |
| UL 1577 | E181974, 5 kVrms | E511334, 5 kVrms (s.7.7) |
| CLR / CPG, CTI | 8 / 8 mm | 8 / 8 mm, CTI > 600, material group I (s.7.6) |
| Supplies | 2.25–5.5 V | 2.5–5.5 V |

Checks:
- **Land pattern:** the board keeps TI's DW0016B HV pattern, with pad centres at ±4.875 mm, 1.65 mm long, so the pad
  copper spans 4.05–5.70 mm from the centre line. The CA-IS3720 lead span is 10.10–10.50 mm with a 0.55–0.85 mm foot
  (s.11.3), so the foot lies 4.20–5.25 mm from the centre line, inside the pads. The 8.1 mm pad-to-pad barrier is a
  board property and does not change.
- **Spare channel:** pins 5 and 12 are single-pin nets on the board. A new audit.rs rule (`SPARE_CHANNEL_PARTS`) and a
  mutation test fail if either is ever connected.
- **Barrier stress:** 286 V peak against VIORM 1414 is 20 % (the ledger limit is 50 %).
- **CMTI:** the rows stay FILTERED / OPEN at 100 / 95 = 1.05×, against 0.89× before. The 1.5× rule is still not met.
- **Default states:** they keep the stage-30 safety argument (FMEA §6b). U44 reads LOW on HS-B power loss or an open
  input, and U9 and U32 read HIGH.

Rejected:
- **Novosense NSi822xW**, CMTI min 200, which would close the 1.5× rule. Datasheet 1.6 gives only an input "pull high or
  low" current and no open-input output state, and FMEA §6b relies on that state. The default-HIGH NSi8220W1 also had
  only 91 at JLC.
- **ISO7720 / CA-IS3721 / ISO7721 variants:** wrong channel direction or no CMTI gain.

## 2. 24 × 10 µF 50 V X7R 1210: Taiyo Yuden UMK325AB7106KM-T → Samsung CL32B106KBJNNNE

Why: JLC had 3,921 of the Taiyo part against 12,000 for 500 boards, and TY-COMPAS lists it as "non-preferred". JLC had
44,561 of the Samsung part, at $0.1575 against $0.2186.

`python3 -I mlcc_bias.py` gives the effective capacitance per part at each rail, with −10 % tolerance and 100 °C:

| Rail | V | Taiyo | Samsung |
|---|---|---|---|
| Driver VSS pairs (SW–N, LEG_RET–N_LS) | 2 | 8.54 µF | 8.76 µF (8.17 with the bias-temperature curve) |
| 5 V rails | 5 | 8.20 | 8.23 |
| V15_LS | 15 | 3.67 | 5.74 |
| P–N module span | 17 | 3.16 | 5.26 |
| V24_RAW | 24 | 2.22 | 3.87 |

- The ECO acceptance condition, ≥ 10 µF effective per driver VSS pair, holds at 16.3 µF.
- The RECOM start-up bound holds. P–N is 21.4 µF nominal against the 41.4 µF the soft-start was simulated to pass
  (ALT-BIAS §3.4), and no part can exceed its nominal.
- Thickness is 2.7 mm max, against the Taiyo part's 2.8 mm.
- s19b BP-04 (≥ 70 % of design C) stays open at 15 / 17 / 24 V with either part, but the margin improves.

## 3. Price basis

The 2026-10-13 stock survey had priced UMK325AB7106KM-T at a class-default estimate ($0.12 at 500). It is corrected to
the JLC ladder ($0.2186) in `sourcing/STOCK-2026-10-13_pricefix-umk325.csv`, and the 19c and s30 cards are restated
the same way as the KLDR fix. Without that correction the scorecard would show the cap swap as $0.90 dearer, when on
one basis it is $1.47 cheaper.
