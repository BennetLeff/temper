# PS2 (MEAN WELL MPM-20-24) against its 85 °C rating on the B3 hot-copper field

Board s42 (`9e075b4b`), B3 hot-copper BASIS (cb65ce911). Scratch study, 2026-10-15. The repo was read only.

## Verdict

**PS2 is inside its rating in all three cases, on the estimate below. The B3 sweep's −27.2 K (c18 @ 61) and −35.7 K
(c28 @ 55) do not measure a rating margin.** Two things are wrong with that comparison:

- **It compares an ambient rating with a pad temperature.** MPM-20's 85 °C is a working *ambient* temperature, used with
  a load-derating curve. The datasheet gives no case or pin limit.
- **Most of the 112 °C pad reading is PS2's own heat, pushed through a path that does not exist on the real part.**
  - B3's `meanwell` package has `body_air=False` (`thermal_body.py:123`). The 0.674 W board share of PS2's loss
    therefore has no way out except the four pins.
  - Three of the four pins sit on 0.4 mm tracks. The board spreading resistance at the pads is 50 K/W.
  - A solve with PS2's heat set to zero puts its pads at a 71.1 °C mean and 80.0 °C hottest, against 104.9 / 108.8 °C
    with the heat on. So PS2's own heat adds 33.7 K. Without it, the board under the body averages 66.1 °C.

The real module sheds about 70 % of its loss from its 52 × 27 × 24 mm case to air. Allowing for that:

- **c18 @ 61:**
  - case ≈ 81 °C (77–89 across the efficiency and coupling corners);
  - pads ≈ 79 °C;
  - equivalent ambient ≈ 65 °C.
- **Equivalent ambient** means the weighted mean of the air and board temperatures the module exchanges heat with.

At PS2's as-built load (7.08 W, 32.8 % of 21.6 W), the p.3 curve allows 82.9 °C of ambient:

| Case | Equivalent ambient (central) | Margin, as-built load | Margin, 90 % rule | Margin at the 9.59 W sizing allocation | Pessimistic bound* |
|---|---|---|---|---|---|
| c18 @ 61 (release) | 65.1 °C | **+17.8 K** | +15.1 K | +9.1 K | +2.9 K (−5.8 K at 9.59 W) |
| c22 @ 55 | 60.7 °C (estimate) | **+22.2 K** | +19.5 K | +13.5 K | +4.1 K (−4.6 K) |
| c28 @ 55 | 63.8 °C (estimate) | **+19.1 K** | +16.4 K | +10.4 K | −6.0 K (−14.7 K) |

\*Bound: all of the module's surroundings at the hotter of (a) bay + 15 K (the repo's board-heated-air convention) and
(b) PS2's hottest pad with PS2 unpowered. That is an extreme case: a module wrapped entirely in 80–89 °C air. The c28
bound is extrapolated from c18.

**Classification:**
- **Inside rating, on estimate**, at c18 @ 61, c22 @ 55 and c28 @ 55, at the as-built load. This needs one bench
  confirmation, because nothing measures the air at PS2. See the bench check below.
- **Not determinable without the bench** at the 9.59 W sizing allocation under the bound assumptions, and at the
  audit's 78 °C "all allowances stacked" bay. The equivalent ambient moves about 1:1 with bay air, so at 78 °C the
  c18 margin is about +0.8 K at 7.08 W and −7.9 K at 9.59 W. The ledger already lists that 78 °C case as a gap.

**Recommended action:**
- No hardware change.
- Fix the B3 model:
  - give the `meanwell` class a body-to-air path, as the film_hf caps already have;
  - rate PS2 on equivalent or local air against the p.3 curve at its load, not on its pad.
- Measure PS2's case, its local air and its output current at the S2 soak.
- Keep the fixes ranked below as contingencies in case the bench refutes the estimate.

## 1. Rating basis (MEAN WELL MPM-20-SPEC 2024-10-30, sha256 `24d3a6bb642d74ea…`, the ledger's file)

| Question | Answer | Source (quoted) |
|---|---|---|
| What PS2 is | MPM-20-24, 24 V 0.9 A, 21.6 W rated, efficiency 87 % typ | p.2 "RATED POWER … 21.6W", "EFFICIENCY (Typ.) … 87%"; BOM: ledger entry MPM-20-24 (PS2); `monitor-sweep.json` (s42 `frozen/default.csv`) |
| Is 85 °C ambient or case? | **Ambient**, with load derating | p.2 "WORKING TEMP. -35 ~ +85℃ (Refer to "Derating Curve")"; p.3 curve x-axis "AMBIENT TEMPERATURE (℃)", "(HORIZONTAL)"; p.1 "Wide operating temp. range -35 ~ +85℃" |
| Load derating vs ambient (12–24 V models) | 100 % to 55 °C, 70 % at 60 °C, 50 % at 70 °C, 30 % at 85 °C, nothing above 85 °C | p.3 Derating Curve, read from a 300 dpi render (`render/mpm20-derating2.png`, `-3.png`). This matches the ledger's 2026-10-15 re-read |
| Test conditions | 230 VAC, rated load, 25 °C ambient unless stated | p.2 Note 1 |
| Case-temperature limit or Tc point | **None published**, in the spec (4 pp.) or in MEAN WELL's PCB-type installation manual (families incl. IRM, MPM). Only an OTP of unstated threshold | p.2 "OVER TEMPERATURE Protection type : Shut down o/p voltage, recovers automatically after temperature goes down"; `PCB_EN.pdf` (ModDate 2026-01-12) has no Tc |
| Installation condition behind the rating | Ventilation, 10–15 cm clearance from an adjacent heat source, derate at high ambient | `PCB_EN.pdf` p.1 Installation (4): "Allow good ventilation … a 10-15 cm clearance must be kept when the adjacent device is a heat source"; (5) "operate under high ambient temperature … will require a de-rating in output current"; p.2 Warning (3) "refer to the specifications about the maximum ambient temperature limitations" |
| Safety approval basis | Medical and appliance standards. **No IEC/UL 62368-1, no UL file number, and no Tma or temperature condition printed for any approval** | p.2 SAFETY STANDARDS: "IEC 60601-1:2005+A1, TUV BS EN/EN 60601-1:2006+A1+A12+A2, ANSI/AAMI ES60601-1:2005/A2:2021, CAN/CSA C22.2 No. 60601-1:2014+A2, IEC 60335-1:2010/AMD2:2016, Dekra BS EN/EN 60335-1:2012+A11+A13+A1+A14+A2+A15, EAC TP TC 004 approved"; "Primary-Secondary: 2xMOPP"; "I/P-O/P:4KVAC"; Note 7 "Touch current … <80μA/264VAC" |

**Not sourced:** the temperature at which the 60601-1 / 60335-1 certificates were issued (the CB report's Tma) and the
OTP threshold. The 60335-1 approval is the one that matters for a UL 858 / 1026 appliance. It is already
CERTIFIER-PACKET A3 #14 and an S1 certifier item.

## 2. PS2's load (design records)

| Load basis | P_out | % of 21.6 W | Ambient limit (p.3) | Limit at 90 % (ledger rule) |
|---|---|---|---|---|
| **As built: 60 kHz window top, deck gate charge 382.6 + 61 nC, RECOM at the 45 % allocation** | **7.08 W** | **32.8** | **82.9 °C** | 80.2 °C |
| Same, RECOM at 53 % typ (ALT-BIAS R13): estimate | 6.51 W | 30.2 | 84.9 °C | 82.4 °C |
| Ledger sizing allocation (740 nC, 80 kHz; ALT-BIAS:52) | 9.59 W | 44.4 | 74.2 °C | 70.5 °C |
| ALT-BIAS 80 kHz budget (outside the 35–60 kHz window; ledger: not used) | 11.10 W | 51.4 | 69.3 °C | 66.5 °C |

- **Where 7.08 W comes from:** `make_heat_sources.py` C28_F: 2 × 17 V × I_ch / 0.45 + 24 V × (2 I_ch + 30 mA) + 24 V ×
  10 mA, with I_ch = 443.6 nC × 60 kHz + 22.9 mA = 49.5 mA.
  - It reproduces the B3 heat row: 7.08 W × (1/0.84 − 1) = 1.348 W, of which 0.674 W goes into the board.
  - It is the PS2 load in every BASIS case. Tank current does not change it.
- **The 740 nC allocation is not a physical charge** (DECISIONS item "c28 heat file at the 60 kHz window top").
- **Arithmetic:** for a load between 50 % and 30 %, T = 70 + (50 − L) × 15 / 20. So 32.8 % gives 70 + 12.9 = 82.9 °C.

## 3. What temperature the rating applies to on this board

### 3a. What B3 can and cannot say

- **It has no rating row and no body-to-air path for PS2.**
  - The `meanwell` class is r_pad 15 K/W, `body_air=False`, and its cite says "ASSUMED pin conduction class value".
  - So the body node (116.1 °C at c18) is pad + 0.674 W × 15 K/W, not a case temperature.
  - The other half of the loss (`sink_fraction` 0.5) leaves the model.
- **Its pad temperature is not a proxy for PS2's ambient.** The sweep's note "the pad proxy is pessimistic for this part"
  is right in direction, but the size matters. The pad reading is 112 °C. The board PS2 actually sits on is 66–80 °C.
- **What B3 can give: the board field without PS2's own heat.** That is valid, because the model is linear in the
  part-heat rows. The two solves in 3b (allowed budget: 2) give it.

### 3b. Two solves at c18 @ 61, 0.5 mm, hot copper

`scripts/ps2_field.py` mirrors `run_basis.one()`, with the same inputs, lead ties and hot copper at the bay. Snapshot:
`git archive cb65ce911` plus the s42 A4 fields, copied from the ps-selv worktree (`cache.json` computed_on_board
`9e075b4b`).

- **Control:** the base solve reproduces the BASIS run file's PS2 probe (pad max 108.81 °C, mean 104.87 °C) to the
  printed digit.

| PS2 pad (F.Cu mean) | Net / copper | With PS2 heat | PS2 heat zeroed |
|---|---|---|---|
| 1 AC/L | `tco_l`, 0.4 mm F.Cu track, 53.8 mm to J3 | 108.4 °C | 64.9 °C |
| 2 AC/N | `n_filt` F.Cu pour, 1823 mm² (mains neutral after L1) | 94.0 °C | **80.0 °C** (hottest) |
| 3 −V | `n_ls`, 0.4 mm In1 track | 107.2 °C | 74.3 °C |
| 4 +V | `v24_raw`, 0.4 mm In1 track | 108.8 °C | 67.0 °C |
| Pad mean / probe max | | 104.9 / 108.8 °C | 71.1 / 80.2 °C |
| Board under the body (F.Cu mean, min–max) | | 74.0 °C (63–109) | **66.1 °C** (61.6–81.0) |
| 10 mm ring around the body | | 80.6 °C | 76.1 °C |

- **PS2's own heat raises its pads by 33.7 K.** The spreading resistance is 50.1 K/W (0.674 W → 33.7 K). It also raises
  the ring by 4.5 K.
- **Heat path from outside:** pin 2 sits on the `n_filt` pour, which carries the 13.5 A line current. It is the only PS2
  pad that reaches the board's heat, at 80 °C (bay + 19 K).
  - Under the body there is little copper: 49 mm² of `n_filt` F.Cu, 17 mm² of `hv_ret` (In1) and 15 mm² of `bus_p`
    (In2). It is 66 °C.
  - Pins 1, 3 and 4 are on thin tracks. They are cool without PS2 and hot with it. That is the signature of the
    module's own injected heat.

### 3c. Module estimate (`scripts/ps2_calc.py`, all estimates)

**Network.** The case node exchanges heat with:
- **Air:** h 10 W/m²K (the B3 still-air basis).
  - Top face 1425 mm², to bay air.
  - Sides 3821 mm², to the board's warm layer.
  - Layer rise = bay + 0.178 × the ring's excess over the bay. 0.178 is the `thermal_body.py:245-251` film-cap method
    (k/h ≈ 4.3 mm, exponential profile) applied to the 24 mm faces. Its control: 0.242 for 17.5 mm, matching that
    method's 0.24.
- **Board:**
  - pins, R 15 K/W (B3's assumption; corners 5 / 40), in series with the 50.1 K/W pad spreading, to the zero-PS2 pads;
  - in parallel, the bottom face across an air gap of 1 mm (corners 0.5 / 2 mm, k 0.030), in series with the board
    patch under the body (2 × h × A = 0.0285 W/K), to the zero-PS2 board under the body.

**Formulas.** With G_air = 0.0525 W/K and G_board = 0.0325 W/K (mid):
- T_eq = (G_air·T_air + G_b·T_b) / (G_air + G_b).
- T_case = T_eq + P_loss / (G_air + G_b).
- T_eq does not depend on P_loss. It is the ambient a module in free air would need to reach the same case
  temperature at the same loss. That is the quantity to read against the derating curve, assuming MEAN WELL's
  derating is taken with the module in still air on a board at chamber temperature. That assumption is mine, not
  MEAN WELL's: the sheet does not say where the ambient is measured.

**c18 @ 61 (mid corner):**
- Air: top face 61.0 °C, side layer 63.7 °C.
- Board seen: 68.5 °C.
- T_eq = (0.0525 × 63.0 + 0.0325 × 68.5) / 0.0850 = 65.1 °C.
- At P_loss = 1.348 W: T_case = 65.1 + 1.348 / 0.0850 = 81.0 °C.
  - 0.40 W goes to the board and 0.94 W to air.
  - Pads ≈ 78.7 °C, not 104.9 °C.
- Corners:
  - T_case 77.5 °C (η 0.87) to 88.0 °C (η 0.80, high-R corner);
  - 86.6 °C at the 9.59 W allocation;
  - T_eq 64.7–65.3 °C over all corners.

**c22 / c28 (estimate, no zero-PS2 solve within the budget):**
- Zero-PS2 pad mean = B3 pad mean − 33.7 K. This is superposition: same 0.674 W, same copper; the loop gains of 0.06 /
  0.12 change it by a few per cent.
- The board under the body, the ring and pin 2 are scaled by the nearby unheated probes (R22–R25, J3, R1, R2): mean
  excess 19.1 / 23.9 / 34.1 K at c18 / c22 / c28.
- Results:
  - **c22:** T_eq 60.7 °C, case 76.6 °C.
  - **c28:** T_eq 63.8 °C, case 79.7 °C, pin 2 ≈ 89 °C.

**Case temperature against a peer rating (context only, not PS2's limit).** RECOM's RAC20-K, a potted 20 W module of
the same 2" × 1" class, publishes "Maximum Case Temperature +95°C" (RAC20-K Rev. 14-2025 p.5). PS2's estimated case of
77–89 °C would sit under that. MPM-20 publishes no case figure.

## 4. Fixes, ranked (contingencies: the estimate says none is needed)

| # | Fix | Cost | Certainty | Effect | Approval basis |
|---|---|---|---|---|---|
| 0 | **B3 model fix + bench (recommended)**: `meanwell` body-to-air path (A_top bay, A_sides board layer); a PS2 rating row on T_eq / local air against the p.3 curve at the load; delete the pad-vs-85 °C sweep line | none (model) | high for the model; the bench closes it | removes the false −27 / −36 K | none |
| 1 | **Derate PS2's load** | none (already low) | high | As built: 32.8 % load, limit 82.9 °C, T_eq 65.1 → 17.8 K margin at c18. At T_eq 65 °C the curve allows 60 % (13.0 W; 11.7 W under the 90 % rule). The firmware's 60 kHz window top is the bound that keeps PS2 at 7.08 W, so record it as a PS2 constraint | none: the module stays inside its own datasheet |
| 2 | **Thermal relief at pin 2** (spokes or a short neck from the `n_filt` pour) | low (one copper edit; pin 2 draws ≤ 0.75 A, p.2 "AC CURRENT 0.75A/115VAC") | medium | It is the only pad that imports board heat (80 °C vs 66 °C under the body). Upper bound of the gain: T_b falls from 68.5 toward 66 → T_eq −1 K. **Small, because PS2 is not in a hot-copper zone.** A full island under PS2 gains nothing: there is almost no copper under the body | none for the module; recheck D5 creepage at J3 / pin 2 (`d5_audit.py`) |
| 3 | **Module with a 105 °C or higher rating, same footprint and pinout** | — | **none found** | MEAN WELL IRM-20 (2025-11-21 p.2: −30 ~ +85 °C, curve down to ~5 % at 85), MPM-30 (−40 ~ +85 °C; 69.5 × 39 mm, a different case), IRM-30 (−30 ~ +85 °C, 69.5 × 39 mm); RECOM RAC20-K (−40 to +85 °C ambient, 95 °C case; L/N pitch 20.32 vs 20.8 mm, outputs 10.16 vs 8 mm apart on a 45.72 vs 45 mm span, so **not footprint-compatible**); MORNSUN LHE20-20B24WG (−40 to +85 °C; 62 × 45 mm). Search results gave Traco TMF 20 at 70 °C and ARCH AFC20N / AFCV20 at 70 / 85 °C. Those are snippets, unverified. **No stock or price given, because nothing qualifies.** MPM-20-24 itself: JLC C6675337, 5,047 at $9.7843 (ledger, 2026-10-15, not re-read) | **Any swap reopens S1:** MPM-20 was chosen for < 80 µA touch current (DECISIONS item 50; margin 8.8 µA). RAC20-K prints no touch-current figure in the text read, so its leakage is unsourced. MPM-30 is approved only to 60601-1 + CSA, and 60335-1 is "Design refer to … (by request)" (MPM-30-SPEC p.2): a weaker appliance basis than MPM-20 |
| 4 | **Move PS2** (layout lane) | high (a re-layout of the TCO domain, J3 courtyard, D5) | low gain | The board under PS2 is already one of the coolest spots on the board model: 66 °C, 5 K over the bay | none for the module; D5 / TCO-loop routing re-audit |
| 5 | **Airflow** over PS2 | high (an enclosure change; D-18 ducts the blower through the sink only) | unknown (no board-face airflow record) | It would cut the board layer and case rise | none |

## 5. Bench check (S2 soak)

**Thermocouples:**
- **TC1, case:** top face centre of PS2, fine-wire K-type, Kapton or epoxy bonded. MEAN WELL defines no Tc point, so
  this is the hottest likely spot for a potted module and the point to report.
- **TC2, local air:** shielded bead 5 mm from the long side face, at mid-height (12 mm), on the side away from J3.
- **TC3, bay air:** ≥ 50 mm from any board part.
- **TC4, pin 1 or pin 4 pad:** solder side. These are the pads B3 calls 108–109 °C.
  - **All four PS2 pins are at hazardous voltage:** pins 1 / 2 are mains, and the output is HOT-referenced with no PE
    bond. Use an insulated thermocouple and an isolated logger, or read the pad by IR through a viewing port.
- **Also log PS2's output current** (V24_RAW), at the c18-equivalent operating point.

**Reading it** (rises over TC3, so any bench bay maps to the model):

| Reading | Model prediction (c18) | Confirms | Refutes |
|---|---|---|---|
| TC1 − TC3 (case rise) | +20 K (+16 … +27 K over the corners) | ≤ +27 K | ≥ +35 K: case well above the estimate, so the air path is weaker than assumed |
| TC2 − TC3 (local-air rise) | +2.7 K (side layer); bound +15 K | ≤ +15 K | > +21.9 K: 61 + 21.9 = 82.9 °C, the limit at 7.08 W (+19.2 K under the 90 % rule) |
| TC4 − TC3 (pad rise) | +18 K (+14 … +22 K) | ≤ +25 K | ≈ +44 … +48 K (B3's 105–109 °C at bay 61): the pins really do carry the loss |
| PS2 output power | 6.5–7.1 W | ≤ 7.1 W | > 9.6 W: the margin falls to 74.2 °C (as the ledger allocation) |

**Rating criterion** (to record in the ledger):
- (TC2 − TC3) + 61 °C ≤ the p.3 limit at the measured load: 82.9 °C at 7.08 W, 80.2 °C under the 90 % rule.
- Also judge this against the audit's 78 °C stacked bay, where the c18 margin is +0.8 K at 7.08 W.

## Files

- `results/ps2.json`: rating basis, loads, B3 proxy, field study, network corners, margins per case.
- `scripts/ps2_field.py`: the 2 solves. `scripts/ps2_calc.py`: the arithmetic. The `field/` folder holds the
  per-solve JSON and rise fields.
- `dl/MANIFEST.json`: 7 datasheets (URL, revision, sha256). `txt/` holds the pdftotext extracts; `render/` holds the
  derating-curve renders.
- `runs-copy/`: the hot-copper BASIS run files with probes, copied from the ps-selv worktree (s42, cb65ce911).

## Numbers I could not source

- OTP threshold, internal hot-spot or electrolytic ratings, and any Tc point for MPM-20.
- The temperature basis (Tma) of the 60601-1 / 60335-1 certificates.
- Where MEAN WELL measures "ambient". The equivalent-ambient reading rests on my assumption about it.
- The gap between PS2's bottom face and the board (assumed 0.5–2 mm), and the pin thermal resistance (assumed
  5–40 K/W).
- RAC20-K touch current.
- Efficiency at 120–140 VAC and 33 % load (taken as 0.80–0.87).
- Local air at PS2: unmeasured, which is the point of the bench check.
