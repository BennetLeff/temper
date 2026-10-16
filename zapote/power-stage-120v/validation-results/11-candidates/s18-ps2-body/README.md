# S18: PS2 (MEAN WELL MPM-20-24) gets a body-to-air path and a gated local-air row in B3

**Result: PS2 passes its datasheet rating in every BASIS case.**

| Case | Margin under the ledger's 90 % rule | Margin on the curve itself |
|---|---|---|
| c17.5 @ 61 (release) | **+4.2 K** | +6.9 K |
| c22 @ 55 | +10.2 K | +12.9 K |
| c28 @ 55 | +10.2 K | +12.9 K |

The rated quantity is the module's local air, which the model puts at bay + 15 K (76.0 °C at release). The limit at
PS2's as-built 7.08 W load is 80.2 °C under the ledger's 90 % rule, or 82.9 °C on the curve.

**What moved.**
- The release margin moves from +1.0 to **+1.2 K**, and the binding row is still R10.
- **PS2 does not bind.** It is the fourth-worst gated row at release, tied with R20 at +4.2 K.
- The old "−26.5 K" reading compared the 85 °C ambient rating with a pad temperature. It also came from a model that
  forced half of PS2's loss through its pins and dropped the other half. Neither was a rating margin.

**Board and base.**
- Board native21s47 `4139c87b…`, hot-copper BASIS.
- Branch `claude/native21-s18-ps2-body` from `4446e08a1` (ps-integrate: s47 on the hot-copper basis).
- The integrator decides (`DECISIONS-DRAFT.md`, item 64?).

```
cd validation-results/04-board-current-thermal/round5-native21/b3-ratings
python3 run_basis.py --workers 3 --runs $S/basis --out $S/margins-basis.json                  # BASIS, S18 model
python3 run_basis.py --workers 3 --module-pins-only --runs $S/control-pins-only --out $S/control-pins-only/margins.json
python3 run_basis.py --workers 2 --cases c17.5_h10@61 --module-r-pad 5 --module-gap-mm 0.22 --runs $S/sens-strong --out $S/sens-strong/margins.json
python3 run_basis.py --workers 2 --cases c17.5_h10@61 --module-r-pad 40 --runs $S/sens-weak --out $S/sens-weak/margins.json
python3 test_b3_airflow.py; python3 test_b3_hot_copper.py
python3 -I ../../../11-candidates/s18-ps2-body/scripts/summarize.py $S/basis $S/base-runs margins.json(s47) $S/margins-basis.json \
        "$S/sens-strong:strong" "$S/sens-weak:weak" > results/ps2-summary.json
#   S = /Users/bennet/Desktop/temper/worktrees/runs-native21/s18-ps2 (run files, not in git); base-runs = the s47 run files
```

## 1. What MEAN WELL rates (MPM-20-SPEC 2024-10-30, sha256 `24d3a6bb…`, re-fetched 2026-10-15, same file as the ledger's)

| Question | Answer | Source (quoted) |
|---|---|---|
| What the 85 °C is | **The ambient air around the module**, used with a load derating | p.2 ENVIRONMENT "WORKING TEMP. -35 ~ +85℃ (Refer to "Derating Curve")"; p.3 Derating Curve x-axis "AMBIENT TEMPERATURE (℃)", "(HORIZONTAL)"; p.1 "Wide operating temp. range -35 ~ +85℃" |
| Derating, 12–24 V models | 100 % to 55 °C, 70 % at 60 °C, 50 % at 70 °C, 30 % at 85 °C, then vertical to 0 at 85 °C | p.3 curve, read from a 200 dpi render (`runs-native21/s18-ps2/render/p3-derating.png`); this matches the ledger and the ps2-thermal study |
| Input-voltage derating | 100 % from 100 VAC up, so the 108–140 VAC line corners sit on it | p.3 "Output Derating VS Input Voltage" |
| Case, Tc point or pin limit | **None published** | p.1–p.4; MEAN WELL PCB-type Installation Manual (`PCB_EN.pdf`, ModDate 2026-01-12) p.1 (4) "Allow good ventilation …", (5) "operate under high ambient temperature … will require a de-rating in output current", p.2 Warning (3) "Please refer to the specifications about the maximum ambient temperature limitations". The OTP threshold is not given (p.2 "OVER TEMPERATURE … Shut down o/p voltage") |
| Where "ambient" is measured | **Not stated** | neither document says |
| Body | 52.4 × 27.2 × 24 mm (L × W × H), ±0.5 mm; pins 1.04 mm diameter, 3.5 +1/−0.5 mm long | p.2 OTHERS "DIMENSION 52.4\*27.2\*24mm (L\*W\*H)"; p.4 Case No.219A |
| Efficiency | 87 % typ, at 230 VAC, rated load and 25 °C | p.2 "EFFICIENCY (Typ.) … 87%"; Note 1 |
| Approval basis | IEC 60601-1, IEC/EN 60335-1 (Dekra), CAN/CSA 60601-1, ANSI/AAMI ES60601-1. No UL file number and no Tma printed | p.2 SAFETY STANDARDS; ledger entry MPM-20-24 (unchanged) |

**So the gated row rates PS2's modelled local air, and never its pad or case.** `results/datasheet-manifest.json`
holds the URLs, sha256 and the quotes.

## 2. The model (`thermal_body.py` `meanwell` class → `module_box`)

**Before.**
- The class had pins only (`body_air False`), with 15 K/W from the body node to the four pads.
- The network carried the heat row's board share, 0.5 × 1.348 W = 0.674 W, all of it through the pins.
- The other half (`sink_fraction` 0.5, "convects from the case") left the model.

**Now, done the same way the film caps got their body path (`film_hf`, jet-2026-10-15).**
- **Loss.** The body node carries the **whole module loss**: the heat row's 1.348 W, which is P_out (1/0.84 − 1) at
  P_out = 7.08 W.
  - The row's board and case shares must sum to 1, or the build refuses.
  - η 0.84 is make_heat_sources' conservative bound below the datasheet's 87 % typ, which is specified at 230 VAC and full
    load (p.2 Note 1). At 87 % the loss would be 1.058 W. MEAN WELL publishes no efficiency at 120 VAC or 33 % load.
- **Both paths are kept and solved.**
  - **Pins:** the class value of 15 K/W, split by pad copper area. It is ASSUMED: four 1.04 mm pins, 3.5 mm (p.4), and
    the in-body path is unpublished.
  - **Case to air:**
    - g_air = h·A on an isothermal potted body (the module is "Encapsulated Type", p.1–p.4);
    - A = top + four sides = 52.4·27.2 + 2(52.4 + 27.2)·24 = **5246 mm²**;
    - h = the case h (10 W/m²K, still air).
  - Not credited: the bottom face and radiation (B3's h 10 already includes radiation).
- **Air.** The air is bay + `MODULE_AIR_RISE_K`. That constant **is** `FILM_HF_AIR_RISE_K`, the film caps' 15 K rule
  (board-heated layer + plume + 3 K headroom), so there is one value.
  - A `TopRegion` that credits the body replaces it, as for the caps.
  - The run also records the layer estimate behind the rule for PS2's 24 mm faces: `layer_factor(24)` = 0.178 × the
    F.Cu excess of the 10 mm ring around the body (0.242 at the caps' 17.5 mm, which is the rule's 0.24).
- **Controls.** `--module-pins-only` is the pre-S18 model. Sensitivities:
  - `--module-r-pad` (pin path);
  - `--module-gap-mm` (bottom face to the board under it, one local tie per cell);
  - `--module-air-rise`.
- **Run file.** The PS2 row records:
  - `loss_w`, `pins_w`, `body_air_w`, `gap_w`;
  - `case_c`;
  - `env_upper_c`;
  - `board_under_body_c`, `board_ring_c`;
  - `layer_factor`.

**Gate row** (`b3_ratings_gate.MODULES` / `module_rows`, hot-copper basis only, as the probe rows are):
- **est** = bay + max(15 K rule, layer_factor × ring excess). This is the local air.
- **Limit** = the p.3 ambient at which 0.9 × curve(T) × 21.6 W = P_out. That is the ledger's MPM-20-24 derating rule,
  "output … ≤ 90 % of the curve-derated power", with the bay replaced by the local air.
  - P_out = the run's loss / (1/0.84 − 1) = 7.078 W (32.8 %). The test reproduces the make_heat_sources C28_F formula.
  - The limit is 80.2 °C. The curve alone gives 82.9 °C, which the row also records.
- **Refusals:**
  - pins-only or old hot runs (unless `--allow-module-pins-only`, which then writes no row);
  - pins carrying heat *into* the module (a board-heated module, where local air would not cover it);
  - a load over the rule at any ambient;
  - another MPN at PS2 on the frozen BOM;
  - meshes that disagree on loss or air;
  - a rotated body box.

## 3. Results (`results/ps2-summary.json`, `results/margins-s18.json`)

**PS2's gated row.** All temperatures are in °C.

| Case | Local air (rated) | Layer estimate | Limit (90 % / curve) | **Margin** | Case node | Pad max | Pins / air (W) |
|---|---|---|---|---|---|---|---|
| c17.5 @ 61 | **76.0** (61 + 15) | 61 + 3.0 | 80.2 / 82.9 | **+4.2 K** (+6.9) | 95.5 | 91.5 | 0.34 / 1.01 |
| c22 @ 55 | 70.0 | 55 + 4.0 | 80.2 / 82.9 | **+10.2 K** (+12.9) | 90.8 | 87.5 | 0.27 / 1.08 |
| c28 @ 55 | 70.0 | 55 + 5.8 | 80.2 / 82.9 | **+10.2 K** (+12.9) | 93.2 | 97.6 | 0.14 / 1.20 |

- **The pad proxy falls** from 109.2 / 108.2 / 117.6 °C (pins-only, 0.25 mm) to 91.1 / 86.9 / 97.1 °C. The 15 K rule
  governs the air in every case: the layer estimate stays at 3–6 K.
- **The pins export heat in every case.** The c28 share is the smallest, 0.14 W, because the board around PS2 is
  hotter there: the 10 mm ring reads 86.8 °C at 0.25 mm, against 77.8 °C at release.
- **Energy** closes to ≤ 4e-11 relative.

**Release and ratchets** (card metrics; same board, same run inputs apart from PS2):

| Metric | s47 (pins-only PS2) | S18 model |
|---|---|---|
| `b3_release_margin_K` | +1.0 (R10) | **+1.2** (R10) |
| `b3_laminate_margin_K` | −51.1 | −51.0 |
| `b3_rated_part_margin_K` | −51.3 (R12, c28) | −51.2 (R12, c28) |
| `b3_advisory_margin_K` (not on the card) | −17.5 (C21, c28) | −16.0 (C21, c28) |
| `b3_ratings` | PASS | PASS |

- **Why the board cools.** With the case-to-air path, 0.34 W instead of 0.674 W enters the board at release (0.14 W at
  c28). Every common row moves the same way, cooler, by 0 to +3.1 K.
- **Largest moves:**
  - R22–R25 (27–39 mm from PS2), +1.7 to +3.1 K;
  - C21 / C22, +0.6 to +1.5 K;
  - R10, +0.2 K: est 131.0 → 130.8 °C against 131.9 °C.

**Corners at c17.5 @ 61** (pin path and bottom-face gap, one case each):

| Corner | Board gets (pins + gap) | Case node | PS2 margin | Release (R10) |
|---|---|---|---|---|
| Strong tie: r_pad 5 K/W + 0.22 mm bottom gap (the KiCad 3D model's seat: PS2 box top z 25.713 − 24 over the 1.493 mm board top) | 0.15 + 0.63 = 0.78 W | 86.9 | +4.2 K | **+1.1 K** |
| Central: 15 K/W, no gap | 0.34 W | 95.5 | +4.2 K | +1.2 K |
| Weak tie: 40 K/W | 0.25 W | 97.0 | +4.2 K | +1.2 K |

- **The strong corner puts more heat into the board than the old model did** (0.78 vs 0.674 W), and R10 still reads
  +1.1 K. The heat now spreads under the body, onto copper-poor laminate, instead of being forced into the pins' 0.4 mm
  tracks. So the +0.1 to +0.2 K release gain does not depend on the assumed tie.
- **Release margin across the corners: +1.1 to +1.2 K. The binding row stays R10.**

**Control.** `--module-pins-only` reproduced all six s47 run files, identical apart from `runtime_s` /
`cg_iterations` / `sens`. Through the gate (`--allow-module-pins-only`) it reproduced the committed s47 `margins.json`
byte for byte (`cmp`).

## 4. Where this differs from the S18 study (`b3-ratings/ps2-thermal-2026-10-15`)

**The estimates.**
- The study estimated an equivalent ambient of 65.1 °C at c18 @ 61, so +17.8 K.
- This row reads +4.2 K (+6.9 K on the curve), because it rates **bay + 15 K**, the film caps' board-heated-air rule, not
  the study's 61–64 °C of air. The 15 K rule is conservative here: PS2's own layer estimate is 3.0 K.
- The study's "pessimistic bound" (+2.9 K) used the same bay + 15 K but also took the hottest pad as surroundings. This
  row rates the air, as the datasheet does.

**Case node.**
- The study put the case at about 81 °C at c18 @ 61.
- The model reads 95.5 °C at c17.5 @ 61: 19.5 K over its 76 °C air, against the study's +16 K over its 65 °C equivalent
  ambient. The rise over local air agrees within the study's corner range. The absolute is higher only because the air
  is.

**Not rated: `env_upper_c`.** This is the case node's pin-pad environment, (g_air·T_air + Σg·T_pad) / Σg. It reads
84.2 / 79.5 / 81.9 °C, which is 4 K over the 90 % limit at release. It is an upper bound that double-counts PS2's own
spreading rise on its pads (34 K of the old pad reading, by the study's zero-PS2 solve). The datasheet rates air, so it
is reported only. If the bench finds the board under PS2 hotter than its local air, the right row is an equivalent
ambient, and the gate already refuses a board that heats the module through its pins.

## 5. Ledger, chain and card

**Ledger** (`scripts/ledger_s18.py`, idempotent; `gate.py` PASS, `tests/test_gate.py` 0 failures):
- **Why it was touched.** The ledger cites `margins.json` rows by key, and the body path moved them by 0.1–2.8 K. With
  the new rows, 28 keyed citations in 10 entries were stale and the gate failed.
- **Re-citing.** The script re-cites those citations. It moves each stress's worst_case_value and the ratings derived
  from a cited terminal row:
  - 25121WF680JT4E: 1 W·(155 − T)/85 at R10 130.8 °C / R12 142.9 °C;
  - CSS2H: 5 W·(170 − T)/100, parameter names included.
  It then recomputes every affected check ratio.
- **Every ratio moves toward margin.** For example, 25121WF680JT4E's release power check goes from 0.7684 to 0.7622.
- **MPM-20-24 gains the B3 PS2 row** as a keyed stress, "Local air at PS2, B3 (release case)" 76.0 °C. It is checked
  against the rating "Ambient limit at the as-built load (90 % rule)", 80.2 °C (ratio 0.9476). The entry's status and its
  existing gaps (local air unmeasured, the 78 °C stacked bay) are unchanged.

**Chain** (`sh native-21/layout/gates/chain.sh native21s47 runs-native21/s46/pass-j1 runs-native21/s18-ps2/chain`,
TASK04_WORKERS=4).
- **It ran because the card reads the moved B3 metrics.** It reached CHAIN_DONE, `exit=0`.
- **B3 ratings matched the direct runs exactly.** The chain's `margins.json` equals `results/margins-s18.json` apart from
  `board_sha256`.
- **Board hash.** The chain's build hashes to `7317a1f3…` instead of s47's `4139c87b…`, with the same copper key
  `387b3e2d48c8` and the same 8806 primitives.
  - Eight primitives (hole outlines in filled zones near x 129 mm) differ at the micron level, by a few vertices placed
    or added; that is KiCad fill jitter.
  - The D5 audit's tied minimum (8.507 mm) moved from C3 to C4.
  - So the chain's tracked build outputs (geometry export, gerbers, boxes, Kelvin pin, caches) were **restored**, not
    committed. The committed `margins.json` is the direct BASIS run on the committed s47 geometry (`4139c87b`).
- **Card** (`results/scorecard-native21s47-s18.json`, `results/compare.txt`):

```
ACCEPT native21s47 vs validation-results/10-benchmark/scorecard-native21s47.json: cheaper [], better ['b3_laminate_margin_K', 'b3_rated_part_margin_K', 'b3_release_margin_K']
```

Against the s47 card, only `board_sha256` (the fill jitter), `build`, `sources.b3_ratings` and the three B3 metrics
change: release +1.0 → +1.2, laminate −51.1 → −51.0, rated parts −51.3 → −51.2. Every gate is unchanged.

## 5b. What it means for the ledger's other loads (not gated)

| Load | % of 21.6 W | Limit, 90 % / curve | Margin at release (local air 76.0) | At bay 55 (70.0) |
|---|---|---|---|---|
| As built, 60 kHz window top (B3's heat row; gated) | 32.8 | 80.2 / 82.9 | **+4.2 / +6.9 K** | +10.2 / +12.9 K |
| Ledger "P bias allocation" 9.59 W (740 nC, 80 kHz; not a physical charge) | 44.4 | 70.5 / 74.2 | **−5.5 / −1.8 K** | +0.5 / +4.2 K |

- **The ledger's sizing allocation does not fit the derating at the modelled local air of the release case.** The ledger
  check "P at 61 C bay" (65 %) passes only because it reads the curve at bay air.
- The as-built load passes. The firmware's 60 kHz window top is what holds PS2 at 7.08 W, so that window top is now a
  PS2 rating constraint (as the S18 study proposed).
- **The audit's 78 °C stacked bay** puts the local air at 93 °C. That is above the 85 °C working maximum at any load, so
  it fails outright. That case is already a ledger gap (the bay, not this model).

## 6. Bench check (S2 soak) that would confirm it

PS2 is at hazardous voltage on every pin: pins 1 and 2 are mains, and the output is HOT-referenced with no PE bond. Use
insulated fine-wire K thermocouples and an isolated logger, or IR through a port. Run at the c17.5-equivalent operating
point and log PS2's output (V24_RAW) current.

| TC | Placement | What it tests | Model (c17.5 @ 61, rise over TC3) | Confirms | Refutes |
|---|---|---|---|---|---|
| TC2, **the rated quantity** | Shielded bead in free air 5 mm off PS2's long side face, at mid-height (12 mm above the board), on the side away from J3, not touching anything | Local air | ≤ +15 K (rule); layer estimate +3 K | TC2 − TC3 ≤ +15 K | **> +19.2 K** (61 + 19.2 = the 80.2 °C limit; +21.9 K against the curve). A second bead 5 mm above the top-face centre reads the plume; record it |
| TC3 | Bay air, ≥ 50 mm from any board part, shielded | Bay | 0 | — | — |
| TC1 | PS2 case top-face centre, Kapton- or epoxy-bonded | Case-to-air path | TC1 − TC2 ≈ +19.5 K (+10.9 strong tie … +21.0 weak) | +11 … +21 K | ≥ +27 K: the air path is weaker than h·A at h 10, so the case and pins run hotter |
| TC4 | Pin 1 or pin 4 pad, solder side | Pin share | TC4 − TC3 ≈ +30 K (91 °C at bay 61) | ≤ +32 K | ≈ +44 … +48 K (the old 105–109 °C): the pins really carry the loss |
| — | PS2 output power | Load | 6.5–7.1 W | ≤ 7.1 W | > 9.6 W (the margin falls to −5.5 K, section 5) |

Rating criterion for the ledger: (TC2 − TC3) + 61 °C ≤ the p.3 limit at the measured load under the 90 % rule (80.2 °C
at 7.08 W).

## 7. Did not match / open

- **The 85 °C "pad vs rating" line is gone, and the monitor sweep skips PS2 by itself.**
  `monitor-probes-2026-10-15/scripts/monitor_sweep.py` excludes refs that have a gate row. The c47
  `monitor-sweep-s47.json` record still lists PS2 at 111.5 °C; it is a dated record.
- **The heat row's split is now unused by the network.** It is still read by the legacy `b3/thermal.py` point model,
  which keeps 0.674 W into the pads. That is the legacy peak metrics' basis (`b3_c28_h25_peak_C`, `b3_nominal_h10_peak_C`),
  and this lane does not change it.
- **Assumed, not sourced:**
  - the 15 K/W pin path (corners 5–40);
  - η at 120 VAC / 33 % load (0.84 used; datasheet 87 % typ is at 230 VAC full load);
  - the bottom-face gap (0.22 mm in the KiCad model; MEAN WELL draws none);
  - where MEAN WELL measures "ambient".
- **MEAN WELL's installation manual asks for a 10–15 cm clearance from an adjacent heat source** (PCB_EN p.1 (4)). PS2
  sits 27–39 mm from R22–R25 and on a board carrying 13.5 A. This is a certifier / owner reading, not a rating. Recorded,
  not acted on.
- **Not done:** no OPEN-ITEMS edit, no BOM or copper change.

## Files

- `scripts/summarize.py`: the summary and row deltas, read from the run files and margins files.
- `results/ps2-summary.json`: PS2 rows, splits, corners, and row deltas against s47.
- `results/margins-s18.json`: the gate output for this model (the same file as b3-ratings `margins.json` here).
- `results/datasheet-manifest.json`: URLs, sha256 and verbatim quotes.
- `results/scorecard-native21s47-s18.json`, `results/compare.txt`: the chain card and its comparison with s47.
- `scripts/ledger_s18.py`: the ledger re-cite and the MPM-20-24 B3 stress (commit 2).
- Code (commit 1):
  - `b3-convergence/thermal_body.py`;
  - `b3-convergence/body_runs.py`;
  - `b3-ratings/b3_ratings_gate.py`;
  - `b3-ratings/run_basis.py`;
  - `b3-ratings/test_b3_airflow.py`.
